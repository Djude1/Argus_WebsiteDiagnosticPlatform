"""GEO 實體與權威訊號（roadmap §3 GEO 第 1 項，E-E-A-T）。

AI 摘要與知識圖譜要能判斷「這個網站是誰、文章是誰寫的」：
- 組織實體：Organization／LocalBusiness 等標記，附 `sameAs` 連到 Wikidata、維基百科或官方社群帳號，
  讓同一個組織在不同來源被認成同一個實體。
- 文章作者：文章頁（Article／BlogPosting／NewsArticle 標記或 `og:type=article`）要有作者
  （JSON-LD `author`、`<meta name="author">`、`article:author` 或 `rel="author"` 連結）。

- 內容新鮮度（roadmap §3 GEO 第 2 項）：文章的發布／更新日期是否存在、是否合理（更新早於發布、
  未來日期），以及 JSON-LD 與 article:*_time meta 寫的日期是否一致。只檢查日期標記本身，
  不判斷內容「舊不舊」——長青內容不需要常更新。

只讀爬蟲已保存的頁面（rendered_dom 優先），不發任何請求；只看 2xx 且沒被阻擋的頁面。
沒有任何結構化資料的網站已由逐頁的「可補充 JSON-LD」提醒，這裡不重複列「缺少組織實體」。
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit

from apps.scans.models import Finding
from apps.scans.scanners import make_finding
from apps.scans.seo.structured_data import LOCAL_BUSINESS_TYPES

ORGANIZATION_TYPES = {
    "Organization", "Corporation", "NGO", "EducationalOrganization", "CollegeOrUniversity",
    "School", "GovernmentOrganization", "NewsMediaOrganization", "OnlineStore",
    "MedicalOrganization", "SportsOrganization",
} | LOCAL_BUSINESS_TYPES
# 不含 Person：文章的 author 節點就是 Person，算進來會把每位作者都當成網站的組織實體
ARTICLE_TYPES = {
    "Article", "NewsArticle", "BlogPosting", "TechArticle", "Report", "ScholarlyArticle",
}
# 列表頁：WordPress 常把分類、彙整頁也標成 og:type=article（css-tricks、Smashing Magazine 實測）
LISTING_TYPES = {"CollectionPage", "ItemList", "SearchResultsPage"}
# 沒有結構化資料的列表頁：一頁有好幾個 <article> 區塊就是文章列表，不是單篇文章
LISTING_ARTICLE_BLOCKS = 3
# sameAs 指向的來源（主機 → 顯示名稱）；其餘網址仍算 sameAs，只是不另外命名
SAME_AS_SOURCES = {
    "wikidata.org": "Wikidata",
    "wikipedia.org": "維基百科",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "linkedin.com": "LinkedIn",
    "x.com": "X",
    "twitter.com": "X",
    "youtube.com": "YouTube",
    "github.com": "GitHub",
    "threads.net": "Threads",
}
MAX_LISTED = 10
_ISO_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
# 兩個來源的日期差在這個範圍內視為一致（時區造成的跨日不算）
DATE_TOLERANCE = timedelta(days=1)


class _EntityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self.og_type = ""
        self.published_time = False
        self.meta_published = ""
        self.meta_modified = ""
        self.article_blocks = 0
        self.meta_author = False
        self.rel_author = False
        self._in_ld = False
        self._ld_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "article":
            self.article_blocks += 1
        if tag == "script" and attr.get("type", "").lower() == "application/ld+json":
            self._in_ld, self._ld_parts = True, []
        elif tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            content = attr.get("content", "").strip()
            if name == "og:type":
                self.og_type = content.lower()
            elif name in {"author", "article:author"} and content:
                self.meta_author = True
            elif name == "article:published_time" and content:
                self.published_time = True
                self.meta_published = content
            elif name == "article:modified_time" and content:
                self.meta_modified = content
        elif tag in {"a", "link"} and "author" in attr.get("rel", "").lower().split():
            self.rel_author = True

    def handle_data(self, data):
        if self._in_ld:
            self._ld_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self.json_ld.append("".join(self._ld_parts))
            self._in_ld = False


def _type_names(node: dict) -> set[str]:
    raw = node.get("@type") or []
    raw = raw if isinstance(raw, list) else [raw]
    return {str(t).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1] for t in raw if t}


def _nodes(data):
    """所有 JSON-LD 節點（含 @graph 與巢狀物件）。"""
    if isinstance(data, list):
        for item in data:
            yield from _nodes(item)
    elif isinstance(data, dict):
        yield data
        for value in data.values():
            if isinstance(value, (dict, list)):
                yield from _nodes(value)


def _present(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_present(v) for v in value)
    if isinstance(value, dict):
        return bool(value.get("name") or value.get("@id") or value.get("url"))
    return False


def _same_as_urls(node: dict) -> list[str]:
    raw = node.get("sameAs") or []
    raw = raw if isinstance(raw, list) else [raw]
    return [str(u).strip() for u in raw if isinstance(u, str) and u.strip().startswith("http")]


def _source_label(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for domain, label in SAME_AS_SOURCES.items():
        if host == domain or host.endswith("." + domain):
            return label
    return host


def parse_date(value) -> date | None:
    """取日期部分（ISO 8601 與「2026-10-06 10:00:00 +0000 UTC」這類寫法），失敗回 None。"""
    match = _ISO_DATE.search(str(value or ""))
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _usable(page) -> bool:
    status = page.status_code or 0
    return 200 <= status < 300 and not page.blocked_reason


def analyze_entity(pages: list) -> dict:
    """{has_json_ld, organizations: [{name, url, same_as: [{label, url}]}],
    articles, articles_without_author: [網址]}。"""
    summary = {
        "pages": 0, "has_json_ld": False, "organizations": [], "articles": 0,
        "articles_without_author": [], "article_dates": [],
    }
    seen_orgs: set[str] = set()
    for page in pages:
        if not _usable(page):
            continue
        summary["pages"] += 1
        parser = _EntityParser()
        try:
            parser.feed(page.rendered_dom or page.html or "")
            parser.close()
        except Exception:  # noqa: BLE001 — 壞掉的 HTML 不影響其他頁
            continue
        # og:type=article 還要有發布時間、且不像列表頁才算文章頁（單憑 og:type 會把分類頁算進來）；
        # JSON-LD 明確標 Article 的不看 <article> 數量——文章頁常有好幾個「相關文章」區塊
        og_article = (
            parser.og_type == "article" and parser.published_time
            and parser.article_blocks < LISTING_ARTICLE_BLOCKS
        )
        ld_article = False
        ld_published = ld_modified = ""
        is_listing = False
        has_author = parser.meta_author or parser.rel_author
        for block in parser.json_ld:
            try:
                data = json.loads(block)
            except (ValueError, TypeError):
                continue
            summary["has_json_ld"] = True
            for node in _nodes(data):
                types = _type_names(node)
                is_listing = is_listing or bool(types & LISTING_TYPES)
                if types & ARTICLE_TYPES:
                    ld_article = True
                    has_author = has_author or _present(node.get("author"))
                    ld_published = ld_published or str(node.get("datePublished") or "")
                    ld_modified = ld_modified or str(node.get("dateModified") or "")
                if types & ORGANIZATION_TYPES and not types & ARTICLE_TYPES:
                    # 有些網站在 JSON-LD 裡放了 HTML 實體（例如 &#039;）
                    name = html.unescape(str(node.get("name") or "")).strip()
                    key = name.lower() or str(node.get("@id") or node.get("url") or "")
                    if not key or key in seen_orgs:
                        continue
                    seen_orgs.add(key)
                    summary["organizations"].append({
                        "name": name,
                        "url": str(node.get("url") or ""),
                        "same_as": [
                            {"label": _source_label(u), "url": u} for u in _same_as_urls(node)
                        ],
                    })
        if (ld_article or og_article) and not is_listing:
            url = page.final_url or page.url
            summary["articles"] += 1
            if not has_author:
                summary["articles_without_author"].append(url)
            summary["article_dates"].append({
                "url": url,
                "ld_published": ld_published, "ld_modified": ld_modified,
                "meta_published": parser.meta_published, "meta_modified": parser.meta_modified,
            })
    return summary


def entity_findings(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary["pages"] == 0:
        return findings
    organizations = summary["organizations"]
    if summary["has_json_ld"] and not organizations:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.LOW,
            rule_id="geo-entity-organization-missing",
            title="結構化資料沒有說明網站背後的組織",
            description=(
                "網站有結構化資料，但沒有任何頁面標記 Organization、LocalBusiness 等組織實體。"
                "AI 摘要與知識圖譜較難確認「這個網站是誰」，引用時也較難附上正確的品牌名稱。"
            ),
            remediation=(
                "在首頁加入 Organization（或對應的 LocalBusiness 子類型）JSON-LD，"
                "寫明 name、url、logo，並以 sameAs 連到官方社群帳號或 Wikidata 項目。"
            ),
            evidence=f"已檢查 {summary['pages']} 頁，有結構化資料但沒有組織實體",
            impact_area="entity",
            evidence_json={"pages_checked": summary["pages"]},
            priority_score=34,
        ))
    elif organizations and not any(org["same_as"] for org in organizations):
        names = "、".join(org["name"] or "（未命名）" for org in organizations[:3])
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.INFO,
            rule_id="geo-entity-no-same-as",
            title="組織實體沒有連到外部的官方資料",
            description=(
                f"組織標記（{names}）沒有 sameAs。加上 Wikidata、維基百科或官方社群帳號的連結，"
                "能讓搜尋引擎與 AI 確認這些來源說的是同一個組織。"
            ),
            remediation="在組織的 JSON-LD 加上 sameAs 陣列，列出官方社群帳號與 Wikidata 項目網址。",
            evidence=f"組織實體：{names}；sameAs：無",
            impact_area="entity",
            evidence_json={"organizations": organizations[:5]},
        ))
    missing = summary["articles_without_author"]
    if missing:
        listed = "；".join(missing[:MAX_LISTED])
        more = f"…另 {len(missing) - MAX_LISTED} 頁" if len(missing) > MAX_LISTED else ""
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.LOW,
            rule_id="geo-article-author-missing",
            title="文章頁沒有標示作者",
            description=(
                f"{summary['articles']} 個文章頁中有 {len(missing)} 個看不出作者。"
                "作者是判斷內容經驗與可信度（E-E-A-T）的重要線索，AI 引用時也常附上作者。"
            ),
            remediation=(
                "在文章的 JSON-LD 加上 author（Person，含 name 與作者介紹頁 url），"
                "並在頁面上顯示作者名稱與介紹連結。"
            ),
            evidence=f"沒有作者的文章頁：{listed}{more}",
            impact_area="entity",
            evidence_json={"articles": summary["articles"], "without_author": missing[:50]},
            priority_score=33,
        ))
    return findings


def freshness_findings(summary: dict, today: date) -> list[dict]:
    """文章日期：缺少、不合理（更新早於發布、未來日期）、JSON-LD 與 meta 不一致。"""
    missing, invalid, inconsistent = [], [], []
    latest_ok = today + DATE_TOLERANCE
    for item in summary.get("article_dates") or []:
        ld_pub, ld_mod = parse_date(item["ld_published"]), parse_date(item["ld_modified"])
        meta_pub, meta_mod = parse_date(item["meta_published"]), parse_date(item["meta_modified"])
        published, modified = ld_pub or meta_pub, ld_mod or meta_mod
        if not published and not modified:
            missing.append(item["url"])
            continue
        problems = []
        if published and modified and modified + DATE_TOLERANCE < published:
            problems.append(f"更新日期 {modified} 早於發布日期 {published}")
        future = [d for d in (published, modified) if d and d > latest_ok]
        if future:
            problems.append(f"日期 {max(future)} 在未來")
        if problems:
            invalid.append(f"{item['url']}（{'；'.join(problems)}）")
        diffs = [
            f"{label}：JSON-LD {a}、meta {b}"
            for label, a, b in (("發布", ld_pub, meta_pub), ("更新", ld_mod, meta_mod))
            if a and b and abs(a - b) > DATE_TOLERANCE
        ]
        if diffs:
            inconsistent.append(f"{item['url']}（{'；'.join(diffs)}）")

    findings = []
    if missing:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.LOW,
            rule_id="geo-article-date-missing",
            title="文章頁沒有標示發布或更新日期",
            description=(
                f"{len(missing)} 個文章頁的結構化資料與 meta 都沒有日期。讀者與 AI 無法判斷內容"
                "是何時寫的、是否仍然適用，引用時也較難附上時間。"
            ),
            remediation=(
                "在文章的 JSON-LD 加上 datePublished，內容有實質修改時更新 dateModified，"
                "並在頁面上顯示發布與更新日期。"
            ),
            evidence="沒有日期的文章頁：" + _listed(missing),
            impact_area="freshness",
            evidence_json={"urls": missing[:50]},
            priority_score=31,
        ))
    if invalid:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.LOW,
            rule_id="geo-article-date-invalid",
            title="文章日期不合理",
            description=(
                "有文章的更新日期早於發布日期，或日期在未來。搜尋引擎與 AI 會不信任這類日期，"
                "也可能誤判內容的時效。"
            ),
            remediation=(
                "檢查網站產生 datePublished／dateModified 的設定（時區、欄位對調、預約發布）。"
            ),
            evidence=_listed(invalid),
            impact_area="freshness",
            evidence_json={"items": invalid[:50]},
            priority_score=31,
        ))
    if inconsistent:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.LOW,
            rule_id="geo-article-date-inconsistent",
            title="文章的結構化資料與 meta 寫了不同日期",
            description=(
                "同一篇文章的 JSON-LD 與 article:published_time／article:modified_time "
                "日期相差超過一天，搜尋引擎與 AI 不知道該相信哪一個。"
            ),
            remediation="讓 JSON-LD 與 meta 由同一個欄位產生，確保兩邊的發布與更新日期相同。",
            evidence=_listed(inconsistent),
            impact_area="freshness",
            evidence_json={"items": inconsistent[:50]},
            priority_score=30,
        ))
    return findings


def _listed(items: list[str]) -> str:
    more = f"…另 {len(items) - MAX_LISTED} 項" if len(items) > MAX_LISTED else ""
    return "；".join(items[:MAX_LISTED]) + more
