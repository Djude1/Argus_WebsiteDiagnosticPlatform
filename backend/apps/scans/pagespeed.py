"""Google PageSpeed Insights：Lighthouse 實驗室分數＋CrUX 真實使用者資料（roadmap P1）。

- **Lighthouse（實驗室）**：Google 機房以模擬行動裝置跑一次，四個分數（效能、無障礙、最佳做法、
  SEO）與核心指標（LCP、CLS、TBT、FCP、Speed Index）。單次量測，數值會隨網路與伺服器狀況浮動。
- **CrUX（真實使用者）**：Chrome 使用者過去 28 天的實際體驗（第 75 百分位）。網址本身資料不足時
  改用整個網站（origin）的資料並標示；兩者都沒有就回報「資料不足」與原因，不硬湊數字。

外部指標**不併入 Argus 分數**（roadmap：外部指標保持獨立），只在掃描結果與報告中並列呈現。

只測首頁、只在勾 UX 且有設定 `ARGUS_PAGESPEED_API_KEY` 時執行（沒有金鑰時 Google 的匿名配額
幾乎都被用完）。受測網址會送到 Google 量測；金鑰只放 .env／K8s Secret，不寫 log、不進錯誤訊息。
"""

from __future__ import annotations

import httpx
from django.conf import settings
from django.utils import timezone

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
CATEGORY_LABELS = {
    "performance": "效能",
    "accessibility": "無障礙",
    "best-practices": "最佳做法",
    "seo": "SEO",
}
LAB_METRICS = {
    "largest-contentful-paint": "LCP（最大內容繪製）",
    "cumulative-layout-shift": "CLS（版面位移）",
    "total-blocking-time": "TBT（主執行緒阻塞）",
    "first-contentful-paint": "FCP（首次內容繪製）",
    "speed-index": "Speed Index",
}
FIELD_METRICS = {
    "LARGEST_CONTENTFUL_PAINT_MS": "LCP",
    "INTERACTION_TO_NEXT_PAINT": "INP",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "CLS",
    "FIRST_CONTENTFUL_PAINT_MS": "FCP",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "TTFB",
}
FIELD_CATEGORY_LABELS = {"FAST": "良好", "AVERAGE": "需改善", "SLOW": "不佳"}
MAX_OPPORTUNITIES = 5


class PageSpeedError(Exception):
    """量測失敗；訊息是可對使用者顯示的原因（不含金鑰或回應內文）。"""


def enabled() -> bool:
    return bool(settings.ARGUS_PAGESPEED_ENABLED and settings.ARGUS_PAGESPEED_API_KEY)


def fetch(url: str, *, strategy: str = "mobile") -> dict:
    """呼叫 PSI 並回傳 `parse()` 的結果；失敗丟 PageSpeedError。"""
    params = [("url", url), ("strategy", strategy), ("key", settings.ARGUS_PAGESPEED_API_KEY)]
    params += [("category", category) for category in CATEGORIES]
    try:
        response = httpx.get(
            API_URL, params=params, timeout=settings.ARGUS_PAGESPEED_TIMEOUT_SECONDS
        )
    except httpx.TimeoutException as exc:
        raise PageSpeedError("PageSpeed Insights 逾時") from exc
    except httpx.HTTPError as exc:
        raise PageSpeedError(f"無法連線到 PageSpeed Insights（{exc.__class__.__name__}）") from exc
    if response.status_code == 429:
        raise PageSpeedError("PageSpeed Insights 配額用完")
    if response.status_code >= 400:
        raise PageSpeedError(f"PageSpeed Insights 回應 HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise PageSpeedError("PageSpeed Insights 回應格式錯誤") from exc
    return parse(data, strategy=strategy)


def parse(data: dict, *, strategy: str = "mobile") -> dict:
    """把 PSI 回應整理成 `ScanJob.performance_report` 的格式。"""
    lighthouse = data.get("lighthouseResult") or {}
    runtime_error = (lighthouse.get("runtimeError") or {}).get("code")
    categories = lighthouse.get("categories") or {}
    audits = lighthouse.get("audits") or {}
    lab = {
        "tool": "Lighthouse",
        "version": lighthouse.get("lighthouseVersion", ""),
        "strategy": strategy,
        "fetched_at": lighthouse.get("fetchTime", ""),
        "final_url": lighthouse.get("finalDisplayedUrl") or lighthouse.get("finalUrl", ""),
        "error": runtime_error or "",
        "scores": {
            key: round(categories[key]["score"] * 100)
            for key in CATEGORIES
            if isinstance((categories.get(key) or {}).get("score"), (int, float))
        },
        "metrics": {
            key: {
                "label": label,
                "value": audits[key].get("numericValue"),
                "display": audits[key].get("displayValue", ""),
                "score": audits[key].get("score"),
            }
            for key, label in LAB_METRICS.items()
            if key in audits
        },
        "opportunities": _opportunities(audits),
    }
    return {
        "source": "pagespeed_insights",
        "checked_at": timezone.now().isoformat(),
        "lab": lab,
        "field": _field(data),
    }


def _opportunities(audits: dict) -> list[dict]:
    """效能改善機會（Lighthouse 估計可省下的時間最多的前幾項）。"""
    items = []
    for key, audit in audits.items():
        details = audit.get("details") or {}
        if details.get("type") != "opportunity":
            continue
        score = audit.get("score")
        if score is None or score >= 0.9:
            continue
        items.append({
            "id": key,
            "title": audit.get("title", key),
            "display": audit.get("displayValue", ""),
            "savings_ms": details.get("overallSavingsMs") or 0,
        })
    items.sort(key=lambda item: -item["savings_ms"])
    return items[:MAX_OPPORTUNITIES]


def _field_block(block: dict | None) -> dict | None:
    metrics = (block or {}).get("metrics") or {}
    if not metrics:
        return None
    out = {}
    for key, label in FIELD_METRICS.items():
        metric = metrics.get(key)
        if not metric or metric.get("percentile") is None:
            continue
        value = metric["percentile"]
        # CrUX 的 CLS 以 ×100 的整數回傳（5 代表 0.05）
        if key == "CUMULATIVE_LAYOUT_SHIFT_SCORE":
            value = value / 100
        out[label] = {
            "p75": value,
            "category": metric.get("category", ""),
            "category_label": FIELD_CATEGORY_LABELS.get(metric.get("category", ""), ""),
        }
    return {"overall": (block or {}).get("overall_category", ""), "metrics": out} if out else None


def _field(data: dict) -> dict:
    """CrUX：優先用網址本身的資料，沒有就改用整個網站的資料，兩者都沒有就說明原因。"""
    url_level = data.get("loadingExperience") or {}
    page = None if url_level.get("origin_fallback") else _field_block(url_level)
    if page:
        return {"tool": "CrUX", "period": "過去 28 天", "scope": "url", **page}
    origin = _field_block(data.get("originLoadingExperience"))
    if origin:
        return {"tool": "CrUX", "period": "過去 28 天", "scope": "origin", **origin}
    return {
        "tool": "CrUX",
        "period": "過去 28 天",
        "scope": "none",
        "reason": (
            "Chrome 使用者體驗報告（CrUX）沒有這個網站足夠的真實使用者資料（流量太少或剛上線）"
        ),
    }


def summary_lines(report: dict) -> dict[str, str]:
    """報告範圍表用的兩行文字；沒有資料回空 dict。"""
    if not report:
        return {}
    lines = {}
    lab = report.get("lab") or {}
    if lab.get("scores"):
        scores = "、".join(
            f"{CATEGORY_LABELS[key]} {lab['scores'][key]}"
            for key in CATEGORIES
            if key in lab["scores"]
        )
        lines["Lighthouse（行動版、實驗室單次量測）"] = (
            f"{scores}（Google 量測，不計入 Argus 分數）"
        )
    field = report.get("field") or {}
    if field.get("metrics"):
        scope = "此網址" if field.get("scope") == "url" else "整個網站（此網址資料不足）"
        metrics = "、".join(
            f"{name} {_format_field(name, item['p75'])}（{item['category_label'] or '—'}）"
            for name, item in field["metrics"].items()
        )
        lines["真實使用者體驗（CrUX，過去 28 天）"] = f"{scope}：{metrics}"
    elif field.get("reason"):
        lines["真實使用者體驗（CrUX）"] = field["reason"]
    return lines


def _format_field(name: str, value) -> str:
    if name == "CLS":
        return f"{value:.2f}"
    return f"{value / 1000:.1f} 秒" if value >= 1000 else f"{value} 毫秒"
