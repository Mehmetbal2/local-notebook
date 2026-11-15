import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "packages"))

from services import summary_service
from services.workflow_planner import _parse_json_object


class SummaryRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_summary_retries_empty_and_invalid_responses(self):
        calls = []
        responses = [
            "",
            "not json",
            '{"summary": "Recovered summary", "keywords": ["Agentic Engineering"]}',
        ]

        async def fake_llm_complete(*args, **kwargs):
            calls.append(args[0])
            return responses.pop(0)

        original_llm_complete = summary_service._llm_complete
        original_retry_delay = summary_service.SUMMARY_RETRY_BASE_DELAY
        summary_service._llm_complete = fake_llm_complete
        summary_service.SUMMARY_RETRY_BASE_DELAY = 0
        try:
            result = await summary_service.generate_file_summary(
                "notes.pdf",
                ["Segment summary one.", "Segment summary two."],
                "api-key",
                "https://example.test",
                "model",
            )
        finally:
            summary_service._llm_complete = original_llm_complete
            summary_service.SUMMARY_RETRY_BASE_DELAY = original_retry_delay

        self.assertEqual(result["summary"], "Recovered summary")
        self.assertEqual(result["keywords"], ["Agentic Engineering"])
        self.assertEqual(len(calls), 3)
        self.assertIn("Previous response was invalid", calls[1])


class PlannerParsingTests(unittest.TestCase):
    def test_parse_fenced_json_with_unescaped_inner_quotes(self):
        raw = '''```json
{"steps": [{"step_id": "three_alignments", "step_name": "核心框架", "instruction": "说明为什么这三条线是成为"五倍十倍工程师"的前提。"}, {"step_id": "harness", "step_name": "Harness 编排层", "instruction": "解释 Harness 作为模型上层编排工具的角色（即"harness engine"）。"}]}
```'''

        parsed = _parse_json_object(raw, preferred_keys=("steps",))

        self.assertEqual(len(parsed["steps"]), 2)
        self.assertIn('"五倍十倍工程师"', parsed["steps"][0]["instruction"])
        self.assertIn('"harness engine"', parsed["steps"][1]["instruction"])


class QuickToolFeatureTests(unittest.TestCase):
    def test_feature_display_name_supports_tr_en_and_zh(self):
        from routes.feature_routes import feature_display_name

        expected = {
            "content_summary": ("İçerik özeti", "Content summary", "内容摘要"),
            "timeline": ("Zaman çizelgesi", "Timeline", "时间线"),
            "mind_map": ("Zihin haritası", "Mind map", "思维导图"),
            "flashcards": ("Bilgi kartları", "Flashcards", "闪卡"),
            "quiz": ("Sınav", "Quiz", "测验"),
        }
        for feature_type, (tr_label, en_label, zh_label) in expected.items():
            self.assertEqual(feature_display_name(feature_type, "Turkish"), tr_label)
            self.assertEqual(feature_display_name(feature_type, "English"), en_label)
            self.assertEqual(feature_display_name(feature_type, "Chinese"), zh_label)

    def test_standalone_feature_instructions_are_distinct(self):
        from workers.tasks import _standalone_feature_instruction

        feature_types = [
            "content_summary",
            "timeline",
            "mind_map",
            "flashcards",
            "quiz",
        ]
        instructions = [
            _standalone_feature_instruction(ft, "", "Turkish")
            for ft in feature_types
        ]
        self.assertEqual(len(set(instructions)), len(feature_types))
        self.assertTrue(all("Turkish" in instr for instr in instructions))

    def test_markdown_to_blocks_syncs_table_citations_as_well_as_lists_and_paragraphs(self):
        from agent.blocks_builder import markdown_to_blocks

        citation_map = {
            "citation_1": {"segment_id": "seg-1", "summary": "First"},
            "citation_2": {"segment_id": "seg-2", "summary": "Second"},
            "citation_3": {"segment_id": "seg-3", "summary": "Third"},
        }
        md = (
            "Intro sentence [citation_1].\n\n"
            "- List point [citation_2]\n\n"
            "| Stage | Evidence |\n"
            "| --- | --- |\n"
            "| Step 1 | Detail [citation_3] |"
        )
        blocks, next_num = markdown_to_blocks(md, citation_map, start_display_num=1)

        self.assertEqual(next_num, 4)
        self.assertEqual(citation_map["citation_1"]["display_num"], 1)
        self.assertEqual(citation_map["citation_2"]["display_num"], 2)
        self.assertEqual(citation_map["citation_3"]["display_num"], 3)

        table_block = next(b for b in blocks if b.get("extra", {}).get("is_table"))
        citation_parts = [p for p in table_block["content_parts"] if p["type"] == "citation_ref"]
        self.assertEqual(len(citation_parts), 1)
        self.assertEqual(citation_parts[0]["citation_id"], "citation_3")
        self.assertEqual(citation_parts[0]["display_num"], 3)


if __name__ == "__main__":
    unittest.main()
