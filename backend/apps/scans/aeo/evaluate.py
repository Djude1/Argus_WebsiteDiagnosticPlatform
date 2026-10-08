"""AEO 站台層級評估：把四層串起來，產出逐題結果、指標、分數與 findings。

    正文擷取（原始 HTML 與渲染後各一次）→ 問題集 → 站內段落檢索 → 答案與證據核對

- 分數＝各題判定的加權平均（可回答 1、資訊不足 0.5、內容衝突 0.25、無答案 0），
  核心題（聯絡、期限、價格）權重較高。頁面層級的 AEO 問題（noindex、標記錯誤）再依
  calculate_scores 的一般規則扣分。
- 內容不足以出題時（正文太少或題目不足）狀態為 insufficient：AEO **不評分**，報告顯示
  「未充分評估」與原因，而不是 100 分。
- 指標：「有答案的問題比例」與「答案附有原文的比例」（答案值確實出現在引用段落中）。
- 引用可得性（2026-10-08，roadmap §2 第 6 項）：有答案的題目再看搜尋引擎與 AI 能不能引用——
  頁面 noindex、禁止摘要（nosnippet、max-snippet:0）或答案段落在 data-nosnippet 區塊內＝無法被引用；
  答案只在執行 JavaScript 後才出現＝引用受限（多數 AI 爬蟲不執行 JavaScript）。只是逐題標示與
  比例，不改 AEO 分數、不另產生問題：noindex／nosnippet／data-nosnippet 本身已由
  `page_checks.py` 逐頁列出並扣分，再列一次會重複扣分。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from apps.scans.aeo import answers as a
from apps.scans.aeo.content import (
    blocks_indexing,
    blocks_snippets,
    extract_page_content,
    robots_directives,
)
from apps.scans.aeo.questions import EMAIL, PHONE, build_question_set
from apps.scans.evidence import contacts as shared

METHOD_VERSION = "rules-v1"
MIN_MAIN_TEXT_CHARS = 100  # 中文資訊密度高，100 字已足以出題
MIN_QUESTIONS = 3
# 原始 HTML 正文不到渲染後的這個比例，且渲染後有一定內容 → 主要內容需要 JavaScript
JS_DEPENDENT_RATIO = 0.3
JS_DEPENDENT_MIN_CHARS = 150
MAX_QUESTION_FINDINGS = 12


@dataclass
class SitePage:
    url: str
    html: str  # 瀏覽器渲染後的 DOM
    raw_html: str = ""  # 伺服器原始回應
    blocked: bool = False
    headers: dict = field(default_factory=dict)  # 回應標頭（讀 X-Robots-Tag）


@dataclass
class AeoEvaluation:
    status: str  # "evaluated" | "insufficient"
    reason: str = ""
    score: int | None = None
    results: list[a.QuestionResult] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _render_comparison(pages: list[SitePage], rendered, raw_contents: dict) -> list[dict]:
    rows = []
    for page, content in zip(pages, rendered, strict=True):
        raw = raw_contents.get(page.url)
        if raw is None:
            continue
        rows.append(
            {
                "url": page.url,
                "raw_chars": raw.text_chars,
                "rendered_chars": content.text_chars,
                "js_dependent": (
                    content.text_chars >= JS_DEPENDENT_MIN_CHARS
                    and raw.text_chars < content.text_chars * JS_DEPENDENT_RATIO
                ),
            }
        )
    return rows


# ---------- 引用可得性 ----------

CITABLE = "citable"
LIMITED = "limited"
NOT_CITABLE = "not_citable"
CITATION_LABELS = {CITABLE: "可被引用", LIMITED: "引用受限", NOT_CITABLE: "無法被引用"}


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _citation(result: a.QuestionResult, directives: dict, raw_texts: dict) -> dict | None:
    """有答案的題目能不能被搜尋引擎與 AI 引用；看第一筆證據（判定所依據的段落）。"""
    if not result.evidence:
        return None
    evidence = result.evidence[0]
    found = directives.get(evidence.page_url) or {}
    blocked = []
    if blocks_indexing(found):
        key = "noindex" if "noindex" in found else "none"
        blocked.append(f"頁面設定 {key}（{found[key]}），不會被搜尋引擎與 AI 搜尋收錄")
    elif blocks_snippets(found):
        key = next(
            k for k in found if k in {"nosnippet", "none"} or k.startswith("max-snippet")
        )
        blocked.append(f"頁面禁止擷取摘要（{key}，{found[key]}）")
    if evidence.nosnippet:
        blocked.append("答案所在段落標了 data-nosnippet，不會被拿來當摘要")
    if blocked:
        return {"status": NOT_CITABLE, "label": CITATION_LABELS[NOT_CITABLE], "reasons": blocked}
    raw = raw_texts.get(evidence.page_url)
    needle = _normalize(evidence.value or evidence.quote.strip("…")[:20])
    if raw is not None and needle and needle not in raw:
        return {
            "status": LIMITED,
            "label": CITATION_LABELS[LIMITED],
            "reasons": [
                "答案只在執行 JavaScript 後才出現在頁面上；Google 會執行 JavaScript，"
                "但多數 AI 爬蟲只讀原始 HTML"
            ],
        }
    return {"status": CITABLE, "label": CITATION_LABELS[CITABLE], "reasons": []}


def _citation_summary(citations: list[dict]) -> dict | None:
    if not citations:
        return None
    counts = {key: sum(1 for c in citations if c["status"] == key) for key in CITATION_LABELS}
    return {"counts": counts, "citable_ratio": round(counts[CITABLE] / len(citations), 3)}


def _score(results: list[a.QuestionResult]) -> int:
    total_weight = sum(r.question.weight for r in results) or 1
    earned = sum(r.question.weight * a.VERDICT_VALUE[r.verdict] for r in results)
    return round(100 * earned / total_weight)


def evaluate_site(pages: list[SitePage]) -> AeoEvaluation:
    usable = [p for p in pages if not p.blocked and p.html]
    rendered = [extract_page_content(p.url, p.html) for p in usable]
    raw_contents = {
        p.url: extract_page_content(p.url, p.raw_html) for p in usable if p.raw_html
    }
    main_chars = sum(c.text_chars for c in rendered)
    render_rows = _render_comparison(usable, rendered, raw_contents)
    base_summary = {
        "method": METHOD_VERSION,
        "evaluated_at": timezone.now().isoformat(),
        "pages_analyzed": len(usable),
        "main_text_chars": main_chars,
        "render": {
            "pages_compared": len(render_rows),
            "js_dependent_pages": [r for r in render_rows if r["js_dependent"]][:10],
        },
    }

    if main_chars < MIN_MAIN_TEXT_CHARS:
        reason = (
            f"已掃描頁面的正文合計只有 {main_chars} 字（排除導覽、頁尾與隱藏內容），"
            "不足以建立可檢測的問題；AEO 本次未充分評估。"
        )
        return AeoEvaluation(
            "insufficient",
            reason,
            summary={
                **base_summary,
                "status": "insufficient",
                "reason": reason,
            },
            findings=_render_findings(base_summary),
        )

    questions = build_question_set(rendered)
    if len(questions) < MIN_QUESTIONS:
        reason = (
            f"只能從網站內容建立 {len(questions)} 個問題（至少需要 {MIN_QUESTIONS} 個），"
            "AEO 本次未充分評估。"
        )
        return AeoEvaluation(
            "insufficient",
            reason,
            summary={
                **base_summary,
                "status": "insufficient",
                "reason": reason,
            },
            findings=_render_findings(base_summary),
        )

    passages = [p for c in rendered for p in c.passages]
    # 共用聯絡資訊證據（與資安的個資檢查同一套擷取，P0-B）
    contact_evidence = [c for p in usable for c in shared.collect_contacts(p.url, p.html)]
    results = [
        reconcile_contact(
            a.judge(qn, a.retrieve_candidates(qn, passages), passages), contact_evidence, passages
        )
        for qn in questions
    ]
    counts = {v: sum(1 for r in results if r.verdict == v) for v in a.VERDICT_LABELS}
    answered = [r for r in results if r.verdict == a.ANSWERED]
    score = _score(results)
    directives = {p.url: robots_directives(p.html, p.headers) for p in usable}
    raw_texts = {
        url: _normalize(" ".join(passage.text for passage in content.passages))
        for url, content in raw_contents.items()
    }
    citations = {id(r): _citation(r, directives, raw_texts) for r in answered}
    questions = []
    for r in results:
        row = r.as_dict()
        if citations.get(id(r)):
            row["citation"] = citations[id(r)]
        questions.append(row)
    summary = {
        **base_summary,
        "status": "evaluated",
        "reason": "",
        "questions_total": len(results),
        "counts": counts,
        "answered_ratio": round(len(answered) / len(results), 3),
        "evidence_ratio": (
            round(sum(1 for r in answered if r.value_in_quote) / len(answered), 3)
            if answered
            else None
        ),
        "score": score,
        # 共用證據的筆數（只記數量，不重複存個資）
        "shared_contacts": {
            kind: sum(1 for c in contact_evidence if c.kind == kind)
            for kind in (shared.EMAIL, shared.PHONE)
        },
        "citation": _citation_summary([c for c in citations.values() if c]),
        "questions": questions,
    }
    findings = _question_findings(results) + _render_findings(base_summary)
    return AeoEvaluation("evaluated", "", score, results, findings, summary)


# ---------- 共用聯絡資訊證據 ----------

_CONTACT_KIND = {EMAIL: shared.EMAIL, PHONE: shared.PHONE}
_CONTACT_LABEL = {shared.EMAIL: "Email", shared.PHONE: "電話"}


def _passage_values(kind: str, passage) -> dict[str, str]:
    """段落中的聯絡資訊：正規化值 → 原文寫法。"""
    if kind == shared.EMAIL:
        return {shared.normalize_email(v): v for v in shared.find_emails(passage.text)}
    return {shared.normalize_phone(v): v for v in shared.find_phones(passage.text)}


def reconcile_contact(result: a.QuestionResult, evidence: list, passages: list) -> a.QuestionResult:
    """聯絡題（Email／電話）以共用證據核對，避免和資安檢查互相矛盾。

    - 共用證據中的值出現在任何可讀段落（含被當成標題的短段落）：判定為可回答，附該段原文。
    - 只出現在導覽列、頁首、隱藏區塊、屬性或 HTML 註解：判定不變，但理由寫明它在哪裡、
      為什麼正文讀不到——情境不同不算矛盾，不能只寫「找不到」。
    """
    kind = _CONTACT_KIND.get(result.question.answer_type)
    # 只修正「找不到／資訊不足」；已判可回答或內容衝突（兩頁客服專線不同）的不動
    if kind is None or result.verdict in {a.ANSWERED, a.CONFLICT}:
        return result
    relevant = [c for c in evidence if c.kind == kind]
    if not relevant:
        return result
    wanted = {c.normalized for c in relevant if c.location != shared.LOCATION_COMMENT}
    for passage in passages:
        found = _passage_values(kind, passage)
        hit = next((found[n] for n in found if n in wanted), "")
        if hit:
            return a.QuestionResult(
                result.question,
                a.ANSWERED,
                f"找到具體答案：{hit}",
                [a._evidence(passage, hit)],
                result.candidates_checked,
            )
    places = "、".join(
        sorted({shared.LOCATION_LABELS[c.location] for c in relevant})
    )
    label = _CONTACT_LABEL[kind]
    result.reason = (
        f"{result.reason}（網頁原始碼中有 {len(relevant)} 筆{label}，位置：{places}；"
        f"但不在正文或頁尾的可讀文字裡，例如只出現在導覽列、頁首、隱藏區塊或 HTML 註解，"
        f"訪客與 AI 摘要不一定讀得到。資安檢查列出的{label}與此判定情境不同，並不矛盾。）"
    )
    return result


# ---------- findings ----------

_REMEDIATION = {
    a.MISSING: (
        "在最相關的頁面（例如聯絡、招生、價格頁）用文字直接寫出答案，並從首頁或主選單連到該頁。"
    ),
    a.INSUFFICIENT: (
        "把答案寫成具體、可核對的文字（數字、日期含年度、步驟、金額），"
        "避免只放宣傳語或「詳情請洽」。"
    ),
    a.CONFLICT: "統一各頁的資訊；若是不同梯次或方案，請在同一段落清楚標示適用對象與年度。",
}
_SEVERITY = {a.MISSING: "low", a.INSUFFICIENT: "low", a.CONFLICT: "medium"}


def _question_findings(results: list[a.QuestionResult]) -> list[dict]:
    from apps.scans.models import Finding
    from apps.scans.scanners import make_finding

    problems = [r for r in results if r.verdict != a.ANSWERED]
    problems.sort(key=lambda r: (-r.question.weight, r.verdict))
    findings = []
    for result in problems[:MAX_QUESTION_FINDINGS]:
        severity = _SEVERITY[result.verdict]
        if result.verdict == a.MISSING and result.question.weight >= 1.0:
            severity = "medium"
        label = a.VERDICT_LABELS[result.verdict]
        evidence_lines = [
            f"{e.page_url}｜{e.location}｜「{e.quote}」" for e in result.evidence
        ] or ["（已掃描頁面中沒有相關段落）"]
        findings.append(
            make_finding(
                category=Finding.Category.AEO,
                severity=getattr(Finding.Severity, severity.upper()),
                rule_id=f"aeo-answer-{result.verdict}",
                title=f"問題「{result.question.text}」：{label}",
                description=result.reason,
                remediation=_REMEDIATION[result.verdict],
                evidence=f"問題：{result.question.text}\n" + "\n".join(evidence_lines),
                impact_area="answer_engine",
                priority_score=round(20 + 30 * result.question.weight, 1),
                evidence_json={
                    "question": result.question.as_dict(),
                    "verdict": result.verdict,
                    "evidence": [e.as_dict() for e in result.evidence],
                    "urls": sorted({e.page_url for e in result.evidence}),
                    "assessment": {
                        "condition": f"訪客或 AI 問「{result.question.text}」時，網站文字能直接"
                        "給出答案"
                        + (f"（{result.question.expect}）" if result.question.expect else ""),
                        "observed": result.reason,
                        "missing": "答案所在的明確段落"
                        if result.verdict == a.MISSING
                        else "具體、一致的答案內容",
                        "verify": (
                            "修改後重新掃描，這一題的判定應變為「可回答」，且證據指向修改後的段落。"
                        ),
                    },
                },
            )
        )
    return findings


def _render_findings(summary: dict) -> list[dict]:
    from apps.scans.models import Finding
    from apps.scans.scanners import make_finding

    dependent = summary["render"]["js_dependent_pages"]
    if not dependent:
        return []
    lines = [
        f"{r['url']}｜原始 HTML 正文 {r['raw_chars']} 字、"
        f"執行 JavaScript 後 {r['rendered_chars']} 字"
        for r in dependent
    ]
    return [
        make_finding(
            category=Finding.Category.AEO,
            severity=Finding.Severity.INFO,
            rule_id="aeo-render-dependent",
            title="主要內容需執行 JavaScript 才會出現",
            description=(
                f"有 {len(dependent)} 頁的正文大多在瀏覽器執行 JavaScript 之後才出現。"
                "Google 會執行 "
                "JavaScript，這不代表 Google 看不到；但不執行 JavaScript 的工具（部分 AI 爬蟲、"
                "摘要與"
                "連結預覽服務）只會拿到原始 HTML 的少量文字。"
            ),
            remediation=(
                "重要答案（聯絡方式、價格、期限、流程）建議在伺服器回應的 HTML 中就以文字呈現，例如"
                "採用伺服器端渲染或預先產生頁面。"
            ),
            evidence="\n".join(lines)[:1500],
            impact_area="answer_engine",
            evidence_json={"pages": dependent},
        )
    ]
