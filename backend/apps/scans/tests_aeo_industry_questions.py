"""AEO 同業常見問句：付款方式與預約（roadmap §2 第 5 項）。

標註過的案例在 aeo/gold_dataset.py（由 aeo_benchmark 量測）；這裡鎖定真實網站核對時修正的邊界。
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.aeo.evaluate import SitePage, evaluate_site

_INTRO = (
    "<h1>森林選物</h1><p>我們提供台灣在地職人手作的生活器物，包含木作餐具、陶瓷杯盤與植物染布品，"
    "每件商品都附有職人介紹，歡迎加入購物車選購。</p>"
    "<p>本站文字與圖片皆為原創內容，轉載前請先取得同意，並註明出處與原始連結。</p>"
)


def _results(main: str, nav: str = "") -> dict:
    html = f"<html><body>{nav}<main>{_INTRO}{main}</main></body></html>"
    evaluation = evaluate_site([SitePage("https://shop.example/", html)])
    return {r.question.key: r for r in evaluation.results}


class IndustryQuestionTests(SimpleTestCase):
    def test_english_payment_methods_count(self):
        results = _results(
            "<h2>Payment</h2>"
            "<p>Guests pay online by credit card or bank transfer before dining.</p>"
            "<p>付款完成後會寄出確認信，訂單可在會員頁查詢。</p>"
        )
        self.assertEqual(results["payment"].verdict, "answered")
        self.assertEqual(results["payment"].confidence, "confirmed")

    def test_menu_links_do_not_trigger_or_answer(self):
        # 學校網站選單上的「出納付款查詢」「心理諮商線上預約」（2026-10-08 ntub.edu.tw）
        links = "".join(
            f"<p><a href='/{i}'>{text}</a></p>"
            for i, text in enumerate(["出納付款查詢", "心理諮商線上預約", "付款查詢", "場地預約"])
        )
        results = _results(links)
        self.assertNotIn("payment", results)
        self.assertNotIn("booking", results)

    def test_brand_names_are_not_booking_channels(self):
        results = _results(
            "<h2>訂位須知</h2><p>修改訂位人數時，EZTABLE 有權取消此訂單，請先確認後再預訂。</p>"
            "<p>我們的網站使用 inline 樣式排版，訂位相關說明會不定期更新。</p>"
        )
        self.assertEqual(results["booking"].verdict, "insufficient")

    def test_booking_by_line_or_phone(self):
        results = _results(
            "<h2>預約方式</h2><p>請加入 LINE 官方帳號預約，或來電 02-2700-1234 預約到店時段。</p>"
        )
        self.assertEqual(results["booking"].verdict, "answered")
        self.assertEqual(results["booking"].confidence, "likely")
