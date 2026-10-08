"""AEO 答案可信度（確認／可能／推測，roadmap §2 AEO 第 4 項）。"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.scans.aeo import answers as a
from apps.scans.aeo.benchmark import run_benchmark
from apps.scans.aeo.content import Passage
from apps.scans.aeo.questions import INTENTS, Question
from apps.scans.reports import _aeo_items


def _question(key: str, source: str = "intent", answer_type: str = "") -> Question:
    intent = next((i for i in INTENTS if i.key == key), None)
    return Question(
        key=key, text=intent.question if intent else key,
        answer_type=answer_type or intent.answer_type,
        keywords=intent.keywords if intent else (key,), weight=1.0, source=source,
    )


def _result(question, verdict, value="", quote="") -> a.QuestionResult:
    text = quote or value
    evidence = [a.Evidence("https://x.tw/", "段落", text, value)] if text else []
    return a.QuestionResult(question, verdict, "理由", evidence)


class ConfidenceTests(SimpleTestCase):
    def test_exact_value_in_quote_is_confirmed(self):
        result = _result(
            _question("contact_phone"), a.ANSWERED, "02-2771-1234", "電話 02-2771-1234"
        )
        self.assertEqual(result.confidence, a.CONFIRMED)
        data = result.as_dict()
        self.assertEqual((data["confidence"], data["confidence_label"]), ("confirmed", "確認"))
        self.assertIn("逐字出現", data["limitation"])

    def test_steps_criteria_and_site_questions_are_likely(self):
        self.assertEqual(_result(_question("apply_how"), a.ANSWERED, "填寫").confidence, a.LIKELY)
        site = _question("site_1", source="site", answer_type="freeform")
        self.assertEqual(_result(site, a.ANSWERED, "我們提供").confidence, a.LIKELY)

    def test_definition_is_only_possible(self):
        self.assertEqual(_result(_question("about"), a.ANSWERED, "我們提供").confidence, a.POSSIBLE)

    def test_no_confidence_without_an_answer(self):
        result = _result(_question("contact_phone"), a.MISSING)
        self.assertEqual(result.confidence, "")
        self.assertIsNone(result.as_dict()["confidence"])
        self.assertIsNone(result.as_dict()["limitation"])

    def test_conflict_with_quoted_values_is_confirmed(self):
        passages = [
            Passage("https://x.tw/a", 0, "營業時間：週一至週五 09:00-18:00。"),
            Passage("https://x.tw/b", 0, "營業時間：週一至週五 10:00-19:00。"),
        ]
        result = a.judge(_question("hours"), passages, passages)
        self.assertEqual((result.verdict, result.confidence), (a.CONFLICT, a.CONFIRMED))


class ConfidenceBenchmarkTests(SimpleTestCase):
    def test_confirmed_answers_stay_precise(self):
        """確認等級的答案若出錯，網站主會以為這題已解決：precision 必須維持 ≥ 0.95。"""
        hit, total = run_benchmark().precision_by_confidence().get(a.CONFIRMED, (0, 0))
        self.assertGreater(total, 0)
        self.assertGreaterEqual(hit / total, 0.95)


class ReportTests(SimpleTestCase):
    def test_report_appends_confidence_to_verdict(self):
        scan = SimpleNamespace(aeo_report={"status": "evaluated", "questions": [
            {"text": "聯絡電話是多少？", "verdict": "answered", "verdict_label": "可回答",
             "confidence_label": "確認", "evidence": [
                 {"url": "https://x.tw/", "location": "頁尾", "quote": "電話 02-2771-1234"}]},
            {"text": "退款規定？", "verdict": "missing", "verdict_label": "無可用答案",
             "reason": "找不到", "evidence": []},
        ]})
        items = _aeo_items(scan)
        self.assertEqual([i["verdict"] for i in items], ["可回答（確認）", "無可用答案"])
