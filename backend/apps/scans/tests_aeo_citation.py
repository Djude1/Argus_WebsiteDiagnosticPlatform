"""AEO 引用可得性（aeo/evaluate._citation，roadmap §2 第 6 項）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.aeo.content import extract_page_content
from apps.scans.aeo.evaluate import SitePage, evaluate_site

_INTRO = (
    "<h1>晴光牙醫診所</h1><p>我們提供一般牙科、兒童牙科與植牙矯正服務，"
    "由三位專科醫師看診，並設有無障礙診間與兒童遊戲區，讓全家人都能安心就醫。</p>"
)
_ANSWERS = (
    "<h2>門診資訊</h2>"
    "<p>地址：台北市大安區復興南路一段100號2樓，交通：捷運大安站步行3分鐘。</p>"
    "<p>服務時間：週一至週五 09:00-18:00，週六 09:00-12:00，採預約制。</p>"
)


def _html(main: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body><main>{main}</main></body></html>"


def _citations(page: SitePage) -> tuple[dict, dict]:
    evaluation = evaluate_site([page])
    by_key = {q["key"]: q.get("citation") for q in evaluation.summary["questions"]}
    return by_key, evaluation.summary["citation"]


class NosnippetPassageTests(SimpleTestCase):
    def test_passages_inside_data_nosnippet_are_flagged(self):
        content = extract_page_content("https://a.example/", _html(
            "<p>這一段可以拿來當摘要，內容是一般的服務介紹文字。</p>"
            "<div data-nosnippet><p>這一段不想被摘要，內容是內部說明文字。</p></div>"
            "<p>區塊結束後的這一段又可以當摘要，不應被標記。</p>"
            "<p>行內也可以標：<span data-nosnippet>這幾個字不想被摘要</span>，其餘照常。</p>"
        ))
        flags = [p.nosnippet for p in content.passages]
        # 行內元素結束時段落會切開：span 之後的「，其餘照常。」是另一段、不標記
        self.assertEqual(flags, [False, True, False, True, False])


class CitationTests(SimpleTestCase):
    def test_normal_answers_are_citable(self):
        html = _html(_INTRO + _ANSWERS)
        citations, summary = _citations(SitePage("https://a.example/", html, raw_html=html))
        self.assertEqual(citations["address"]["status"], "citable")
        self.assertEqual(summary["citable_ratio"], 1.0)

    def test_nosnippet_meta_and_header_block_citation(self):
        html = _html(_INTRO + _ANSWERS, head="<meta name='robots' content='nosnippet'>")
        citations, summary = _citations(SitePage("https://a.example/", html))
        self.assertEqual(citations["hours"]["status"], "not_citable")
        self.assertIn("nosnippet，meta robots", citations["hours"]["reasons"][0])
        self.assertEqual(summary["citable_ratio"], 0.0)

        html = _html(_INTRO + _ANSWERS)
        page = SitePage("https://a.example/", html, headers={"X-Robots-Tag": "noindex"})
        citations, _ = _citations(page)
        self.assertIn("noindex（X-Robots-Tag）", citations["address"]["reasons"][0])

    def test_answer_in_data_nosnippet_block_is_not_citable(self):
        html = _html(_INTRO + "<div data-nosnippet>" + _ANSWERS + "</div>")
        citations, _ = _citations(SitePage("https://a.example/", html))
        self.assertEqual(citations["address"]["status"], "not_citable")
        self.assertIn("data-nosnippet", citations["address"]["reasons"][0])

    def test_answer_only_after_javascript_is_limited(self):
        rendered = _html(_INTRO + _ANSWERS)
        raw = _html(_INTRO + "<div id='app'></div>")
        citations, summary = _citations(SitePage("https://a.example/", rendered, raw_html=raw))
        self.assertEqual(citations["hours"]["status"], "limited")
        self.assertIn("JavaScript", citations["hours"]["reasons"][0])
        # 介紹段落在原始 HTML 裡就有，仍可被引用
        self.assertEqual(citations["about"]["status"], "citable")
        self.assertEqual(summary["counts"]["limited"], 2)
        self.assertEqual(summary["citable_ratio"], 0.333)

    def test_unanswered_questions_have_no_citation(self):
        html = _html(_INTRO + _ANSWERS)
        citations, _ = _citations(SitePage("https://a.example/", html))
        self.assertIsNone(citations.get("contact_phone"))
