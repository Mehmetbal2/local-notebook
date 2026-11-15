import asyncio
import base64
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "packages"))

from services.summary_service import (  # noqa: E402
    _evenly_spaced_indices,
    _extractive_snippet,
    _sample_summaries,
)
from utils.text_decoding import (  # noqa: E402
    decode_bytes,
    looks_like_binary,
    sniff_html_charset,
)
from utils.arabic_text import normalize_arabic_for_embedding  # noqa: E402
from workers.parsers.html_parser import HtmlParser  # noqa: E402
from workers.parsers.txt_parser import TxtParser, _looks_like_tanzil  # noqa: E402


class TextDecodingTests(unittest.TestCase):
    def test_utf16_bom_is_not_decoded_as_cp1256(self):
        text = "مرحبا بالعالم"
        self.assertEqual(decode_bytes(text.encode("utf-16")), text)
        self.assertEqual(decode_bytes(text.encode("utf-16-le")), text)
        self.assertEqual(decode_bytes(text.encode("utf-16-be")), text)

    def test_bomless_utf16(self):
        text = "Arabic text"
        self.assertEqual(decode_bytes(text.encode("utf-16-le")), text)

    def test_cp1256_arabic(self):
        text = "أدب الدنيا والدين"
        self.assertEqual(decode_bytes(text.encode("cp1256")), text)

    def test_utf8_with_bom(self):
        self.assertEqual(decode_bytes("مرحبا".encode("utf-8-sig")), "مرحبا")

    def test_html_charset_sniff(self):
        raw = '<meta charset="windows-1256"><p>مرحبا</p>'.encode("cp1256")
        self.assertEqual(sniff_html_charset(raw), "cp1256")
        self.assertEqual(decode_bytes(raw, sniff_html_charset(raw)), '<meta charset="windows-1256"><p>مرحبا</p>')

    def test_binary_detection(self):
        self.assertTrue(looks_like_binary(b"\x03MSF\x00\x00\x00"))
        self.assertTrue(looks_like_binary(bytes(range(1, 32)) * 4))
        self.assertFalse(looks_like_binary("مرحبا".encode("utf-8")))
        self.assertFalse(looks_like_binary("مرحبا".encode("utf-16")))


class ShamelaHtmlParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="html_parser_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str, encoding: str = "utf-8") -> Path:
        path = self.tmp / name
        path.write_bytes(content.encode(encoding))
        return path

    def test_page_header_is_metadata_not_content(self):
        html = """
        <html><head><title>كتاب تجريبي</title></head><body>
          <div class="PageText">
            <div class="PageHead">
              <span class="PartName">كتاب تجريبي</span>
              <span class="PageNumber">(ص: ١٣)</span>
            </div>
            <span class="title">[مقدمة الكتاب]</span>
            <p>هذا نص الصفحة الأولى.</p>
          </div>
          <div class="PageText">
            <div class="PageHead">
              <span class="PartName">كتاب تجريبي</span>
              <span class="PageNumber">(ص: ١٤)</span>
            </div>
            <p>هذا نص الصفحة الثانية.</p>
          </div>
        </body></html>
        """
        path = self._write("shamela.htm", html)
        result = asyncio.run(HtmlParser().parse(str(path)))

        self.assertNotIn("(ص:", result.text)
        self.assertFalse(any("كتاب تجريبي (ص:" in block.content for block in result.blocks))
        paragraphs = [block for block in result.blocks if block.type == "paragraph"]
        self.assertEqual(paragraphs[0].page, 13)
        self.assertEqual(paragraphs[-1].page, 14)
        self.assertEqual(result.page_count, 14)
        headings = [block.content for block in result.blocks if block.type == "heading"]
        self.assertEqual(headings, ["مقدمة الكتاب"])

    def test_multi_volume_page_locator(self):
        html = """
        <html><body><div class="PageText">
          <div class="PageHead"><span class="PageNumber">(ج2 ص: 7)</span></div>
          <p>المجلد الثاني.</p>
        </div></body></html>
        """
        path = self._write("volume.htm", html)
        result = asyncio.run(HtmlParser().parse(str(path)))
        paragraph = next(block for block in result.blocks if block.type == "paragraph")
        self.assertEqual(paragraph.page, 7)
        self.assertEqual(paragraph.extra, {"volume": 2})

    def test_table_and_data_uri_image_are_preserved(self):
        png = base64.b64encode(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        ).decode("ascii")
        html = f"""
        <html><body>
          <table><caption>جدول</caption>
            <tr><th>أ</th><th>ب</th></tr>
            <tr><td colspan="2">ج</td></tr>
          </table>
          <img src="data:image/png;base64,{png}" alt="صورة">
        </body></html>
        """
        path = self._write("table_image.htm", html)
        result = asyncio.run(HtmlParser().parse(str(path), file_id="file-1"))

        table_block = next(block for block in result.blocks if (block.extra or {}).get("is_table"))
        self.assertTrue(table_block.extra["table_html"].startswith("<table>"))
        self.assertIn("colspan=\"2\"", table_block.extra["table_html"])
        self.assertIn("أ | ب", table_block.content)

        image_block = next(block for block in result.blocks if (block.extra or {}).get("is_image"))
        self.assertEqual(image_block.extra["image_index"], 0)
        self.assertTrue(image_block.extra["image_name"].endswith(".png"))
        self.assertEqual(len(result.images), 1)
        self.assertTrue(Path(result.images[0]["file_path"]).exists())

    def test_valid_html_paragraphs_are_not_nested_by_orphan_normalization(self):
        html = "<html><body><p>one</p><p>two</p><ul><li>a</li><li>b</li></ul></body></html>"
        path = self._write("valid.htm", html)
        result = asyncio.run(HtmlParser().parse(str(path)))
        contents = [block.content for block in result.blocks]
        self.assertEqual(contents, ["one", "two", "a", "b"])


class TxtParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="txt_parser_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tanzil_text(self, count: int = 25) -> str:
        return "\n".join(
            f"1|{ayah}|نص عربي للآية رقم {ayah}"
            for ayah in range(1, count + 1)
        )

    def test_tanzil_detection_positive(self):
        lines = self._tanzil_text().splitlines()
        self.assertTrue(_looks_like_tanzil(lines, "/tmp/quran_test.txt"))

    def test_pipe_delimited_log_is_not_tanzil(self):
        lines = [
            f"1|{index}|Alice|logged in|2024" for index in range(1, 61)
        ]
        self.assertFalse(_looks_like_tanzil(lines, "/tmp/pipe_data.txt"))

        path = self.tmp / "pipe_data.txt"
        path.write_text(
            "id|seq|user|action|year\n" + "\n".join(lines),
            encoding="utf-8",
        )
        result = asyncio.run(TxtParser().parse(str(path)))
        self.assertIn("id|seq|user|action|year", result.text)
        self.assertNotIn("(1:1) Alice", result.text)
        self.assertIn("Alice|logged in|2024", result.text)

    def test_quran_blocks_use_surah_metadata_not_fake_pages(self):
        lines = self._tanzil_text(25)
        lines += "\n" + "\n".join(
            f"2|{ayah}|نص عربي للآية رقم {ayah}"
            for ayah in range(1, 4)
        )
        path = self.tmp / "quran_test.txt"
        path.write_text(lines, encoding="utf-8")
        result = asyncio.run(TxtParser().parse(str(path)))

        self.assertEqual(result.page_count, 0)
        self.assertTrue(all(block.page == 0 for block in result.blocks))
        headings = [block for block in result.blocks if block.type == "heading"]
        self.assertEqual(len(headings), 2)
        self.assertEqual(headings[0].extra["surah"], 1)
        self.assertEqual(headings[0].extra["surah_name"], "الفاتحة")
        body = next(block for block in result.blocks if block.type == "paragraph")
        self.assertEqual(body.extra["surah"], 1)
        self.assertEqual(body.extra["ayah_start"], 1)

    def test_utf16_txt(self):
        path = self.tmp / "arabic.txt"
        path.write_bytes("مرحبا بالعالم\nهذا اختبار".encode("utf-16"))
        result = asyncio.run(TxtParser().parse(str(path)))
        self.assertIn("مرحبا بالعالم", result.text)


class SummarySamplingTests(unittest.TestCase):
    def test_evenly_spaced_indices_include_last(self):
        for total in (1, 2, 21, 39, 40, 41, 200, 201, 2643):
            for count in (1, 5, 20, 32, 64):
                indices = _evenly_spaced_indices(total, count)
                self.assertEqual(len(indices), min(total, count))
                self.assertEqual(indices, sorted(set(indices)))
                if total > 0:
                    self.assertEqual(indices[-1], total - 1)

    def test_extractive_snippet_prefers_sentence_boundary(self):
        content = "First sentence is concise. " + ("x" * 500)
        snippet = _extractive_snippet(content, limit=40)
        self.assertEqual(snippet, "First sentence is concise.")

    def test_sample_summaries_keeps_tail(self):
        summaries = [f"summary-{index}" for index in range(39)]
        sampled = _sample_summaries(summaries, limit=20)
        self.assertEqual(len(sampled), 20)
        self.assertEqual(sampled[-1], "summary-38")


class ArabicSegmentationTests(unittest.TestCase):
    def test_arabic_question_and_semicolon_split(self):
        from services.segment_service import segment_service

        text = "ما هذا؟ هذا اختبار؛ ثم ينتهي۔"
        units = segment_service._split_sentences(text)
        self.assertEqual(
            [unit["text"] for unit in units],
            ["ما هذا؟", " هذا اختبار؛", " ثم ينتهي۔"],
        )

    def test_arabic_embedding_normalization_preserves_non_arabic(self):
        normalized = normalize_arabic_for_embedding("الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ")
        self.assertEqual(normalized, "الحمد لله رب العالمين")
        self.assertEqual(normalize_arabic_for_embedding("hello world"), "hello world")
        self.assertIn("كتاب", normalize_arabic_for_embedding("كِتَاب"))


if __name__ == "__main__":
    unittest.main()
