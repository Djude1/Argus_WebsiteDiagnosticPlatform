"""Argus MCP 工具。

每個工具都走網頁版同一條路徑，不另寫一套規則：
- 建立掃描：ScanJobCreateSerializer（授權聲明、SSRF 檢查、點數預扣、主動測試的網域
  所有權閘門、第三方網域再確認）＋ scans.views.enqueue_created_scan（派工失敗全額退款）
- 取消掃描：scans.tasks.request_scan_cancel（合作式取消＋冪等全額退款）
- 報告：scans.views.ensure_report_file（快取與防偽編號規則相同）
- 只看得到自己的掃描與網域

工具失敗（參數錯、找不到掃描、點數不足…）以 ToolError 回報，協定層會轉成
isError=true 的結果，讓 AI 工具看得到原因。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.urls import reverse

from apps.billing.services import agent_ux_fee, estimate_scan_cost, get_or_create_wallet
from apps.scans.models import ALL_CATEGORIES, Finding, ScanJob, VerifiedDomain
from apps.scans.reports import build_report_number, mask_pii_evidence
from apps.scans.serializers import ScanJobCreateSerializer
from apps.scans.services import (
    assert_public_http_url,
    get_client_ip,
    get_hostname,
    user_owns_domain,
)

REPORT_LINK_SALT = "argus-mcp-report"
IN_PROGRESS = {
    ScanJob.Status.QUEUED,
    ScanJob.Status.CRAWLING,
    ScanJob.Status.SCANNING,
    ScanJob.Status.AGENT_TESTING,
}
_MAX_EVIDENCE = 500


def public_url(request, path: str) -> str:
    """組出給用戶端使用的絕對網址（可由 ARGUS_MCP_PUBLIC_BASE_URL 固定對外網址）。"""
    base = settings.ARGUS_MCP_PUBLIC_BASE_URL
    return f"{base}{path}" if base else request.build_absolute_uri(path)


class ToolError(Exception):
    """工具層可預期的錯誤（訊息會原樣回給 MCP 用戶端）。"""


@dataclass
class ToolContext:
    user: object
    request: object  # Django HttpRequest（建立掃描時記錄授權 IP／User-Agent）
    scan_job: ScanJob | None = None  # 本次呼叫涉及的掃描（寫進呼叫紀錄）


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    input_schema: dict
    handler: Callable[[ToolContext, dict], dict]
    read_only: bool = True
    destructive: bool = False

    def definition(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "idempotentHint": self.read_only,
                "openWorldHint": not self.read_only,
            },
        }


# ---------- 共用 ----------

def _int_arg(args: dict, name: str, default: int, lo: int, hi: int) -> int:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"{name} 必須是整數。")
    if not lo <= value <= hi:
        raise ToolError(f"{name} 必須介於 {lo} 到 {hi}。")
    return value


def _categories_arg(args: dict) -> list[str]:
    raw = args.get("categories") or list(ALL_CATEGORIES)
    if not isinstance(raw, list) or not all(isinstance(c, str) for c in raw):
        raise ToolError("categories 必須是字串陣列。")
    unknown = sorted(set(raw) - set(ALL_CATEGORIES))
    if unknown:
        raise ToolError(
            f"不支援的維度：{', '.join(unknown)}（可用：{', '.join(ALL_CATEGORIES)}）。"
        )
    return [c for c in ALL_CATEGORIES if c in set(raw)]


def _own_scan(ctx: ToolContext, args: dict) -> ScanJob:
    scan_id = args.get("scan_id")
    if isinstance(scan_id, bool) or not isinstance(scan_id, int):
        raise ToolError("scan_id 必須是整數。")
    scan = ScanJob.objects.filter(user=ctx.user, id=scan_id).first()
    if scan is None:
        raise ToolError(f"找不到掃描 #{scan_id}（只能查詢自己的掃描）。")
    ctx.scan_job = scan
    return scan


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def progress_summary(scan: ScanJob) -> dict | None:
    """把 ScanJob.progress 換算成整體百分比（與前端進度條同一算法）。"""
    progress = scan.progress or {}
    if scan.status not in IN_PROGRESS or not progress:
        return None
    steps = progress.get("steps") or []
    step = progress.get("step") or ""
    step_total = progress.get("step_total") or 0
    fraction = min((progress.get("step_done") or 0) / step_total, 1) if step_total else 0
    if steps and step in steps:
        percent = round((steps.index(step) + fraction) / len(steps) * 100)
    else:
        percent = round(
            (progress.get("pages_done") or 0) / max(progress.get("pages_total") or 1, 1) * 100
        )
    return {
        "phase": progress.get("phase"),
        "step": step,
        "steps": steps,
        "step_done": progress.get("step_done"),
        "step_total": step_total,
        "overall_percent": percent,
    }


def _scan_brief(scan: ScanJob) -> dict:
    return {
        "scan_id": scan.id,
        "url": scan.normalized_url,
        "status": scan.status,
        "scan_mode": scan.scan_mode,
        "categories": [c for c in ALL_CATEGORIES if c in scan.effective_categories],
        "max_pages": scan.max_pages,
        "overall_score": scan.overall_score,
        "created_at": _iso(scan.created_at),
        "completed_at": _iso(scan.completed_at),
    }


def _flatten_errors(detail) -> str:
    if isinstance(detail, dict):
        return "；".join(f"{k}: {_flatten_errors(v)}" for k, v in detail.items())
    if isinstance(detail, list):
        return "；".join(_flatten_errors(v) for v in detail)
    return str(detail)


# ---------- 工具實作 ----------

def get_account_status(ctx: ToolContext, args: dict) -> dict:
    from apps.mcp_access.entitlements import get_entitlement

    wallet = get_or_create_wallet(ctx.user)
    ent = get_entitlement(ctx.user)
    return {
        "subscription": {
            "plan": ent.plan_name,
            "status": ent.subscription_status,
            "paid_through": _iso(ent.paid_through),
        },
        "mcp_quota": {
            "monthly_calls": ent.monthly_quota,
            "used_this_month": ent.used_this_month,
            "remaining_this_month": ent.remaining,
            "resets_at": _iso(ent.period_end),
        },
        "coin_balance": wallet.balance,
        "pricing": {
            "coin_per_page_per_category": settings.ARGUS_COIN_PER_CATEGORY,
            "note": "掃描建立時依頁數上限預扣，完成後依實際頁數退差額；失敗或取消全額退回。",
        },
    }


def list_verified_domains(ctx: ToolContext, args: dict) -> dict:
    rows = VerifiedDomain.objects.filter(user=ctx.user).order_by("domain")
    return {
        "domains": [
            {
                "domain": d.domain,
                "status": d.status,
                "effectively_verified": d.is_effectively_verified,
                "method": d.method or None,
                "expires_at": _iso(d.expires_at),
            }
            for d in rows
        ],
        "note": "主動式資安測試只能對 effectively_verified=true 的網域（含其子網域）執行；"
        "被動掃描不需要網域驗證。新增或驗證網域請到 Argus 網站的「網域驗證」頁。",
    }


def estimate_scan(ctx: ToolContext, args: dict) -> dict:
    max_pages = _int_arg(args, "max_pages", settings.ARGUS_DEFAULT_MAX_PAGES, 1,
                         settings.ARGUS_DEFAULT_MAX_PAGES)
    categories = _categories_arg(args)
    cost = estimate_scan_cost(max_pages, categories)
    balance = get_or_create_wallet(ctx.user).balance
    result = {
        "max_pages": max_pages,
        "scope": "single_page" if max_pages == 1 else "site",
        "categories": categories,
        "estimated_max_cost": cost,
        "agent_ux_fee": agent_ux_fee(max_pages, categories),
        "coin_balance": balance,
        "affordable": balance >= cost,
    }
    url = args.get("url")
    if url:
        try:
            normalized = assert_public_http_url(str(url))
        except ValueError as exc:
            raise ToolError(f"網址無法掃描：{exc}") from exc
        result["url"] = normalized
        result["active_mode_allowed"] = user_owns_domain(ctx.user, get_hostname(normalized))
    return result


def create_scan(ctx: ToolContext, args: dict) -> dict:
    from apps.scans.views import enqueue_created_scan

    if args.get("confirm_authorization") is not True:
        raise ToolError(
            "必須設定 confirm_authorization=true，確認你擁有此網站或已取得書面授權。"
        )
    data = {
        "url": args.get("url") or "",
        "authorization_confirmed": True,
        "scan_mode": args.get("scan_mode") or ScanJob.ScanMode.PASSIVE,
        "active_testing_authorized": args.get("scan_mode") == ScanJob.ScanMode.ACTIVE,
        "third_party_reconfirmed": bool(args.get("third_party_reconfirmed")),
        "categories": _categories_arg(args),
        "max_pages": _int_arg(args, "max_pages", settings.ARGUS_DEFAULT_MAX_PAGES, 1,
                              settings.ARGUS_DEFAULT_MAX_PAGES),
        "max_depth": _int_arg(args, "max_depth", settings.ARGUS_DEFAULT_MAX_DEPTH, 1, 10),
        "respect_robots": args.get("respect_robots", True) is not False,
    }
    serializer = ScanJobCreateSerializer(
        data=data,
        context={"request": ctx.request, "client_ip": get_client_ip(ctx.request)},
    )
    if not serializer.is_valid():
        raise ToolError("無法建立掃描：" + _flatten_errors(serializer.errors))
    scan = serializer.save()
    ctx.scan_job = scan
    if not enqueue_created_scan(scan):
        raise ToolError(f"掃描 #{scan.id} 暫時無法啟動，預扣的點數已全額退回，請稍後再試。")
    scan.refresh_from_db()
    return {
        **_scan_brief(scan),
        "held_coins": estimate_scan_cost(scan.max_pages, scan.effective_categories),
        "next": "用 get_scan 追蹤進度；完成後用 get_scan_findings 與 get_scan_report 取得結果。",
    }


def list_scans(ctx: ToolContext, args: dict) -> dict:
    limit = _int_arg(args, "limit", 10, 1, 30)
    qs = ScanJob.objects.filter(user=ctx.user).order_by("-created_at")
    status = args.get("status")
    if status:
        if status not in ScanJob.Status.values:
            raise ToolError(f"status 必須是：{', '.join(ScanJob.Status.values)}。")
        qs = qs.filter(status=status)
    return {"scans": [_scan_brief(s) for s in qs[:limit]]}


def get_scan(ctx: ToolContext, args: dict) -> dict:
    scan = _own_scan(ctx, args)
    result = {
        **_scan_brief(scan),
        "progress": progress_summary(scan),
        "category_scores": scan.category_scores or {},
        "top_actions": (scan.top_actions or [])[:10],
        "findings_count": scan.findings.count(),
        "pages_count": scan.pages.count(),
        "error_message": scan.error_message or None,
        "recent_log": [e.get("msg") for e in (scan.scan_log or [])[-5:]],
    }
    aeo = _aeo_summary(scan)
    if aeo:
        result["aeo"] = aeo
    if scan.status == ScanJob.Status.COMPLETED:
        result["note"] = "category_scores 缺少的維度代表未評估，不是滿分。"
    return result


def _aeo_summary(scan: ScanJob) -> dict | None:
    """AEO 可回答性檢測：逐題判定與第一筆原文證據（個資已遮蔽）。"""
    report = scan.aeo_report or {}
    if not report:
        return None
    if report.get("status") != "evaluated":
        return {"status": report.get("status"), "reason": report.get("reason")}
    questions = []
    for question in report.get("questions") or []:
        evidence = (question.get("evidence") or [])[:1]
        questions.append({
            "question": question.get("text"),
            "verdict": question.get("verdict"),
            "reason": question.get("reason"),
            "evidence": [
                {
                    "url": e.get("url"),
                    "location": e.get("location"),
                    "quote": mask_pii_evidence(e.get("quote") or "")[:200],
                }
                for e in evidence
            ],
        })
    return {
        "status": "evaluated",
        "score": report.get("score"),
        "questions_total": report.get("questions_total"),
        "counts": report.get("counts"),
        "answered_ratio": report.get("answered_ratio"),
        "evidence_ratio": report.get("evidence_ratio"),
        "questions": questions,
    }


_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


def get_scan_findings(ctx: ToolContext, args: dict) -> dict:
    scan = _own_scan(ctx, args)
    limit = _int_arg(args, "limit", 20, 1, 50)
    offset = _int_arg(args, "offset", 0, 0, 10000)
    qs = Finding.objects.filter(scan_job=scan).select_related("page")
    category = args.get("category")
    if category:
        if category not in ALL_CATEGORIES:
            raise ToolError(f"category 必須是：{', '.join(ALL_CATEGORIES)}。")
        qs = qs.filter(category=category)
    severity = args.get("min_severity")
    if severity:
        if severity not in _SEVERITY_ORDER:
            raise ToolError(f"min_severity 必須是：{', '.join(_SEVERITY_ORDER)}。")
        qs = qs.filter(severity__in=_SEVERITY_ORDER[: _SEVERITY_ORDER.index(severity) + 1])
    total = qs.count()
    findings = [
        {
            "id": f.id,
            "severity": f.severity,
            "category": f.category,
            "title": f.title,
            "page_url": (f.page.final_url or f.page.url) if f.page else None,
            "description": f.description,
            "remediation": f.remediation,
            "evidence": mask_pii_evidence(f.evidence or "")[:_MAX_EVIDENCE],
            "rule_id": f.rule_id,
            "source": f.evidence_source or "rule_engine",
        }
        for f in qs[offset: offset + limit]
    ]
    return {
        "scan_id": scan.id,
        "status": scan.status,
        "total": total,
        "offset": offset,
        "findings": findings,
    }


def get_scan_report(ctx: ToolContext, args: dict) -> dict:
    scan = _own_scan(ctx, args)
    if scan.status != ScanJob.Status.COMPLETED:
        raise ToolError(f"掃描 #{scan.id} 狀態為 {scan.status}，完成後才能產生報告。")
    token = signing.TimestampSigner(salt=REPORT_LINK_SALT).sign(f"{scan.id}:{ctx.user.pk}")
    path = reverse("mcp-report-download", kwargs={"token": token})
    return {
        "scan_id": scan.id,
        "report_number": build_report_number(scan),
        "download_url": public_url(ctx.request, path),
        "expires_in_seconds": settings.ARGUS_MCP_REPORT_LINK_TTL,
        "format": "pdf",
        "verify": "收件者可在 Argus 的「報告查驗」頁輸入報告編號核對真偽。",
    }


def cancel_scan(ctx: ToolContext, args: dict) -> dict:
    from apps.scans.tasks import request_scan_cancel

    scan = _own_scan(ctx, args)
    if not request_scan_cancel(scan):
        raise ToolError(f"掃描 #{scan.id} 已結束（{scan.status}），無法終止。")
    return {
        "scan_id": scan.id,
        "status": scan.status,
        "refund": "預扣的點數已全額退回。",
    }


# ---------- 工具清單 ----------

_SCAN_ID = {
    "scan_id": {"type": "integer", "description": "掃描編號（create_scan 或 list_scans 回傳）"}
}
_CATEGORIES = {
    "type": "array",
    "items": {"type": "string", "enum": ALL_CATEGORIES},
    "description": "掃描維度，預設五項全選；費用＝頁數 × 維度數 × 每維單價",
}

TOOLS: tuple[Tool, ...] = (
    Tool(
        "get_account_status", "帳號狀態",
        "查詢訂閱方案、本月 MCP 額度用量與點數餘額。建立掃描前可先確認餘額。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        get_account_status,
    ),
    Tool(
        "list_verified_domains", "已驗證網域",
        "列出帳號已登記的網域與驗證狀態。主動式資安測試只能對已驗證網域執行。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        list_verified_domains,
    ),
    Tool(
        "estimate_scan", "估算掃描費用",
        "估算掃描的點數上限（不連線目標、不扣點）。帶 url 時會一併檢查網址能否掃描、"
        "是否可用主動模式。",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目標網址（選填）"},
                "max_pages": {"type": "integer", "minimum": 1, "description": "頁數上限；1＝單頁"},
                "categories": _CATEGORIES,
            },
            "additionalProperties": False,
        },
        estimate_scan,
    ),
    Tool(
        "create_scan", "建立掃描",
        "建立網站健檢並排入佇列，會依頁數上限預扣點數（完成後退差額，失敗或取消全退）。"
        "只能掃描你擁有或已取得書面授權的網站，必須設定 confirm_authorization=true。"
        "scan_mode=active 需要目標網域已通過驗證。",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目標網址（http/https 公開網站）"},
                "confirm_authorization": {
                    "type": "boolean",
                    "description": "確認你擁有此網站或已取得書面授權（必須為 true）",
                },
                "max_pages": {"type": "integer", "minimum": 1, "description": "頁數上限；1＝單頁"},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 10},
                "categories": _CATEGORIES,
                "scan_mode": {
                    "type": "string", "enum": ["passive", "active"], "default": "passive",
                },
                "third_party_reconfirmed": {
                    "type": "boolean",
                    "description": "目標看起來是大型第三方或敏感產業網站時，需再次確認授權",
                },
                "respect_robots": {"type": "boolean", "default": True},
            },
            "required": ["url", "confirm_authorization"],
            "additionalProperties": False,
        },
        create_scan,
        read_only=False,
    ),
    Tool(
        "list_scans", "掃描列表",
        "列出最近的掃描（新到舊），可依狀態篩選。",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
                "status": {"type": "string", "enum": list(ScanJob.Status.values)},
            },
            "additionalProperties": False,
        },
        list_scans,
    ),
    Tool(
        "get_scan", "掃描狀態與分數",
        "查詢單一掃描的狀態、目前階段與整體進度百分比、各維度分數與優先改善建議。",
        {"type": "object", "properties": _SCAN_ID, "required": ["scan_id"],
         "additionalProperties": False},
        get_scan,
    ),
    Tool(
        "get_scan_findings", "掃描發現",
        "分頁取得掃描發現（嚴重度高的在前），含受影響頁面、證據（已遮蔽個資）與修正建議。",
        {
            "type": "object",
            "properties": {
                **_SCAN_ID,
                "category": {"type": "string", "enum": ALL_CATEGORIES},
                "min_severity": {"type": "string", "enum": _SEVERITY_ORDER,
                                 "description": "只列此嚴重度以上"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": ["scan_id"],
            "additionalProperties": False,
        },
        get_scan_findings,
    ),
    Tool(
        "get_scan_report", "PDF 報告下載連結",
        "取得已完成掃描的 PDF 報告短效下載連結與防偽報告編號。",
        {"type": "object", "properties": _SCAN_ID, "required": ["scan_id"],
         "additionalProperties": False},
        get_scan_report,
    ),
    Tool(
        "cancel_scan", "終止掃描",
        "終止進行中的掃描，預扣點數全額退回。",
        {"type": "object", "properties": _SCAN_ID, "required": ["scan_id"],
         "additionalProperties": False},
        cancel_scan,
        read_only=False,
        destructive=True,
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
