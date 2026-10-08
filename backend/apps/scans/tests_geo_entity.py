"""GEO 實體與權威訊號（geo_entity.py，roadmap §3 GEO 第 1 項）。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.scans.geo_entity import analyze_entity, entity_findings


def _page(url, body="", *, ld=None, head="", status=200, blocked=""):
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(node)}</script>' for node in (ld or [])
    )
    html = f"<html><head>{head}{scripts}</head><body>{body}</body></html>"
    return SimpleNamespace(url=url, final_url=url, status_code=status, html=html,
                           rendered_dom="", blocked_reason=blocked)


ORG = {"@type": "Organization", "name": "晨光咖啡", "url": "https://x.tw/",
       "sameAs": ["https://www.facebook.com/x", "https://www.wikidata.org/wiki/Q1"]}
ARTICLE_META = (
    '<meta property="og:type" content="article">'
    '<meta property="article:published_time" content="2026-10-01">'
)


def _rules(pages):
    return {f["rule_id"]: f for f in entity_findings(analyze_entity(pages))}


class EntityTests(SimpleTestCase):
    def test_organization_with_same_as_has_no_finding(self):
        summary = analyze_entity([_page("https://x.tw/", ld=[ORG])])
        self.assertEqual(summary["organizations"][0]["same_as"][1]["label"], "Wikidata")
        self.assertEqual(entity_findings(summary), [])

    def test_json_ld_without_organization(self):
        rules = _rules([_page("https://x.tw/", ld=[{"@type": "WebSite", "name": "x"}])])
        self.assertEqual(rules["geo-entity-organization-missing"]["severity"], "low")

    def test_no_json_ld_at_all_is_left_to_page_level_check(self):
        self.assertEqual(_rules([_page("https://x.tw/", "<p>hi</p>")]), {})

    def test_organization_without_same_as_is_info(self):
        org = {"@type": "CafeOrCoffeeShop", "name": "Ming&#039;s Cafe"}
        summary = analyze_entity([_page("https://x.tw/", ld=[{"@graph": [org]}])])
        self.assertEqual(summary["organizations"][0]["name"], "Ming's Cafe")
        self.assertEqual(entity_findings(summary)[0]["rule_id"], "geo-entity-no-same-as")
        self.assertEqual(entity_findings(summary)[0]["severity"], "info")

    def test_author_person_is_not_an_organization(self):
        article = {"@type": "BlogPosting", "headline": "h",
                   "author": {"@type": "Person", "name": "王小明"}}
        summary = analyze_entity([_page("https://x.tw/a", ld=[article])])
        self.assertEqual(summary["organizations"], [])
        self.assertEqual((summary["articles"], summary["articles_without_author"]), (1, []))


class ArticleAuthorTests(SimpleTestCase):
    def test_article_without_author(self):
        pages = [
            _page("https://x.tw/a", ld=[ORG, {"@type": "Article", "headline": "h"}]),
            _page("https://x.tw/b", head=ARTICLE_META + '<meta name="author" content="王小明">'),
            _page("https://x.tw/c", head=ARTICLE_META, body='<a rel="author" href="/me">我</a>'),
        ]
        finding = _rules(pages)["geo-article-author-missing"]
        self.assertEqual(finding["evidence_json"], {"articles": 3, "without_author": ["https://x.tw/a"]})

    def test_listing_pages_are_not_articles(self):
        blocks = "<article>a</article>" * 4
        pages = [
            # WordPress 分類頁：og:type=article，但 JSON-LD 是 CollectionPage
            _page("https://x.tw/category/news", head=ARTICLE_META,
                  ld=[{"@type": "CollectionPage"}]),
            # 沒有結構化資料的列表頁：好幾個 <article> 區塊
            _page("https://x.tw/articles", blocks, head=ARTICLE_META),
            # 只有 og:type、沒有發布時間
            _page("https://x.tw/about", head='<meta property="og:type" content="article">'),
        ]
        self.assertEqual(analyze_entity(pages)["articles"], 0)

    def test_declared_article_with_related_cards_still_counts(self):
        page = _page("https://x.tw/post", "<article>相關</article>" * 4,
                     ld=[{"@type": "BlogPosting", "headline": "h"}])
        self.assertEqual(analyze_entity([page])["articles_without_author"], ["https://x.tw/post"])

    def test_blocked_and_error_pages_are_skipped(self):
        pages = [
            _page("https://x.tw/a", ld=[{"@type": "Article"}], status=404),
            _page("https://x.tw/b", ld=[{"@type": "Article"}], blocked="waf"),
        ]
        self.assertEqual(analyze_entity(pages)["pages"], 0)
        self.assertEqual(_rules(pages), {})
