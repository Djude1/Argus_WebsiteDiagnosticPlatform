"""billing 業務邏輯：所有 CoinWallet 異動的唯一入口。

任何外部模組要動 wallet.balance 或建立 CoinTransaction，都應走這裡的函式，
以維持「異動必有交易紀錄、balance_after 必同步」的不變式。
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.models import CoinTransaction, CoinWallet, PricingPlan


class InsufficientCoinError(Exception):
    """錢包餘額不足以執行該扣款。"""

    def __init__(self, *, required: int, balance: int) -> None:
        self.required = required
        self.balance = balance
        super().__init__(f"coin 不足：需要 {required}，目前 {balance}")


def get_or_create_wallet(user) -> CoinWallet:
    wallet, _ = CoinWallet.objects.get_or_create(user=user)
    return wallet


@transaction.atomic
def grant_monthly_bonus_if_needed(user) -> CoinTransaction | None:
    """若本月尚未發放贈點，發放一次並回傳交易；已發過則回 None。

    冪等：以 wallet.last_bonus_year/month 判斷。被 Google 登入流程在每次登入時呼叫。
    """
    bonus = settings.ARGUS_MONTHLY_BONUS_COINS
    if bonus <= 0:
        return None
    wallet = CoinWallet.objects.select_for_update().get_or_create(user=user)[0]
    now = timezone.now()
    if wallet.last_bonus_year == now.year and wallet.last_bonus_month == now.month:
        return None
    new_balance = wallet.balance + bonus
    wallet.balance = new_balance
    wallet.last_bonus_year = now.year
    wallet.last_bonus_month = now.month
    wallet.save(update_fields=[
        "balance", "last_bonus_year", "last_bonus_month", "updated_at",
    ])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=bonus,
        kind=CoinTransaction.Kind.MONTHLY_BONUS,
        balance_after=new_balance,
        note=f"每月贈點 {now.year}-{now.month:02d}",
    )


def estimate_scan_cost(max_pages: int) -> int:
    """掃描預估點數：max_pages × 每頁單價。"""
    return int(max_pages) * settings.ARGUS_COIN_PER_PAGE


@transaction.atomic
def hold_for_scan(user, scan_job) -> CoinTransaction:
    """建立掃描時先預扣 max_pages × coin_per_page。

    呼叫者已驗證餘額足夠（serializer.validate），這裡再加一層 row-level lock
    確保並發建立時不會超扣。若不足會 raise InsufficientCoinError。
    """
    cost = estimate_scan_cost(scan_job.max_pages)
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    if wallet.balance < cost:
        raise InsufficientCoinError(required=cost, balance=wallet.balance)
    new_balance = wallet.balance - cost
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=-cost,
        kind=CoinTransaction.Kind.SCAN_HOLD,
        balance_after=new_balance,
        scan_job=scan_job,
        note=f"建立掃描預扣（max_pages={scan_job.max_pages}）",
    )


def _sum_holds(wallet: CoinWallet, scan_job_id: int) -> int:
    """該 scan 在錢包內的累積淨扣款（負數絕對值）。"""
    rows = CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job_id=scan_job_id,
        kind__in=[
            CoinTransaction.Kind.SCAN_HOLD,
            CoinTransaction.Kind.SCAN_REFUND,
        ],
    ).values_list("amount", flat=True)
    return -sum(rows)  # holds 是負、refunds 是正 → 淨扣 = -sum


@transaction.atomic
def refund_full_for_scan(user, scan_job, *, reason: str) -> CoinTransaction | None:
    """掃描失敗或被取消：把該 scan 的剩餘預扣全額退回。

    冪等：若已退完（淨扣為 0）則回 None。
    """
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    outstanding = _sum_holds(wallet, scan_job.id)
    if outstanding <= 0:
        return None
    new_balance = wallet.balance + outstanding
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=outstanding,
        kind=CoinTransaction.Kind.SCAN_REFUND,
        balance_after=new_balance,
        scan_job=scan_job,
        note=f"掃描{reason}全額退款",
    )


@transaction.atomic
def settle_scan_actual(user, scan_job, actual_pages: int) -> CoinTransaction | None:
    """掃描完成：依實際頁數退差額（max_pages - actual_pages）× coin_per_page。

    同時將 wallet.total_scans_used 累計 +1。冪等：若已結算（淨扣等於實際成本）則
    只更新 total_scans_used、不再退款。
    """
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    actual_cost = max(0, int(actual_pages)) * settings.ARGUS_COIN_PER_PAGE
    outstanding = _sum_holds(wallet, scan_job.id)
    refund_amount = max(0, outstanding - actual_cost)

    # 統計：完成一次掃描，total_scans_used +1（即使 0 refund 也要計數）
    wallet.total_scans_used = (wallet.total_scans_used or 0) + 1

    if refund_amount <= 0:
        wallet.save(update_fields=["total_scans_used", "updated_at"])
        return None

    new_balance = wallet.balance + refund_amount
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "total_scans_used", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=refund_amount,
        kind=CoinTransaction.Kind.SCAN_REFUND,
        balance_after=new_balance,
        scan_job=scan_job,
        note=f"實際 {actual_pages} 頁，退回未使用的 {refund_amount} coin",
    )


@transaction.atomic
def purchase_plan(user, plan: PricingPlan) -> CoinTransaction:
    """模擬付款：直接把方案 coin 加進錢包，並更新累積購買金額。"""
    wallet = CoinWallet.objects.select_for_update().get_or_create(user=user)[0]
    new_balance = wallet.balance + plan.coin_amount
    wallet.balance = new_balance
    wallet.total_purchased_ntd = (wallet.total_purchased_ntd or 0) + plan.price_ntd
    wallet.save(update_fields=[
        "balance", "total_purchased_ntd", "updated_at",
    ])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=plan.coin_amount,
        kind=CoinTransaction.Kind.PURCHASE,
        balance_after=new_balance,
        plan=plan,
        note=f"購買 {plan.name}（NT${plan.price_ntd}）",
    )


@transaction.atomic
def admin_adjust(*, target_user, delta: int, admin_actor, note: str) -> CoinTransaction:
    """管理員手動加/減 coin（含退費）。

    `delta` 可正可負；負數時若超過餘額會被夾到 0（避免負餘額）。
    同時寫一筆 AdminAuditLog 供 superuser 查核。
    """
    if delta == 0:
        raise ValueError("delta 不可為 0")
    wallet = CoinWallet.objects.select_for_update().get_or_create(user=target_user)[0]
    new_balance = max(0, wallet.balance + delta)
    actual_delta = new_balance - wallet.balance
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    tx = CoinTransaction.objects.create(
        wallet=wallet,
        amount=actual_delta,
        kind=CoinTransaction.Kind.ADMIN_ADJUST,
        balance_after=new_balance,
        admin_actor=admin_actor,
        note=note,
    )
    # 寫入 admin 操作 audit log（延後 import 避免 circular）
    from apps.admin_api.models import AdminAuditLog, log_admin_action
    log_admin_action(
        admin_actor=admin_actor,
        action=AdminAuditLog.Action.COIN_ADJUST,
        target_user=target_user,
        target_repr=f"{target_user.username} wallet→{new_balance}",
        payload={
            "delta_requested": delta,
            "delta_actual": actual_delta,
            "balance_after": new_balance,
            "note": note,
            "transaction_id": tx.id,
        },
    )
    return tx
