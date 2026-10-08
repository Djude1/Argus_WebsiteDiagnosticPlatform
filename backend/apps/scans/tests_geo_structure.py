"""GEO 可被 AI 摘要性：長篇無小標題、列舉寫成整段（geo_structure.py，roadmap §3 GEO 第 3 項）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.geo_structure import structure_findings

PROSE = "這是一段描述網站服務與課程內容的完整句子，用來模擬文章正文的長度與段落。" * 3


def _paragraphs(count: int) -> str:
    # 每段內容不同：正文擷取會合併重複段落
    return "".join(f"<p>第 {i} 段。{PROSE}</p>" for i in range(count))


def _rules(body: str, head: str = "") -> dict:
    html = f"<html><head>{head}</head><body><main>{body}</main></body></html>"
    return {f["rule_id"]: f for f in structure_findings("https://x.tw/a", html)}


class LongContentTests(SimpleTestCase):
    def test_long_prose_without_subheadings(self):
        rules = _rules("<h1>標題</h1>" + _paragraphs(30))
        finding = rules["geo-long-content-no-subheadings"]
        self.assertEqual(finding["severity"], "low")
        self.assertIn("沒有 h2–h6 小標題", finding["evidence"])

    def test_subheading_anywhere_counts(self):
        # 部落格常把標題放在 <header> 裡，正文擷取會排除它；直接數原始 HTML
        body = '<article><header class="entry-header"><h2>文章</h2></header>'
        body += _paragraphs(30) + "</article>"
        self.assertNotIn("geo-long-content-no-subheadings", _rules(body))

    def test_short_or_link_list_pages_are_not_long_content(self):
        self.assertNotIn("geo-long-content-no-subheadings", _rules(_paragraphs(5)))
        # 入口網站首頁：上百個短連結文字不是長文
        links = "".join(f"<div><a href='/p{i}'>服務項目第{i}項</a></div>" for i in range(400))
        self.assertNotIn("geo-long-content-no-subheadings", _rules(links))

    def test_non_html_documents_are_skipped(self):
        rss = "<?xml version='1.0'?><rss><channel>" + "<item>新聞</item>" * 500 + "</channel></rss>"
        self.assertEqual(structure_findings("https://x.tw/feed/", rss), [])


class EnumerationTests(SimpleTestCase):
    def test_inline_numbered_items(self):
        rules = _rules(
            "<p>本中心業務：1.技術研究及成果擴散 2.辦理企業職業訓練 3.業務協調及基地統合</p>"
        )
        finding = rules["geo-enumeration-not-list"]
        self.assertEqual(finding["severity"], "info")
        self.assertIn("1.技術研究", finding["evidence"])

    def test_other_enumeration_styles(self):
        for text in (
            "主要區塊：1) 上方導覽 2) 右側功能 3) 主要內容",
            "申請須知：(1)填寫表單（2）上傳文件 (3)繳費",
            "辦法如下：第一、報名 第二、審查 第三、公告",
        ):
            self.assertIn("geo-enumeration-not-list", _rules(f"<p>{text}</p>"), text)

    def test_real_lists_versions_and_code_are_not_flagged(self):
        self.assertEqual(_rules("<ol><li>1. 報名</li><li>2. 審查</li><li>3. 公告</li></ol>"), {})
        self.assertEqual(_rules("<p>支援 1.2、2.5 與 3.10 版，以及 Python 3.12。</p>"), {})
        code = (
            "<pre><code>style(--index: 1): a; style(--index: 2): b; "
            "style(--index: 3): c</code></pre>"
        )
        self.assertEqual(_rules(code), {})
        self.assertEqual(_rules("<p>只有兩項：1.報名 2.繳費</p>"), {})
