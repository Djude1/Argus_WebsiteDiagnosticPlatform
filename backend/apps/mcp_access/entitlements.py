"""MCP 權益：誰可以用、本月可以呼叫幾次。

權益在**每一次**請求都重新判定（不是只在建立憑證時）：訂閱到期、帳號停用或憑證撤銷，
下一次呼叫就會被拒絕。

- 有效訂閱：先跑 lazy 結算（settle_subscription_safe），再看 status 為生效中或已取消、
  且目前仍在已付費期間內（now < current_period_end）。已取消的訂閱保留到當期結束。
- 本月額度：依方案代碼查 ARGUS_MCP_PLAN_QUOTAS，查無則用 ARGUS_MCP_DEFAULT_MONTHLY_CALLS；
  只計 tools/call（initialize、tools/list 不計），以台北時間的月份為期。
- 每分鐘上限：同一使用者 ARGUS_MCP_RATE_PER_MINUTE 次，防止失控的迴圈把額度一次燒光。

掃描本身的費用照舊走點數（建立時預扣、完成退差額、失敗／取消全退），MCP 額度只管呼叫次數。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.billing.models import UserSubscription
from apps.billing.services import settle_subscription_safe
from apps.mcp_access.models import McpCallLog


@dataclass
class Entitlement:
    allowed: bool
    reason: str
    plan_code: str = ""
    plan_name: str = ""
    subscription_status: str = ""
    paid_through: datetime | None = None
    monthly_quota: int = 0
    used_this_month: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None

    @property
    def remaining(self) -> int:
        return max(self.monthly_quota - self.used_this_month, 0)

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "plan_code": self.plan_code,
            "plan_name": self.plan_name,
            "subscription_status": self.subscription_status,
            "paid_through": self.paid_through.isoformat() if self.paid_through else None,
            "monthly_quota": self.monthly_quota,
            "used_this_month": self.used_this_month,
            "remaining_this_month": self.remaining,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


def current_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    """本月額度的期間（台北時間當月 1 日 00:00 起，到下月 1 日 00:00 止）。"""
    local = timezone.localtime(now or timezone.now())
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def monthly_quota_for(plan_code: str) -> int:
    default = settings.ARGUS_MCP_DEFAULT_MONTHLY_CALLS
    return int(settings.ARGUS_MCP_PLAN_QUOTAS.get(plan_code, default))


def usage_in_period(user, start: datetime, end: datetime) -> int:
    return McpCallLog.objects.filter(
        user=user, counted=True, created_at__gte=start, created_at__lt=end
    ).count()


def get_entitlement(user) -> Entitlement:
    start, end = current_period()
    if not getattr(user, "is_active", False):
        return Entitlement(False, "帳號已停用。", period_start=start, period_end=end)
    settle_subscription_safe(user)
    sub = UserSubscription.objects.select_related("plan").filter(user=user).first()
    if sub is None:
        return Entitlement(
            False, "MCP 接入限有效訂閱會員使用，請先到購點頁訂閱方案。",
            period_start=start, period_end=end,
        )
    base = dict(
        plan_code=sub.plan.code,
        plan_name=sub.plan.name,
        subscription_status=sub.status,
        paid_through=sub.current_period_end,
        monthly_quota=monthly_quota_for(sub.plan.code),
        used_this_month=usage_in_period(user, start, end),
        period_start=start,
        period_end=end,
    )
    in_paid_period = timezone.now() < sub.current_period_end
    if sub.status not in (UserSubscription.Status.ACTIVE, UserSubscription.Status.CANCELLED):
        return Entitlement(False, "訂閱已到期，續訂後即可繼續使用 MCP。", **base)
    if not in_paid_period:
        return Entitlement(False, "訂閱已到期，續訂後即可繼續使用 MCP。", **base)
    return Entitlement(True, "", **base)


# 所有請求（含 initialize、tools/list）的每分鐘上限＝工具呼叫上限 × 此倍數
REQUEST_LIMIT_MULTIPLIER = 4


def hit_rate_limit(user, *, scope: str = "call") -> bool:
    """每位使用者每分鐘的上限；超過回 True。

    scope="call"：tools/call（ARGUS_MCP_RATE_PER_MINUTE）；
    scope="request"：任何請求（上限 × REQUEST_LIMIT_MULTIPLIER），避免反覆 initialize 灌爆紀錄。
    """
    limit = int(settings.ARGUS_MCP_RATE_PER_MINUTE)
    if limit <= 0:
        return False
    if scope == "request":
        limit *= REQUEST_LIMIT_MULTIPLIER
    bucket = timezone.now().strftime("%Y%m%d%H%M")
    key = f"mcp-rate:{scope}:{user.pk}:{bucket}"
    added = cache.add(key, 1, timeout=70)
    if added:
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=70)
        return False
    return count > limit
