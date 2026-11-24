import io
import logging
import os
import re
import wave
from dataclasses import dataclass, field
from typing import Optional

import httpx
from utils.errors import public_error_message
from utils.i18n import msg as ui_msg

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；.!?;؟\n])\s*")


def _make_minimal_wav() -> bytes:
    """Create an in-memory 0.25s 16kHz mono PCM WAV buffer for health probing."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 4000)
    return buf.getvalue()


def _get_audio_duration_ms(file_path: str) -> int:
    try:
        import soundfile as sf

        info = sf.info(file_path)
        if info.frames > 0 and info.samplerate > 0:
            return int(info.frames * 1000 / info.samplerate)
    except Exception:
        pass
    try:
        with wave.open(file_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if frames > 0 and rate > 0:
                return int(frames * 1000 / rate)
    except Exception:
        pass
    return 0


def _extract_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:300]
            for key in ("detail", "message", "msg"):
                if data.get(key):
                    return str(data[key])[:300]
    except Exception:
        pass
    # The raw body is not shown: the address can point anywhere, so only the status
    # code and a service's own structured error message are reported.
    return ui_msg("service_returned", status=response.status_code)


@dataclass
class FunASRSegment:
    speaker: int
    text: str
    start: int
    end: int


@dataclass
class FunASRResult:
    success: bool
    duration: int = 0
    speaker_count: int = 0
    full_text: str = ""
    segments: list[FunASRSegment] = field(default_factory=list)
    error_message: Optional[str] = None


def _text_to_segments(full_text: str, duration_ms: int) -> list[FunASRSegment]:
    """Split a plain transcript into sentence segments with proportional timestamps."""
    cleaned = (full_text or "").strip()
    if not cleaned:
        return []

    parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(cleaned) if part and part.strip()]
    if not parts:
        return []

    if duration_ms <= 0:
        return [FunASRSegment(speaker=0, text=part, start=0, end=0) for part in parts]

    total_chars = sum(len(part) for part in parts) or len(parts)
    consumed_chars = 0
    segments: list[FunASRSegment] = []

    for index, part in enumerate(parts):
        start_ms = int(round(consumed_chars * duration_ms / total_chars))
        consumed_chars += len(part)
        end_ms = duration_ms if index == len(parts) - 1 else int(round(consumed_chars * duration_ms / total_chars))
        segments.append(FunASRSegment(speaker=0, text=part, start=start_ms, end=max(start_ms, end_ms)))

    return segments


class FunASRClient:
    """Client for OpenAI-compatible /audio/transcriptions endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout or int(os.getenv("FUNASR_TIMEOUT", "600"))

    def _build_transcribe_url(self) -> str:
        return (
            self.base_url
            if self.base_url.endswith("/audio/transcriptions")
            else f"{self.base_url}/audio/transcriptions"
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def transcribe(
        self,
        file_path: str,
        hotword: str | None = None,
    ) -> FunASRResult:
        if not os.path.exists(file_path):
            return FunASRResult(success=False, error_message=ui_msg("file_not_found", path=file_path))

        data: dict[str, str] = {}
        if self.model:
            data["model"] = self.model
        if hotword:
            data["prompt"] = hotword

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        self._build_transcribe_url(),
                        headers=self._headers(),
                        files={"file": (os.path.basename(file_path), f)},
                        data=data,
                    )
        except httpx.TimeoutException:
            return FunASRResult(success=False, error_message=ui_msg("asr_timeout", seconds=self.timeout))
        except httpx.ConnectError:
            return FunASRResult(success=False, error_message=ui_msg("asr_cannot_connect", url=self.base_url))
        except Exception as exc:
            return FunASRResult(success=False, error_message=ui_msg("asr_failed_detail", error=exc))

        if response.status_code not in (200, 201):
            return FunASRResult(success=False, error_message=_extract_error_message(response))

        try:
            payload = response.json()
        except ValueError:
            return FunASRResult(success=False, error_message=ui_msg("asr_non_json"))

        if not isinstance(payload, dict):
            return FunASRResult(success=False, error_message=ui_msg("asr_bad_format"))

        if payload.get("success") is False:
            return FunASRResult(success=False, error_message=payload.get("error") or ui_msg("asr_failed"))

        result_data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        full_text = str(result_data.get("text") or result_data.get("full_text") or "").strip()
        duration_ms = self._to_ms(result_data.get("duration")) or _get_audio_duration_ms(file_path)

        raw_segments = result_data.get("segments")
        segments: list[FunASRSegment] = []
        if isinstance(raw_segments, list) and raw_segments:
            for seg in raw_segments:
                if not isinstance(seg, dict):
                    continue
                seg_text = str(seg.get("text", "") or "").strip()
                if not seg_text:
                    continue
                segments.append(
                    FunASRSegment(
                        speaker=self._int_or_zero(seg.get("speaker")),
                        text=seg_text,
                        start=self._to_ms(seg.get("start")),
                        end=self._to_ms(seg.get("end")),
                    )
                )

        if not segments and full_text:
            segments = _text_to_segments(full_text, duration_ms)

        if not full_text and segments:
            full_text = " ".join(seg.text for seg in segments)

        speakers = {seg.speaker for seg in segments} or {0}
        return FunASRResult(
            success=True,
            duration=duration_ms,
            speaker_count=self._int_or_zero(result_data.get("speaker_count")) or len(speakers),
            full_text=full_text,
            segments=segments,
        )

    async def health_check(self) -> tuple[bool, str]:
        try:
            wav_bytes = _make_minimal_wav()
            data = {"model": self.model} if self.model else {}
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    self._build_transcribe_url(),
                    headers=self._headers(),
                    files={"file": ("probe.wav", wav_bytes, "audio/wav")},
                    data=data,
                )
            if response.status_code in (200, 201):
                label = ui_msg("conn_ok_model", model=self.model) if self.model else ui_msg("conn_ok")
                return True, label
            return False, _extract_error_message(response)
        except httpx.ConnectError:
            return False, ui_msg("cannot_connect_url", url=self.base_url)
        except httpx.TimeoutException:
            return False, ui_msg("conn_timeout_url", url=self.base_url)
        except Exception as exc:
            logger.warning("FunASR connection test failed: %s", exc)
            return False, public_error_message(exc)

    @staticmethod
    def _to_ms(value) -> int:
        if value is None or value == "":
            return 0
        if isinstance(value, float):
            return max(0, int(round(value * 1000)))
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            try:
                return max(0, int(round(float(value) * 1000)))
            except (TypeError, ValueError):
                return 0

    @staticmethod
    def _int_or_zero(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
