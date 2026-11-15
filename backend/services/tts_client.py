import io
import os
import re
import wave
from pathlib import Path
from typing import Optional

import httpx
from utils.i18n import msg as ui_msg

_CITATION_RE = re.compile(r"\[citation_[^\]]+\]")
_FENCED_CODE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:\-\|]+\|?\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।؟。！？；;\n])\s+")

# Dialogue scripts mark each turn with one of these speaker tags at line start.
DIALOGUE_SPEAKERS = ("HOST", "GUEST")
_SPEAKER_LINE_RE = re.compile(r"^\s*(?:\*\*|__)?\s*(HOST|GUEST)\s*[:：]\s*(?:\*\*|__)?\s*", re.IGNORECASE)


def parse_voices(value: str | None, default: str = "deniz") -> list[str]:
    """`"deniz, emre"` -> `["deniz", "emre"]`; the setting may hold one voice or a list."""
    voices = [v.strip() for v in re.split(r"[,;\s]+", value or "") if v.strip()]
    return voices or [default]


def split_dialogue(markdown: str) -> list[tuple[str, str]]:
    """Return (speaker, text) turns from a script whose lines start with `HOST:` / `GUEST:`.

    Text before the first tag is spoken by the host; a line without a tag continues the
    previous turn, so a paragraph broken over several lines stays one turn.
    """
    turns: list[tuple[str, str]] = []
    for raw_line in (markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SPEAKER_LINE_RE.match(line)
        if match:
            turns.append((match.group(1).upper(), line[match.end():].strip()))
        elif turns:
            speaker, text = turns[-1]
            turns[-1] = (speaker, f"{text} {line}".strip())
        else:
            turns.append(("HOST", line))
    return [(speaker, text) for speaker, text in turns if text]


def _clean_text_for_speech(markdown: str) -> str:
    """Convert Markdown narration with citation markers into clean plain text for TTS."""
    text = (markdown or "").strip()
    if not text:
        return ""

    text = _CITATION_RE.sub("", text)
    text = _FENCED_CODE_RE.sub(r"\1", text)
    text = text.replace("`", "")
    text = _LINK_RE.sub(r"\1", text)
    text = _TABLE_SEP_RE.sub("", text)
    text = text.replace("|", ", ")
    text = _HEADING_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)[*_]|[*_](?!\w)", "", text)
    # Clean stray spaces before punctuation introduced by removing citations
    text = re.sub(r"\s+([.,!?;:،؛。！？])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def blocks_to_speech_text(blocks: list[dict]) -> str:
    """Extract readable text from FeatureAgent blocks (heading/paragraph/quote/list) for TTS."""
    sections: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        if block.get("block_type") == "audio":
            continue
        parts = block.get("content_parts")
        if isinstance(parts, list) and parts:
            text_piece = "".join(
                str(part.get("content", ""))
                for part in parts
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        else:
            raw_content = block.get("content")
            text_piece = str(raw_content).strip() if isinstance(raw_content, str) else ""
        if text_piece:
            sections.append(text_piece)
    return _clean_text_for_speech("\n\n".join(sections))


def _split_long_piece(piece: str, max_chars: int) -> list[str]:
    """Split a single segment exceeding max_chars along word boundaries or hard slices."""
    words = piece.split()
    if not words:
        return [piece[i:i + max_chars] for i in range(0, len(piece), max_chars)]

    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(word), max_chars):
                part = word[i:i + max_chars]
                if len(part) == max_chars:
                    chunks.append(part)
                else:
                    current = part
            continue
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def _split_text_for_tts(text: str, max_chars: int = 3500) -> list[str]:
    """Split text into chunks respecting sentence boundaries and max_chars."""
    cleaned = _clean_text_for_speech(text)
    if not cleaned:
        return []
    if max_chars <= 0:
        max_chars = 3500

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(cleaned) if s and s.strip()]
    if not sentences:
        return []

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_piece(sentence, max_chars))
            continue

        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)
    return chunks


def _strip_id3v2(data: bytes) -> bytes:
    """Strip an ID3v2 header from an MP3 buffer so consecutive MP3 frames concatenate cleanly."""
    if len(data) >= 10 and data[:3] == b"ID3":
        size = (
            ((data[6] & 0x7F) << 21)
            | ((data[7] & 0x7F) << 14)
            | ((data[8] & 0x7F) << 7)
            | (data[9] & 0x7F)
        )
        offset = 10 + size
        if offset < len(data):
            return data[offset:]
    return data


def _merge_audio_chunks(chunks: list[bytes], content_type: str = "") -> tuple[bytes, str, str]:
    """Merge synthesized audio chunks and return (bytes, extension, mime_type)."""
    non_empty = [c for c in chunks if c]
    if not non_empty:
        raise RuntimeError(ui_msg("tts_empty_response"))

    ctype = (content_type or "").split(";")[0].strip().lower()
    first = non_empty[0]

    is_wav = "wav" in ctype or first[:4] == b"RIFF"
    if is_wav:
        if len(non_empty) == 1:
            return non_empty[0], "wav", "audio/wav"
        try:
            out_buf = io.BytesIO()
            with wave.open(io.BytesIO(non_empty[0]), "rb") as w0:
                params = w0.getparams()
                frames = [w0.readframes(w0.getnframes())]
            for chunk in non_empty[1:]:
                with wave.open(io.BytesIO(chunk), "rb") as wi:
                    frames.append(wi.readframes(wi.getnframes()))
            with wave.open(out_buf, "wb") as w_out:
                w_out.setparams(params)
                for frame_data in frames:
                    w_out.writeframes(frame_data)
            return out_buf.getvalue(), "wav", "audio/wav"
        except Exception:
            return b"".join(non_empty), "wav", "audio/wav"

    is_ogg = "ogg" in ctype or first[:4] == b"OggS"
    if is_ogg:
        return b"".join(non_empty), "ogg", "audio/ogg"

    # Default: MP3 (audio/mpeg)
    if len(non_empty) == 1:
        return non_empty[0], "mp3", "audio/mpeg"
    merged = non_empty[0] + b"".join(_strip_id3v2(c) for c in non_empty[1:])
    return merged, "mp3", "audio/mpeg"


def _extract_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            for key in ("detail", "message", "msg"):
                if data.get(key):
                    return str(data[key])
    except Exception:
        pass
    text = (response.text or "").strip()
    return f"HTTP {response.status_code}" + (f": {text[:300]}" if text else "")


class TTSClient:
    """Client for OpenAI-compatible /audio/speech text-to-speech endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        voice: str = "deniz",
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.voice = parse_voices(voice)[0]
        self.timeout = timeout or int(os.getenv("TTS_TIMEOUT", "180"))

    async def _post_chunks(
        self,
        client: httpx.AsyncClient,
        chunks: list[str],
        voice: str,
        label: str = "",
    ) -> tuple[list[bytes], str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        audio_chunks: list[bytes] = []
        content_type = ""
        for idx, chunk in enumerate(chunks, start=1):
            payload = {"model": self.model, "input": chunk, "voice": voice}
            resp = await client.post(self.speech_url, headers=headers, json=payload)
            if resp.status_code != 200 or not resp.content:
                where = f"{label}, " if label else ""
                raise RuntimeError(
                    ui_msg("tts_chunk_error", where=where, index=idx, total=len(chunks), error=_extract_error_message(resp))
                )
            content_type = resp.headers.get("content-type", content_type)
            audio_chunks.append(resp.content)
        return audio_chunks, content_type

    async def synthesize_dialogue(
        self,
        turns: list[tuple[str, str]],
        voices: dict[str, str],
        max_chars_per_chunk: int = 3500,
    ) -> tuple[bytes, str, str]:
        """Speak each (speaker, text) turn with that speaker's voice and join the audio."""
        all_chunks: list[bytes] = []
        content_type = "audio/mpeg"
        spoken = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(self.timeout), connect=15.0)) as client:
            for index, (speaker, text) in enumerate(turns, start=1):
                chunks = _split_text_for_tts(text, max_chars=max_chars_per_chunk)
                if not chunks:
                    continue
                voice = voices.get(speaker) or self.voice
                audio, ctype = await self._post_chunks(client, chunks, voice, label=f"{speaker.lower()} {index}")
                all_chunks.extend(audio)
                content_type = ctype or content_type
                spoken += 1
        if spoken == 0:
            raise RuntimeError(ui_msg("tts_no_dialogue"))
        return _merge_audio_chunks(all_chunks, content_type)

    async def synthesize_dialogue_to_file(
        self,
        turns: list[tuple[str, str]],
        voices: dict[str, str],
        output_dir: Path,
        stem: str,
    ) -> tuple[Path, str]:
        audio_bytes, ext, mime_type = await self.synthesize_dialogue(turns, voices)
        output_dir.mkdir(parents=True, exist_ok=True)
        for old_file in output_dir.glob(f"{stem}.*"):
            old_file.unlink(missing_ok=True)
        output_path = output_dir / f"{stem}.{ext}"
        output_path.write_bytes(audio_bytes)
        return output_path, mime_type

    @property
    def speech_url(self) -> str:
        if self.base_url.endswith("/audio/speech"):
            return self.base_url
        return f"{self.base_url}/audio/speech"

    async def synthesize(self, text: str, max_chars_per_chunk: int = 3500) -> tuple[bytes, str, str]:
        chunks = _split_text_for_tts(text, max_chars=max_chars_per_chunk)
        if not chunks:
            raise RuntimeError(ui_msg("tts_no_text"))

        async with httpx.AsyncClient(timeout=httpx.Timeout(float(self.timeout), connect=15.0)) as client:
            audio_chunks, content_type = await self._post_chunks(client, chunks, self.voice)

        return _merge_audio_chunks(audio_chunks, content_type or "audio/mpeg")

    async def synthesize_to_file(
        self,
        text: str,
        output_dir: Path,
        stem: str,
        max_chars_per_chunk: int = 3500,
    ) -> tuple[Path, str]:
        audio_bytes, ext, mime_type = await self.synthesize(
            text=text,
            max_chars_per_chunk=max_chars_per_chunk,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        for old_file in output_dir.glob(f"{stem}.*"):
            old_file.unlink(missing_ok=True)
        output_path = output_dir / f"{stem}.{ext}"
        output_path.write_bytes(audio_bytes)
        return output_path, mime_type

    @staticmethod
    async def health_check(
        base_url: str,
        api_key: str,
        model: str,
        voice: str = "deniz",
    ) -> tuple[bool, str]:
        if not (base_url or "").strip():
            return False, ui_msg("tts_missing_url")
        if not (api_key or "").strip():
            return False, ui_msg("tts_missing_key")
        if not (model or "").strip():
            return False, ui_msg("tts_missing_model")

        client = TTSClient(base_url=base_url, api_key=api_key, model=model, voice=voice)
        try:
            headers = {
                "Authorization": f"Bearer {client.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": client.model,
                "input": "Merhaba.",
                "voice": client.voice,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as http:
                resp = await http.post(client.speech_url, headers=headers, json=payload)
            if resp.status_code == 200 and len(resp.content) > 64:
                return True, ui_msg("tts_ready", model=client.model, voice=client.voice)
            return False, _extract_error_message(resp)
        except httpx.ConnectError:
            return False, ui_msg("tts_cannot_connect", url=client.speech_url)
        except httpx.TimeoutException:
            return False, ui_msg("tts_timeout", url=client.speech_url)
        except Exception as exc:
            return False, ui_msg("tts_check_failed", error=exc)
