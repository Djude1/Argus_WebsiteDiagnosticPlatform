"""結構化資料的 Google 複合式搜尋結果必填欄位（seo/structured_data.py，roadmap §1 SEO 第 2 項）。"""

from __future__ import annotations

import json

from django.test import SimpleTestCase

from apps.scans.scanners import PageAnalysisInput, analyze_seo, parse_html_signals
from apps.scans.seo.structured_data import validate_blocks


def _v(*nodes) -> dict:
    return validate_blocks([json.dumps(n) for n in nodes])


def _missing(result) -> list[tuple[str, list[str]]]:
    return [(i["type"], i["missing"]) for i in result["issues"]]


class RequiredFieldsTests(SimpleTestCase):
    def test_complete_product_passes(self):
        result = _v({
            "@context": "https://schema.org", "@type": "Product", "name": "手沖壺",
            "offers": {"@type": "Offer", "price": "1200", "priceCurrency": "TWD"},
        })
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["checked"], ["產品"])

    def test_product_needs_one_of_review_rating_offers(self):
        result = _v({"@type": "Product", "name": "手沖壺"})
        self.assertEqual(
            _missing(result), [("產品", ["review／aggregateRating／offers（其中之一）"])]
        )

    def test_offer_price_and_price_specification(self):
        missing = _v({"@type": "Product", "name": "A", "offers": {"@type": "Offer"}})
        self.assertEqual(
            _missing(missing), [("產品優惠", ["price／priceSpecification.price（其中之一）"])]
        )
        ok = _v({"@type": "Product", "name": "A",
                 "offers": [{"priceSpecification": {"price": 10}}]})
        self.assertEqual(ok["issues"], [])
        aggregate = _v({"@type": "Product", "name": "A",
                        "offers": {"@type": "AggregateOffer", "lowPrice": 10}})
        self.assertEqual(_missing(aggregate), [("產品優惠", ["priceCurrency"])])

    def test_nested_rating_and_review(self):
        result = _v({
            "@type": "Product", "name": "A",
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4.5},
            "review": {"@type": "Review", "reviewRating": {"ratingValue": 5}},
        })
        self.assertEqual(sorted(_missing(result)), [
            ("評分彙總", ["ratingCount／reviewCount（其中之一）"]),
            ("評論", ["author"]),
        ])

    def test_event_location_needs_address_unless_virtual(self):
        result = _v({"@type": "MusicEvent", "name": "演唱會", "startDate": "2026-12-01T19:00",
                     "location": {"@type": "Place", "name": "台北小巨蛋"}})
        self.assertEqual(_missing(result), [("活動地點", ["address"])])
        online = _v({"@type": "Event", "name": "線上講座", "startDate": "2026-12-01",
                     "location": {"@type": "VirtualLocation", "url": "https://x.test"}})
        self.assertEqual(online["issues"], [])

    def test_local_business_subtype_and_schema_url_type(self):
        result = _v({"@type": "https://schema.org/CafeOrCoffeeShop", "name": "咖啡館"})
        self.assertEqual(_missing(result), [("在地商家", ["address"])])

    def test_job_posting_location_alternatives(self):
        result = _v({"@type": "JobPosting", "title": "工程師", "datePosted": "2026-10-01",
                     "description": "<p>職務</p>", "hiringOrganization": {"name": "公司"},
                     "jobLocationType": "TELECOMMUTE"})
        self.assertEqual(result["issues"], [])

    def test_software_app_requires_offer_price_and_rating(self):
        result = _v({"@type": ["WebApplication"], "name": "App"})
        self.assertEqual(_missing(result), [("軟體應用程式", [
            "offers.price", "aggregateRating／review（其中之一）",
        ])])

    def test_breadcrumb_items(self):
        result = _v({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首頁", "item": "https://x.test/"},
            {"@type": "ListItem", "position": 2, "item": {"@id": "https://x.test/a", "name": "A"}},
            {"@type": "ListItem", "name": "目前頁面"},
        ]})
        # 第 2 項 item 帶 name 可省略 name；最後一項可省略 item，但 position 必填
        self.assertEqual(
            [(i["item"], i["missing"]) for i in result["issues"]],
            [("導覽路徑 第 3 項", ["position"])],
        )

    def test_graph_nodes_checked_once(self):
        result = _v({"@context": "https://schema.org", "@graph": [
            {"@type": "Organization", "@id": "#org", "name": "Argus"},
            {"@type": "Product", "name": "A",
             "aggregateRating": {"ratingValue": 4, "reviewCount": 3}},
            {"@type": "Recipe", "name": "滷肉飯"},
        ]})
        self.assertEqual(_missing(result), [("食譜", ["image"])])

    def test_no_rules_for_article_organization_and_faq(self):
        result = _v(
            {"@type": "Article"},
            {"@type": "Organization"},
            {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "Q"}]},
        )
        self.assertEqual(result["issues"], [])

    def test_nested_product_reference_not_checked(self):
        result = _v({"@type": "Offer", "price": 1,
                     "itemOffered": {"@type": "Product", "name": "A"}})
        self.assertEqual(result["issues"], [])

    def test_empty_values_count_as_missing_and_syntax_errors_are_skipped(self):
        result = validate_blocks([
            "{not json", json.dumps({"@type": "VideoObject", "name": "片", "thumbnailUrl": [],
                                     "uploadDate": " "}),
        ])
        self.assertEqual(_missing(result), [("影片", ["thumbnailUrl", "uploadDate"])])

    def test_self_serving_reviews(self):
        result = _v({"@type": "Dentist", "name": "牙醫", "address": "台北市",
                     "aggregateRating": {"ratingValue": 5, "reviewCount": 20}})
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["self_serving"], ["牙醫"])


class SeoFindingTests(SimpleTestCase):
    def _findings(self, *nodes):
        scripts = "".join(
            f'<script type="application/ld+json">{json.dumps(n)}</script>' for n in nodes
        )
        html = f"<html><head><title>t</title>{scripts}</head><body><h1>h</h1></body></html>"
        page = PageAnalysisInput(url="https://x.test/p", final_url="https://x.test/p", title="t",
                                 html=html, headers={}, element_boxes={})
        return {f["rule_id"]: f for f in analyze_seo(page, parse_html_signals(html))}

    def test_missing_required_fields_become_low_finding(self):
        findings = self._findings({"@type": "Product", "name": "手沖壺"})
        finding = findings["seo-structured-data-required"]
        self.assertEqual(finding["severity"], "low")
        self.assertIn("產品「手沖壺」缺少：review／aggregateRating／offers", finding["evidence"])
        self.assertEqual(finding["evidence_json"]["url"], "https://x.test/p")

    def test_complete_or_absent_markup_has_no_finding(self):
        self.assertNotIn("seo-structured-data-required", self._findings())
        complete = self._findings({"@type": "Recipe", "name": "滷肉飯", "image": "a.jpg"})
        self.assertNotIn("seo-structured-data-required", complete)

    def test_self_serving_reviews_are_info(self):
        findings = self._findings({"@type": "Organization", "name": "Argus",
                                   "review": {"author": "A", "reviewRating": {"ratingValue": 5}}})
        self.assertEqual(findings["seo-structured-data-self-serving-reviews"]["severity"], "info")
