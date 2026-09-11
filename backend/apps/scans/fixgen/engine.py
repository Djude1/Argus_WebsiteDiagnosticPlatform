"""修正產出產生引擎：prompt → ProviderChain 單次 JSON 產生 → 解析 →
事實政策驗證 → 渲染成可貼上產物。

LLM 只輸出欄位值（不輸出最終 HTML/檔案內容）——逐欄位驗證才有意義，
最終內容由範本確定性渲染，佔位符 injection 也是確定性的。
"""

from __future__ import annotations

import html
import json
import logging
import re
from urllib.parse import urljoin

from django.conf import settings

from apps.agent.providers import ChatProvider, ProviderChain
from apps.scans.fixgen.facts import (
    CrawledFacts,
    PageFacts,
    collect_crawled_facts,
    normalize_for_match,
)
from apps.scans.fixgen.policy import (
    PLACEHOLDER,
    copy_field,
    find_source_url,
    identity_field,
    new_hard_facts,
)
from apps.scans.models import ScanJob

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("json_ld", "og_meta", "llms_txt", "faq_schema")


class FixgenError(Exception):
    """可直接顯示給使用者的產生失敗原因（不含機密）。"""


def generate_artifacts(
    scan_job: ScanJob, chain: ChatProvider | ProviderChain
) -> tuple[dict, dict]:
    """產生四類產物。回傳 (artifacts, meta)；失敗 raise FixgenError。"""
    facts = collect_crawled_facts(scan_job)
    if facts.home is None:
        raise FixgenError("沒有成功爬取的頁面，無法產生修正產出")

    response = chain.chat_text(
        build_prompt(facts),
        model=settings.ARGUS_FIXGEN_MODEL or None,
        temperature=0.2,
        max_tokens=settings.ARGUS_FIXGEN_MAX_TOKENS,
    )
    data = parse_llm_json(response.content)
    artifacts = build_artifacts(facts, data)
    meta = {
        "provider": response.provider,
        "model": response.model,
        "total_tokens": response.total_tokens,
    }
    return artifacts, meta


def build_prompt(facts: CrawledFacts) -> str:
    facts_json = json.dumps(facts.prompt_payload(), ensure_ascii=False, indent=1)
    return (
        "你是網站 SEO/AEO/GEO 修正內容產生器。下方 JSON 是從目標網站爬取到的"
        "全部事實。你只能使用這些事實產生修正內容；網站上沒有的資訊，對應欄位"
        "留空字串或空清單，絕對不可以編造——產生後有驗證步驟，語料中不存在"
        "的值會被佔位符取代。\n\n"
        f"【事實】\n{facts_json}\n\n"
        "【輸出契約】只輸出一個 JSON 物件，不要 markdown 圍欄、不要說明文字：\n"
        "{\n"
        '  "json_ld": {"name": "", "telephone": "", "address": "", "same_as": []},\n'
        '  "og_meta": {"og_description": "", "og_image": ""},\n'
        '  "llms_txt": {"summary": "", "sections": '
        '[{"path": "", "title": "", "description": ""}]},\n'
        '  "faq_schema": {"main_entity": [{"question": "", "answer": ""}]}\n'
        "}\n"
        "規則：\n"
        "- name／telephone／address／same_as 只能取自對應 candidates。\n"
        "- og_description 與 llms_txt.summary 是文案：只能改寫事實中的文字，"
        "不得新增任何數字、統計、獎項、網址或其他事實主張。\n"
        "- og_image 只能從 image_candidates 挑選。\n"
        "- llms_txt.sections[].path 只能使用事實頁面的 URL path，"
        "title／description 只能改寫該頁內容。\n"
        "- faq_schema.main_entity[].question 只能取自 faq_questions"
        "（可微調語氣，不可更換主題）；answer 只能改寫該問答附近的內容。"
        "事實沒有 faq_questions 時，main_entity 留空清單。"
    )


def parse_llm_json(content: str) -> dict:
    text = (content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise FixgenError("LLM 回應中找不到 JSON 內容")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("fixgen: LLM 回應 JSON 解析失敗：%s", exc.__class__.__name__)
        raise FixgenError("LLM 回應不是有效的 JSON") from exc
    if not isinstance(data, dict) or any(key not in data for key in _REQUIRED_KEYS):
        raise FixgenError("LLM 回應缺少必要的輸出欄位")
    return data


def build_artifacts(facts: CrawledFacts, data: dict) -> dict:
    artifacts = {
        "json_ld": _build_json_ld(facts, _as_dict(data.get("json_ld"))),
        "og_meta": _build_og_meta(facts, _as_dict(data.get("og_meta"))),
        "llms_txt": _build_llms_txt(facts, _as_dict(data.get("llms_txt"))),
    }
    faq = _build_faq_schema(facts, _as_dict(data.get("faq_schema")))
    if faq is not None:
        artifacts["faq_schema"] = faq
    return artifacts


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


# ---------- JSON-LD（Organization，全站一份） ----------


def _build_json_ld(facts: CrawledFacts, data: dict) -> dict:
    name, name_ann = identity_field(facts, str(data.get("name", "")), "機構名稱")
    telephone, tel_ann = identity_field(facts, str(data.get("telephone", "")), "電話")
    address, addr_ann = identity_field(facts, str(data.get("address", "")), "地址")

    same_as_raw = [
        str(link).strip() for link in (data.get("same_as") or []) if str(link).strip()
    ]
    same_as_kept = [
        link
        for link in same_as_raw
        if link in facts.urls or link in facts.social_links
    ]
    if not same_as_raw:
        same_as_ann = {"status": "placeholder"}
    elif len(same_as_kept) == len(same_as_raw):
        same_as_ann = {
            "status": "verified",
            "source_url": find_source_url(facts, same_as_kept[0]) if same_as_kept else None,
        }
    elif same_as_kept:
        same_as_ann = {"status": "partial"}
    else:
        same_as_ann = {"status": "placeholder"}

    payload: dict = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": name,
        "url": facts.home.url,
    }
    if telephone:
        payload["telephone"] = telephone
    if address:
        payload["address"] = address
    if same_as_kept:
        payload["sameAs"] = same_as_kept

    content = (
        '<script type="application/ld+json">\n'
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n</script>"
    )
    fields = {
        "name": name_ann,
        "telephone": tel_ann,
        "address": addr_ann,
        "same_as": same_as_ann,
        "url": {"status": "rule"},
        "@type": {"status": "rule"},
    }
    return {"content": content, "fields": fields}


# ---------- Open Graph ＋ meta 描述（首頁／代表頁） ----------


def _build_og_meta(facts: CrawledFacts, data: dict) -> dict:
    home = facts.home
    og_title = home.title or PLACEHOLDER.format(label="頁面標題")
    og_description, desc_ann = copy_field(
        facts, str(data.get("og_description", "")), "網站描述"
    )
    og_site_name = facts.display_name or og_title

    # og:image 是 URL——佔位符字串放進 content 無效，不 grounded 就整個省略標籤
    og_image_raw = str(data.get("og_image", "")).strip()
    if og_image_raw and (
        og_image_raw in facts.image_candidates or og_image_raw in facts.urls
    ):
        og_image = og_image_raw
        image_ann = {"status": "verified", "source_url": home.url}
    else:
        og_image = ""
        image_ann = {"status": "placeholder"}

    # 標題／描述可能含雙引號（如「"限量"優惠」），未跳脫會產出斷裂的
    # meta 標籤——「可直接貼上」是本功能的承諾，輸出必須是合法 HTML。
    esc_title = html.escape(og_title, quote=True)
    esc_description = html.escape(og_description, quote=True)
    esc_site_name = html.escape(og_site_name, quote=True)

    lines = [
        f'<meta property="og:title" content="{esc_title}">',
        f'<meta property="og:description" content="{esc_description}">',
        f'<meta property="og:url" content="{home.url}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{esc_site_name}">',
    ]
    if og_image:
        lines.append(f'<meta property="og:image" content="{html.escape(og_image, quote=True)}">')
        # Twitter Card 有圖給大圖卡；沒圖時仍要輸出 basic card——
        # story 2 承諾的是「完整的 OG＋Twitter Card＋meta 標籤組」，
        # 缺圖不該讓整組 Twitter 標籤跟著消失。
        lines.append('<meta name="twitter:card" content="summary_large_image">')
        lines.append(f'<meta name="twitter:image" content="{html.escape(og_image, quote=True)}">')
    else:
        lines.append('<meta name="twitter:card" content="summary">')
    lines.append(f'<meta name="twitter:title" content="{esc_title}">')
    lines.append(f'<meta name="twitter:description" content="{esc_description}">')
    lines.append(f'<meta name="description" content="{esc_description}">')

    fields = {
        "og_title": {"status": "verified", "source_url": home.url},
        "og_description": desc_ann,
        "og_url": {"status": "rule"},
        "og_type": {"status": "rule"},
        "og_site_name": {"status": "verified", "source_url": home.url},
        "og_image": image_ann,
    }
    return {"content": "\n".join(lines), "fields": fields}


# ---------- llms.txt（主機檔案，下載交付） ----------


def _resolve_page(facts: CrawledFacts, path: str) -> PageFacts | None:
    if not path:
        return None
    absolute = urljoin(facts.home.url, path)
    for page in facts.pages:
        if page.url.rstrip("/") == absolute.rstrip("/"):
            return page
    return None


def _build_llms_txt(facts: CrawledFacts, data: dict) -> dict:
    site_name = facts.display_name or PLACEHOLDER.format(label="網站名稱")
    summary, summary_ann = copy_field(facts, str(data.get("summary", "")), "llms.txt 摘要")

    lines = [f"# {site_name}", f"> {summary}", ""]
    sections_raw = [s for s in (data.get("sections") or []) if isinstance(s, dict)]
    dropped = 0
    for section in sections_raw:
        page = _resolve_page(facts, str(section.get("path", "")))
        if page is None:
            dropped += 1
            continue
        title = str(section.get("title", "")).strip() or page.title
        description = str(section.get("description", "")).strip()
        # 文案新增硬事實 → 丟棄該節（llms.txt 的連結與標題必須完全可信任）
        if new_hard_facts(title, facts) or new_hard_facts(description, facts):
            dropped += 1
            continue
        lines.append(f"- [{title}]({page.url})：{description}")

    if not sections_raw:
        sections_ann = {"status": "placeholder"}
    elif dropped:
        sections_ann = {"status": "partial"}
    else:
        sections_ann = {"status": "verified"}

    fields = {
        "site_name": {"status": "verified", "source_url": facts.home.url},
        "summary": summary_ann,
        "sections": sections_ann,
    }
    return {"content": "\n".join(lines), "fields": fields}


# ---------- FAQPage Schema（僅當站上有 FAQ 依據） ----------


def _extractive_answer(facts: CrawledFacts, question: str) -> str:
    """從問題所在頁面逐字摘錄答案：問題行之後的第一段文字。"""
    normalized = normalize_for_match(question)
    for page in facts.pages:
        for index, line in enumerate(page.lines):
            if normalized and normalized in normalize_for_match(line):
                for followup in page.lines[index + 1 :]:
                    if len(followup) > 10:
                        return followup[:150]
    return ""


def _build_faq_schema(facts: CrawledFacts, data: dict) -> dict | None:
    # 站上無 FAQ 依據 → 不產（即使 LLM 硬給也擋下）
    if not facts.faq_questions:
        return None

    pairs = []
    for item in data.get("main_entity") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not question or not answer:
            continue
        # 問句必須在語料中——憑空出現的問題整組丟棄
        if normalize_for_match(question) not in facts.corpus_norm:
            continue
        if new_hard_facts(answer, facts):
            fallback = _extractive_answer(facts, question)
            if not fallback:
                continue
            answer = fallback
        pairs.append((question, answer))

    if not pairs:
        return None

    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in pairs
        ],
    }
    content = (
        '<script type="application/ld+json">\n'
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n</script>"
    )
    fields = {
        "main_entity": {
            "status": "verified",
            "source_url": find_source_url(facts, pairs[0][0]),
        }
    }
    return {"content": content, "fields": fields}
