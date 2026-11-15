import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "packages"))

from workers.parsers.audio_parser import AudioParser


def segment(speaker: int, text: str, start: int, end: int):
    return SimpleNamespace(speaker=speaker, text=text, start=start, end=end)


class AudioParserMergeTests(unittest.TestCase):
    def test_merges_nearby_chinese_segments_from_same_speaker(self):
        parser = AudioParser()

        blocks = parser._build_blocks([
            segment(0, "我们现在开始。", 0, 900),
            segment(0, "接下来讲第一个问题。", 1100, 2600),
        ])

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].content, "我们现在开始。接下来讲第一个问题。")
        self.assertEqual(blocks[0].extra["time_start"], 0)
        self.assertEqual(blocks[0].extra["time_end"], 2600)
        self.assertEqual(blocks[0].extra["source_segment_count"], 2)

    def test_keeps_different_speakers_separate(self):
        parser = AudioParser()

        blocks = parser._build_blocks([
            segment(0, "这个问题我先说一下。", 0, 900),
            segment(1, "我补充一个细节。", 1000, 1800),
        ])

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].content, "这个问题我先说一下。")
        self.assertEqual(blocks[1].content, "我补充一个细节。")

    def test_text_units_handle_chinese_and_english_differently(self):
        parser = AudioParser()

        self.assertEqual(parser._text_units("中文测试"), 4)
        self.assertEqual(parser._text_units("hello world"), 4)
        self.assertLess(parser._text_units("internationalization"), len("internationalization"))


class AudioTranscriptSegmentationTests(unittest.TestCase):
    def test_text_to_segments_with_duration(self):
        from services.funasr_client import _text_to_segments

        text = "First sentence. Second sentence! Third line\nFourth question?"
        segments = _text_to_segments(text, duration_ms=10000)

        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[0].start, 0)
        self.assertEqual(segments[-1].end, 10000)
        for i, seg in enumerate(segments):
            self.assertLessEqual(seg.start, seg.end)
            if i > 0:
                self.assertEqual(seg.start, segments[i - 1].end)

    def test_text_to_segments_without_duration(self):
        from services.funasr_client import _text_to_segments

        segments = _text_to_segments("Sentence one。Sentence two！", duration_ms=0)
        self.assertEqual(len(segments), 2)
        for seg in segments:
            self.assertEqual(seg.start, 0)
            self.assertEqual(seg.end, 0)

    def test_funasr_client_to_ms(self):
        from services.funasr_client import FunASRClient

        self.assertEqual(FunASRClient._to_ms(1.5), 1500)
        self.assertEqual(FunASRClient._to_ms(0.25), 250)
        self.assertEqual(FunASRClient._to_ms(1500), 1500)
        self.assertEqual(FunASRClient._to_ms(0), 0)


class TTSClientTests(unittest.TestCase):
    def test_clean_text_for_speech_strips_citations_and_markdown(self):
        from services.tts_client import _clean_text_for_speech

        md = (
            "## Giriş\n\n"
            "**Ana fikir** budur [citation_1]. Ayrıntılar [citation_2] ile verilmiştir.\n\n"
            "> Alıntı satırı\n"
            "- Birinci madde (`kod`)\n"
            "| Sütun 1 | Sütun 2 |\n"
            "| --- | --- |\n"
            "| A | B |\n"
        )
        cleaned = _clean_text_for_speech(md)
        self.assertNotIn("citation_", cleaned)
        self.assertNotIn("##", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertNotIn("---", cleaned)
        self.assertIn("Giriş", cleaned)
        self.assertIn("Ana fikir budur.", cleaned)
        self.assertIn("Ayrıntılar ile verilmiştir.", cleaned)

    def test_blocks_to_speech_text_reads_content_parts_and_skips_audio(self):
        from services.tts_client import blocks_to_speech_text

        blocks = [
            {"block_type": "audio", "asset": {"url": "/api/features/f1/audio"}, "caption": "voxcpm2"},
            {
                "block_type": "heading",
                "level": 2,
                "content_parts": [{"type": "text", "content": "Bölüm Başlığı"}],
            },
            {
                "block_type": "paragraph",
                "content_parts": [
                    {"type": "text", "content": "İlk cümle "},
                    {"type": "citation_ref", "citation_id": "citation_1", "display_num": 1},
                    {"type": "text", "content": "."},
                ],
            },
        ]
        spoken = blocks_to_speech_text(blocks)
        self.assertEqual(spoken, "Bölüm Başlığı\n\nİlk cümle.")

    def test_split_text_for_tts_respects_max_chars_and_sentences(self):
        from services.tts_client import _split_text_for_tts

        text = "Birinci cümle. İkinci cümle! Üçüncü cümle? " + ("kelime " * 30)
        chunks = _split_text_for_tts(text, max_chars=80)
        self.assertGreater(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 80)

    def test_strip_id3v2_and_merge_mp3_and_wav_chunks(self):
        import io
        import wave
        from services.tts_client import _merge_audio_chunks, _strip_id3v2

        # ID3v2 header of payload size 5 (bytes 6-9 synchsafe = 0,0,0,5) followed by MP3 frame
        id3_chunk = b"ID3\x03\x00\x00\x00\x00\x00\x05hello" + b"\xff\xfb\x90\x00FRAME2"
        stripped = _strip_id3v2(id3_chunk)
        self.assertEqual(stripped, b"\xff\xfb\x90\x00FRAME2")

        chunk1 = b"\xff\xfb\x90\x00FRAME1"
        merged_mp3, ext, mime = _merge_audio_chunks([chunk1, id3_chunk], "audio/mpeg")
        self.assertEqual(ext, "mp3")
        self.assertEqual(mime, "audio/mpeg")
        self.assertEqual(merged_mp3, b"\xff\xfb\x90\x00FRAME1\xff\xfb\x90\x00FRAME2")

        def make_wav(samples: bytes) -> bytes:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(samples)
            return buf.getvalue()

        wav1 = make_wav(b"\x01\x00" * 100)
        wav2 = make_wav(b"\x02\x00" * 150)
        merged_wav, ext_w, mime_w = _merge_audio_chunks([wav1, wav2], "audio/wav")
        self.assertEqual(ext_w, "wav")
        self.assertEqual(mime_w, "audio/wav")
        with wave.open(io.BytesIO(merged_wav), "rb") as wf_out:
            self.assertEqual(wf_out.getnframes(), 250)


if __name__ == "__main__":
    unittest.main()
