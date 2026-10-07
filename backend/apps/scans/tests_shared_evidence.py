"""共用聯絡資訊證據（evidence/contacts.py，docs/scan-upgrade-roadmap.md P0-B）。

鎖定：資安的個資檢查與 AEO 的聯絡題用同一套擷取；同一頁上，資安看得到的 Email／電話，
AEO 要嘛判定可回答，要嘛在理由中說明它在哪裡、為什麼正文讀不到——不能只說「找不到」。
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.aeo.evaluate import SitePage, evaluate_site
from apps.scans.evidence import contacts
from apps.scans.scanners import PageAnalysisInput, analyze_data_exposure

_BODY = (
    "<p>本中心開設資料分析與前端課程，由系上教師授課，適合在職人士進修與企業內訓。</p>"
    "<p>課程招生中，報名方式為線上填寫報名表並上傳相關文件，完成後會寄送確認信。</p>"
    "<p>本中心長期與在地企業合作，提供實務專題與實習機會，協助學員把所學應用到工作中。</p>"
    "<p>有任何問題可以聯絡我們，電話與信箱都有專人服務，也歡迎寄送電子郵件詢問。</p>"
)


def _page(url: str, main: str, *, outside: str = "") -> str:
    return f"<html><body>{outside}<main><h1>課程介紹</h1>{_BODY}{main}</main></body></html>"


def _contact_result(pages: list[SitePage], key: str):
    evaluation = evaluate_site(pages)
    return next(r for r in evaluation.results if r.question.key == key)


def _security_emails(url: str, html: str) -> set[str]:
    findings = analyze_data_exposure(
        PageAnalysisInput(url=url, final_url=url, title="", html=html, headers={},
                          element_boxes={})
    )
    text = "\n".join(f["evidence"] for f in findings)
    return {e.lower() for e in contacts.find_emails(text)}


class CollectContactsTests(SimpleTestCase):
    def test_location_context(self):
        html = (
            '<a href="mailto:Info@Site.example">寫信給我們</a>'
            "<p>客服 02-2322-6000 或 service@site.example</p>"
            "<!-- 測試用 dev@site.example -->"
            '<input placeholder="例：0911-222-333">'
        )
        found = {(c.kind, c.normalized): c.location for c in contacts.collect_contacts(
            "https://site.example/", html)}
        self.assertEqual(found[("email", "info@site.example")], contacts.LOCATION_LINK)
        self.assertEqual(found[("email", "service@site.example")], contacts.LOCATION_CONTENT)
        self.assertEqual(found[("email", "dev@site.example")], contacts.LOCATION_COMMENT)
        self.assertEqual(found[("phone", "0223226000")], contacts.LOCATION_CONTENT)
        # placeholder 是填寫範例，不是任何人的資料
        self.assertNotIn(("phone", "0911222333"), found)

    def test_international_and_local_phone_normalize_the_same(self):
        self.assertEqual(
            contacts.normalize_phone("+886 2 2322 6000"), contacts.normalize_phone("02-2322-6000")
        )
        self.assertEqual(contacts.normalize_phone("(02)2322-6000 分機 12"), "0223226000")

    def test_evidence_carries_context_contract(self):
        item = contacts.collect_contacts("https://site.example/a", "<p>a@site.example</p>")[0]
        self.assertEqual(
            item.as_dict(),
            {
                "kind": "email", "value": "a@site.example", "source_url": "https://site.example/a",
                "location": "content", "acquisition": "rendered_dom", "viewport": "desktop",
                "auth_context": "anonymous",
            },
        )


class CrossModuleConsistencyTests(SimpleTestCase):
    """資安看到的 Email，AEO 不能在沒有說明的情況下判「找不到」。"""

    def test_email_in_short_heading_is_answered(self):
        """短標題裡的 Email 被當成標題略過，是 2026-10-06 那類矛盾的另一種形態。"""
        url = "https://center.example/contact"
        html = _page(url, "<h2>聯絡信箱</h2><h3>Email：center@center.example</h3>")
        self.assertIn("center@center.example", _security_emails(url, html))

        result = _contact_result([SitePage(url, html)], "contact_email")

        self.assertEqual(result.verdict, "answered")
        self.assertIn("center@center.example", result.evidence[0].quote)

    def test_email_only_in_nav_is_explained_not_contradicted(self):
        url = "https://center.example/"
        html = _page(
            url,
            "<p>如有任何疑問，歡迎來信洽詢，我們會盡快回覆您的信箱。</p>",
            outside="<nav>首頁 課程 office@center.example</nav>",
        )
        self.assertIn("office@center.example", _security_emails(url, html))

        result = _contact_result([SitePage(url, html)], "contact_email")

        self.assertNotEqual(result.verdict, "answered")
        self.assertIn("網頁原始碼中有 1 筆Email", result.reason)
        self.assertIn("並不矛盾", result.reason)

    def test_phone_written_differently_still_matches(self):
        url = "https://center.example/"
        html = _page(
            url,
            "<h2>聯絡電話</h2><h3>TEL +886-2-2322-6000</h3>",
            outside='<header><a href="tel:0223226000">撥打電話</a></header>',
        )
        result = _contact_result([SitePage(url, html)], "contact_phone")
        self.assertEqual(result.verdict, "answered")

    def test_no_contact_anywhere_keeps_original_verdict(self):
        url = "https://shop.example/"
        html = _page(url, "<p>有任何問題歡迎來電洽詢，也可以寫信到我們的客服信箱。</p>")
        result = _contact_result([SitePage(url, html)], "contact_email")
        # 頁面只說「歡迎寫信」卻沒有地址：維持原判定（資訊不足），不加共用證據的說明
        self.assertEqual(result.verdict, "insufficient")
        self.assertNotIn("網頁原始碼中有", result.reason)

    def test_summary_records_shared_contact_counts_without_values(self):
        url = "https://center.example/contact"
        html = _page(url, "<p>聯絡信箱 a@center.example，電話 02-2322-6000。</p>")
        summary = evaluate_site([SitePage(url, html)]).summary
        self.assertEqual(summary["shared_contacts"], {"email": 1, "phone": 1})
