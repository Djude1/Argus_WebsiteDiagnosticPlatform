"""從掃描爬到的頁面萃取修正產出所需的事實基礎。

修正產出的核心承諾是「絕不編造」：這裡輸出的一切都來自 crawled HTML 本身，
既是 prompt 的事實來源，也是事實政策驗證的比對語料。爬不到的東西不會
出現在 candidates 裡，LLM 只能從中挑選。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from apps.scans.models import ScanJob
from apps.scans.scanners import detect_faq_structure, parse_html_signals

# prompt 內嵌的頁面摘要上限（字元）；驗證語料不受此限
_PROMPT_MAX_PAGES = 15
_PROMPT_TEXT_PER_PAGE = 1500
# 驗證語料最多涵蓋的頁數
_CORPUS_MAX_PAGES = 30

_MAX_QUESTIONS = 10
_MAX_LINKS = 10
_MAX_CONTACTS = 5

_SOCIAL_HOSTS = (
    "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "youtu.be", "linkedin.com", "line.me", "threads.net", "t.me",
)

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)
_OG_SITE_NAME_RE = re.compile(
    r'<meta\s+property=["\']og:site_name["\']\s+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
# 市話（02-2311-1234）與手機（0912-345-678）兩種形態
_PHONE_RE = re.compile(r"(?<!\d)0\d{1,2}-\d{3,4}-\d{3,4}(?!\d)")
_MOBILE_RE = re.compile(r"(?<!\d)09\d{2}-?\d{3}-?\d{3}(?!\d)")
_TW_CITY_RE = re.compile(r"[臺台][北中南東宜桃竹苗彰投雲嘉屏高花蓮金馬澎][縣市]")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def text_lines(html: str) -> list[str]:
    """HTML → 逐行可見文字（block 標準換行），供逐行擷取問句、地址等。"""
    without = _SCRIPT_STYLE_RE.sub(" ", html or "")
    raw_lines = _TAG_RE.sub("\n", without).split("\n")
    return [re.sub(r"\s+", " ", line).strip() for line in raw_lines]


@dataclass
class PageFacts:
    url: str
    title: str
    lines: list[str]
    html: str


@dataclass
class CrawledFacts:
    pages: list[PageFacts] = field(default_factory=list)
    home: PageFacts | None = None
    urls: set[str] = field(default_factory=set)
    corpus_norm: str = ""
    site_name: str = ""
    og_site_name: str = ""
    meta_description: str = ""
    telephones: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    image_candidates: list[str] = field(default_factory=list)
    faq_questions: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.og_site_name or self.site_name

    def prompt_payload(self) -> dict:
        """餵進 prompt 的事實 JSON（有上限，避免 prompt 爆量）。"""
        home_title = self.home.title if self.home else ""
        return {
            "site_name_candidates": list(
                dict.fromkeys(
                    name for name in (self.og_site_name, self.site_name, home_title) if name
                )
            ),
            "homepage_title": home_title,
            "homepage_meta_description": self.meta_description,
            "telephone_candidates": self.telephones,
            "address_candidates": self.addresses,
            "email_candidates": self.emails,
            "social_link_candidates": self.social_links,
            "image_candidates": self.image_candidates,
            "faq_questions": self.faq_questions,
            "pages": [
                {
                    "url": p.url,
                    "title": p.title,
                    "text_excerpt": " / ".join(p.lines)[:_PROMPT_TEXT_PER_PAGE],
                }
                for p in self.pages[:_PROMPT_MAX_PAGES]
            ],
        }


def collect_crawled_facts(scan_job: ScanJob) -> CrawledFacts:
    pages_qs = (
        scan_job.pages.all()
        .filter(blocked_reason="", status_code=200)
        .exclude(html="")
        .order_by("depth", "url")
    )
    facts = CrawledFacts()
    corpus_parts: list[str] = []
    telephones: list[str] = []
    addresses: list[str] = []
    emails: list[str] = []
    social_links: list[str] = []
    questions: list[str] = []

    for page in pages_qs[:_CORPUS_MAX_PAGES]:
        page_facts = PageFacts(
            url=page.final_url or page.url,
            title=page.title or "",
            lines=text_lines(page.html or ""),
            html=page.html or "",
        )
        facts.pages.append(page_facts)
        facts.urls.add(page.url)
        facts.urls.add(page.final_url)
        corpus_parts.append(page_facts.title)
        corpus_parts.extend(page_facts.lines)
        corpus_parts.append(page_facts.html)

        page_text = " ".join(page_facts.lines)
        telephones.extend(_PHONE_RE.findall(page_text) + _MOBILE_RE.findall(page_text))
        addresses.extend(_address_lines(page_facts.lines))
        emails.extend(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", page_text))
        social_links.extend(_social_hrefs(page_facts.html))
        if len(questions) < _MAX_QUESTIONS and detect_faq_structure(
            page_facts.html, parse_html_signals(page_facts.html).dl_count
        ):
            questions.extend(
                q for q in _question_lines(page_facts.lines) if q not in questions
            )

    facts.home = facts.pages[0] if facts.pages else None
    # 比對用語料：lowercase + 去除所有空白，避免換行／全形差異造成假陰性
    facts.corpus_norm = _normalize(" ".join(corpus_parts))

    if facts.home:
        home = facts.home
        facts.og_site_name = _first_match(_OG_SITE_NAME_RE, home.html)
        facts.site_name = _site_name_from_title(home.title)
        facts.meta_description = parse_html_signals(home.html).meta_description
        facts.image_candidates = _image_candidates(home)

    facts.telephones = list(dict.fromkeys(telephones))[:_MAX_CONTACTS]
    facts.addresses = list(dict.fromkeys(addresses))[:_MAX_CONTACTS]
    facts.emails = list(dict.fromkeys(emails))[:_MAX_CONTACTS]
    facts.social_links = list(dict.fromkeys(social_links))[:_MAX_LINKS]
    facts.faq_questions = questions[:_MAX_QUESTIONS]
    return facts


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", (value or "")).lower()


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text or "")
    return match.group(1).strip() if match else ""


def _site_name_from_title(title: str) -> str:
    """「陽光咖啡 Sunshine Coffee｜手沖咖啡與自製甜點」→「陽光咖啡 Sunshine Coffee」。"""
    for sep in ("｜", "|", "–", "—", "·", " - ", " − "):
        if sep in title:
            return title.split(sep)[0].strip()
    return title.strip()


def _address_lines(lines: list[str]) -> list[str]:
    """含台灣縣市名且出現「…路/街…號」的行，視為地址候選。"""
    found = []
    for line in lines:
        if _TW_CITY_RE.search(line) and re.search(r"(路|街)[\u4e00-\u9fff0-9]{0,12}號", line):
            found.append(line[:80])
    return found


def _social_hrefs(html: str) -> list[str]:
    links = []
    for href in _HREF_RE.findall(html or ""):
        href = href.strip()
        host = href.lower()
        if href.startswith("https://") and any(social in host for social in _SOCIAL_HOSTS):
            links.append(href)
    return links


def _image_candidates(home: PageFacts) -> list[str]:
    candidates = []
    for src in _IMG_SRC_RE.findall(home.html or ""):
        absolute = urljoin(home.url, src.strip())
        if absolute.startswith(("http://", "https://")):
            candidates.append(absolute)
    return list(dict.fromkeys(candidates))[:_MAX_LINKS]


def _question_lines(lines: list[str]) -> list[str]:
    questions = []
    for line in lines:
        for sentence in re.split(r"[。；]", line):
            sentence = sentence.strip()
            if sentence.endswith(("？", "?")) and 4 <= len(sentence) <= 80:
                questions.append(sentence)
    return questions
