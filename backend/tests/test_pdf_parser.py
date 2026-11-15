import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "packages"))

from workers.parsers.pdf_parser import PDFParser


class PDFParserOCRImageTypeTests(unittest.TestCase):
    def test_chart_items_with_image_paths_become_image_blocks(self):
        parser = PDFParser()

        blocks, images = parser._parse_content_list_to_blocks(
            [
                {
                    "type": "chart",
                    "img_path": "images/chart-a.jpg",
                    "content": "",
                    "chart_caption": ["Figure 1: Results."],
                    "bbox": [100, 200, 300, 400],
                    "page_idx": 2,
                }
            ],
            {"images/chart-a.jpg": "/tmp/chart-a.jpg"},
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(images), 1)
        self.assertEqual(blocks[0].content, "[Image]")
        self.assertEqual(blocks[0].page, 3)
        self.assertEqual(blocks[0].extra["bbox"], [100, 200, 300, 400])
        self.assertTrue(blocks[0].extra["is_image"])
        self.assertEqual(blocks[0].extra["image_index"], 0)
        self.assertEqual(blocks[0].extra["image_name"], "chart-a.jpg")
        self.assertEqual(blocks[0].extra["image_source_type"], "chart")
        self.assertEqual(blocks[0].extra["image_caption"], "Figure 1: Results.")
        self.assertEqual(images[0]["file_path"], "/tmp/chart-a.jpg")
        self.assertEqual(images[0]["page"], 3)
        self.assertEqual(images[0]["img_name"], "chart-a.jpg")

    def test_tables_with_image_paths_stay_table_blocks(self):
        parser = PDFParser()

        blocks, images = parser._parse_content_list_to_blocks(
            [
                {
                    "type": "table",
                    "img_path": "images/table-a.jpg",
                    "table_body": "<table><tr><td>A</td></tr></table>",
                    "table_caption": ["Table 1"],
                    "bbox": [10, 20, 30, 40],
                    "page_idx": 0,
                }
            ],
            {"images/table-a.jpg": "/tmp/table-a.jpg"},
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(images, [])
        self.assertTrue(blocks[0].extra["is_table"])
        self.assertNotIn("is_image", blocks[0].extra)


class PDFParserOCRMarkdownTests(unittest.TestCase):
    def test_markdown_page_to_content_list_classifies_blocks(self):
        from services.ocr_client import _markdown_page_to_content_list

        md = (
            "# Main Heading\n\n"
            "## Sub Heading\n\n"
            "Regular paragraph text.\n\n"
            "| Col1 | Col2 |\n| --- | --- |\n| A | B |\n\n"
            "$$E = mc^2$$\n\n"
            "```python\nprint('hi')\n```"
        )
        items = _markdown_page_to_content_list(md, page_idx=2)

        self.assertTrue(all(item["page_idx"] == 2 for item in items))

        h1 = next(item for item in items if item.get("text") == "Main Heading")
        self.assertEqual(h1["type"], "text")
        self.assertEqual(h1["text_level"], 1)

        h2 = next(item for item in items if item.get("text") == "Sub Heading")
        self.assertEqual(h2["type"], "text")
        self.assertEqual(h2["text_level"], 2)

        eq = next(item for item in items if item["type"] == "equation")
        self.assertIn("E = mc^2", eq["text"])

        code = next(item for item in items if item["type"] == "code")
        self.assertIn("print('hi')", code["code_body"])
        self.assertEqual(code.get("guess_lang"), "python")

        table_item = next(item for item in items if "| Col1 | Col2 |" in item.get("text", ""))
        self.assertEqual(table_item["type"], "text")

    def test_parse_content_list_to_blocks_preserves_page_and_flags(self):
        from services.ocr_client import _markdown_page_to_content_list

        md = (
            "# Intro\n\n"
            "| Key | Value |\n| --- | --- |\n| k | v |\n\n"
            "$$a^2 + b^2 = c^2$$\n\n"
            "```bash\necho ok\n```"
        )
        content_list = _markdown_page_to_content_list(md, page_idx=4)
        parser = PDFParser()
        blocks, images = parser._parse_content_list_to_blocks(content_list)

        self.assertEqual(images, [])
        self.assertTrue(all(block.page == 5 for block in blocks))

        heading_block = next(b for b in blocks if b.content == "Intro")
        self.assertEqual(heading_block.extra.get("level"), 1)

        table_block = next(b for b in blocks if "| Key | Value |" in b.content)
        self.assertTrue(table_block.extra.get("is_table"))

        formula_block = next(b for b in blocks if "a^2 + b^2 = c^2" in b.content)
        self.assertTrue(formula_block.extra.get("is_formula"))

        code_block = next(b for b in blocks if "echo ok" in b.content)
        self.assertTrue(code_block.extra.get("is_code"))
        self.assertEqual(code_block.extra.get("guess_lang"), "bash")


if __name__ == "__main__":
    unittest.main()
