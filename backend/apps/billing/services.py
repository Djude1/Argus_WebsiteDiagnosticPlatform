"""billing 業務邏輯：所有 CoinWallet 異動的唯一入口。

任何外部模組要動 wallet.balance 或建立 CoinTransaction，都應走這裡的函式，
以維持「異動必有交易紀錄、balance_after 必同步」的不變式。
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    CoinTransaction,
    CoinWallet,
    PricingPlan,
    PurchaseOrder,
    SubscriptionCharge,
    SubscriptionOrder,
    SubscriptionPlan,
    UserSubscription,
)

logger = logging.getLogger(__name__)


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
    cap = settings.ARGUS_FREE_BONUS_BALANCE_CAP
    if cap > 0 and not has_paid_history(user):
        # 從未購點、從未訂閱：月贈點只補到上限，避免閒置帳號無限累積點數負債（2026-10-07）
        bonus = min(bonus, max(0, cap - wallet.balance))
    if bonus <= 0:
        # 已達上限：仍標記本月已處理，避免每次登入重算
        wallet.last_bonus_year = now.year
        wallet.last_bonus_month = now.month
        wallet.save(update_fields=["last_bonus_year", "last_bonus_month", "updated_at"])
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


def agent_ux_fee(max_pages: int, categories=None) -> int:
    """AI Agent 擬真使用者 UX 測試的固定附加費（0 表示這次不收）。

    只有在「agent 功能開啟 + 全網站掃描（max_pages > 1）+ 勾選 UX 維度」時計收。
    這三個條件與 scan_plan.run_agent_ux 一致，且都能從 estimate_scan_cost 現有的
    兩個參數推得，因此 hold（用 max_pages）與 settle（用實際頁數）會自動對稱：
    只爬到 1 頁的掃描 settle 時 max_pages 傳實際頁數＝1 → 不收費 → 這筆自動退回。
    """
    from apps.scans.models import ALL_CATEGORIES

    if not settings.ARGUS_AGENT_ENABLED:
        return 0
    if int(max_pages) <= 1:
        return 0
    selected = {c for c in (categories or []) if c in ALL_CATEGORIES} or set(ALL_CATEGORIES)
    if "ux" not in selected:
        return 0
    return settings.ARGUS_COIN_AGENT_UX


def agent_deep_fee(max_pages: int, *, active_authorized: bool) -> int:
    """深度資安 Hermes-Agent 的固定附加費（0 表示這次不收）。

    條件與 scan_plan.run_agent 一致：agent 功能開啟＋主動模式且已授權＋全網站。
    預扣時依條件先算進去；結算時只有 agent 真的以深度模式執行才收（見 settle_scan_actual）。
    """
    if not settings.ARGUS_AGENT_ENABLED or not active_authorized or int(max_pages) <= 1:
        return 0
    return settings.ARGUS_COIN_AGENT_DEEP


def estimate_scan_cost(max_pages: int, categories=None, *, deep_agent: bool = False) -> int:
    """掃描預估點數：max_pages × 勾選維度數 × 每維單價，另加 Agent 附加費。

    categories 為 None（內部舊呼叫）或空集合時視同五維全選，
    與導入維度計費前的「max_pages × ARGUS_COIN_PER_PAGE」等價。
    deep_agent=True 時另加深度資安附加費（呼叫端負責判斷是否符合條件）。
    """
    # 延遲 import：ALL_CATEGORIES 的事實來源在 scans.models，頂層 import 會循環
    from apps.scans.models import ALL_CATEGORIES

    selected = {c for c in (categories or []) if c in ALL_CATEGORIES} or set(ALL_CATEGORIES)
    page_cost = int(max_pages) * len(selected) * settings.ARGUS_COIN_PER_CATEGORY
    deep_fee = agent_deep_fee(max_pages, active_authorized=True) if deep_agent else 0
    return page_cost + agent_ux_fee(max_pages, categories) + deep_fee


def _scan_is_deep(scan_job) -> bool:
    """這筆掃描符合深度資安 Agent 的執行條件（主動＋已授權）。"""
    from apps.scans.models import ScanJob

    return (
        scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
        and bool(scan_job.active_testing_authorized)
    )


def scan_hold_amount(scan_job) -> int:
    """建立掃描時實際要預扣的點數（免費首掃為 0）。網頁與 MCP 共用。"""
    if scan_job.is_trial:
        return 0
    return estimate_scan_cost(
        scan_job.max_pages,
        scan_job.effective_categories,
        deep_agent=_scan_is_deep(scan_job),
    )


def qualifies_for_free_trial(max_pages: int, categories, scan_mode: str) -> bool:
    """是否為 Standard Full Scan：被動＋整站＋五面向全選。"""
    from apps.scans.models import ALL_CATEGORIES, ScanJob

    return (
        settings.ARGUS_FREE_TRIAL_SCAN_ENABLED
        and int(max_pages) > 1
        and scan_mode == ScanJob.ScanMode.PASSIVE
        and set(categories or []) >= set(ALL_CATEGORIES)
    )


def free_trial_available(user, *, exclude_scan_id: int | None = None) -> bool:
    """這個帳號還能不能使用首次免費完整掃描。

    已用掉＝有一筆免費掃描不是失敗或取消（進行中與已完成都算）；失敗或取消的免費掃描
    不算用掉，讓使用者可以再試一次。
    """
    if not settings.ARGUS_FREE_TRIAL_SCAN_ENABLED or not user or not user.pk:
        return False
    from apps.scans.models import ScanJob

    used = ScanJob.objects.filter(user=user, is_trial=True).exclude(
        status__in=[ScanJob.Status.FAILED, ScanJob.Status.CANCELLED]
    )
    if exclude_scan_id is not None:
        used = used.exclude(id=exclude_scan_id)
    return not used.exists()


def affordable_site_pages(balance: int, categories, *, deep_agent: bool, max_pages: int) -> int:
    """餘額不足時，同一組設定下最多付得起幾頁的整站掃描（至少 2 頁才有意義，否則回 0）。

    Partial Scan 用：前端讓使用者確認「掃 N 頁」，不自動縮小範圍。
    """
    best = 0
    for pages in range(2, int(max_pages)):
        if estimate_scan_cost(pages, categories, deep_agent=deep_agent) <= balance:
            best = pages
        else:
            break
    return best


def has_paid_history(user) -> bool:
    """是否購點或訂閱過（月贈點上限只套用在從未付費的帳號）。"""
    wallet = CoinWallet.objects.filter(user=user).first()
    if wallet is not None and (wallet.total_purchased_ntd or 0) > 0:
        return True
    return UserSubscription.objects.filter(user=user).exists()


@transaction.atomic
def hold_for_scan(user, scan_job) -> CoinTransaction:
    """建立掃描時先預扣 max_pages × 勾選維度數 × 每維單價。

    呼叫者已驗證餘額足夠（serializer.validate），這裡再加一層 row-level lock
    確保並發建立時不會超扣。若不足會 raise InsufficientCoinError。
    """
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    if scan_job.is_trial and not free_trial_available(user, exclude_scan_id=scan_job.id):
        # 同時送出兩筆免費掃描：錢包鎖住後再確認一次，第二筆改為一般付費掃描
        type(scan_job).objects.filter(id=scan_job.id).update(is_trial=False)
        scan_job.is_trial = False
    cost = scan_hold_amount(scan_job)
    if scan_job.is_trial:
        return CoinTransaction.objects.create(
            wallet=wallet,
            amount=0,
            kind=CoinTransaction.Kind.SCAN_HOLD,
            balance_after=wallet.balance,
            scan_job=scan_job,
            note="首次免費完整掃描（不扣點）",
        )
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
        note=(
            f"建立掃描預扣（max_pages={scan_job.max_pages}，"
            f"{len(scan_job.effective_categories)} 維度）"
        ),
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


def estimate_rebuild_hold() -> int:
    """建立複刻時要預扣的點數上限。

    這是**預授權額度不是價格**：最終只收實際用量（settle_rebuild_actual），
    差額退回。預扣存在的理由是餘額不足的人不能先把 agent 的錢花掉。
    """
    return settings.ARGUS_COIN_REBUILD_HOLD


def rebuild_coins_for_usd(cost_usd) -> int:
    """把 agent 回報的實際花費（USD）換算成點數。

    無條件進位：不足一點的用量仍要收一點，否則大量極小的呼叫會完全免費。
    再套最低消費——agent 用免費模型時 USD 成本是 0，但 Argus 自己的 worker
    與儲存成本不會因此消失。
    """
    exact = Decimal(str(cost_usd or 0)) * settings.ARGUS_COIN_PER_USD
    return max(
        settings.ARGUS_COIN_REBUILD_MIN,
        int(exact.to_integral_value(rounding=ROUND_CEILING)),
    )


@transaction.atomic
def hold_for_rebuild(user, site_rebuild) -> CoinTransaction:
    """建立複刻任務時預扣。

    先扣再跑，不是跑完才扣：優化那段會呼叫外部 agent 花真錢，餘額不足的人
    必須在花錢之前就被擋下來。失敗時由 refund_rebuild 退回。
    """
    cost = estimate_rebuild_hold()
    get_or_create_wallet(user)
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    if wallet.balance < cost:
        raise InsufficientCoinError(required=cost, balance=wallet.balance)
    new_balance = wallet.balance - cost
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=-cost,
        kind=CoinTransaction.Kind.REBUILD_HOLD,
        balance_after=new_balance,
        scan_job=site_rebuild.scan_job,
        site_rebuild=site_rebuild,
        note=f"網頁複刻預扣上限（page={site_rebuild.page_id}）",
    )


@transaction.atomic
def settle_rebuild_actual(user, site_rebuild) -> CoinTransaction | None:
    """複刻成功：依 agent 回報的實際花費結算，退回沒用到的預扣。

    與 settle_scan_actual 同一套模式。實收金額**上限是預扣額**：實際用量
    超過預扣時只收預扣額，不追扣——追扣等於在使用者沒同意、也沒再檢查餘額
    的情況下二次扣款，可能把餘額扣成負數。

    冪等：已經有這次複刻的 REBUILD_REFUND 交易就代表結算過了，直接跳過。
    """
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    if CoinTransaction.objects.filter(
        wallet=wallet,
        site_rebuild=site_rebuild,
        kind=CoinTransaction.Kind.REBUILD_REFUND,
    ).exists():
        return None

    held = _sum_rebuild_holds(wallet, site_rebuild.id)
    actual = min(held, rebuild_coins_for_usd(site_rebuild.cost_usd))
    refund_amount = max(0, held - actual)

    if refund_amount <= 0:
        # 0 元標記交易當冪等信號：實際用滿預扣時也要留下「已結算」的痕跡
        return CoinTransaction.objects.create(
            wallet=wallet,
            amount=0,
            kind=CoinTransaction.Kind.REBUILD_REFUND,
            balance_after=wallet.balance,
            scan_job=site_rebuild.scan_job,
            site_rebuild=site_rebuild,
            note=f"實際用量 {actual} coin，無退款差額",
        )

    new_balance = wallet.balance + refund_amount
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=refund_amount,
        kind=CoinTransaction.Kind.REBUILD_REFUND,
        balance_after=new_balance,
        scan_job=site_rebuild.scan_job,
        site_rebuild=site_rebuild,
        note=f"實際用量 {actual} coin，退回未使用的 {refund_amount} coin",
    )


def _sum_rebuild_holds(wallet: CoinWallet, site_rebuild_id: int) -> int:
    """該次複刻在錢包內的累積淨扣款。

    刻意用 site_rebuild 而非 scan_job 當條件：一次掃描可以產生多次複刻，
    用 scan_job 篩會把同一掃描其他複刻的預扣一起算進來，退款就會超退。
    """
    rows = CoinTransaction.objects.filter(
        wallet=wallet,
        site_rebuild_id=site_rebuild_id,
        kind__in=[
            CoinTransaction.Kind.REBUILD_HOLD,
            CoinTransaction.Kind.REBUILD_REFUND,
        ],
    ).values_list("amount", flat=True)
    return -sum(rows)


@transaction.atomic
def charge_rebuild_usage(user, site_rebuild, cost_usd) -> CoinTransaction | None:
    """追問等後續回合的事後扣款：直接按實際用量收，沒有預扣也沒有退款。

    不能沿用 settle_rebuild_actual：那個以「這次複刻只結算一次」為前提（有
    REBUILD_REFUND 就跳過），第二輪會被冪等邏輯整個略過——追問等於免費，
    但它花的是真錢。

    扣款上限是當前餘額：CoinWallet.balance 是 PositiveBigIntegerField，
    扣成負數會直接拋資料庫錯誤。view 層已先擋掉餘額不足的人，這裡是最後一道。
    """
    coins = rebuild_coins_for_usd(cost_usd)
    if coins <= 0:
        return None
    get_or_create_wallet(user)
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    charged = min(coins, wallet.balance)
    if charged <= 0:
        return None
    new_balance = wallet.balance - charged
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=-charged,
        kind=CoinTransaction.Kind.REBUILD_HOLD,
        balance_after=new_balance,
        scan_job=site_rebuild.scan_job,
        site_rebuild=site_rebuild,
        note=f"網頁複刻追問，實際用量 {coins} coin",
    )


@transaction.atomic
def refund_rebuild(user, site_rebuild, *, reason: str) -> CoinTransaction | None:
    """複刻失敗：把該次複刻的預扣退回。

    冪等：已退完（淨扣為 0）回 None。使用者只拿到不花錢的原樣快照時也算失敗，
    照樣要退——那一段本來就不該收費。

    用 get_or_create_wallet 而非直接 get：退款是在失敗路徑上呼叫的，這裡再
    因為「錢包不存在」拋一次例外，只會把原本的失敗原因蓋掉、更難查。
    """
    get_or_create_wallet(user)
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    outstanding = _sum_rebuild_holds(wallet, site_rebuild.id)
    if outstanding <= 0:
        return None
    new_balance = wallet.balance + outstanding
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=outstanding,
        kind=CoinTransaction.Kind.REBUILD_REFUND,
        balance_after=new_balance,
        scan_job=site_rebuild.scan_job,
        site_rebuild=site_rebuild,
        note=f"網頁複刻{reason}退款",
    )


@transaction.atomic
def settle_scan_actual(
    user, scan_job, actual_pages: int, *, deep_agent_ran: bool = False
) -> CoinTransaction | None:
    """掃描完成：依實際頁數 × 勾選維度數退還差額。

    deep_agent_ran：深度資安 Agent 是否真的執行過；沒執行就不收深度附加費（預扣的退回）。
    免費首掃（is_trial）應收為 0。

    同時將 wallet.total_scans_used 累計 +1。
    冪等：若已存在此 scan 的 SCAN_REFUND 交易（本函式的差額退款、無退款標記、
    或 refund_full_for_scan 的全退），代表已結算，整段跳過（含 total_scans_used）。
    """
    wallet = CoinWallet.objects.select_for_update().get(user=user)

    # 冪等前置檢查：已有此 scan 的 SCAN_REFUND 交易 → 已結算，避免 total_scans_used 重複累加
    if CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job=scan_job,
        kind=CoinTransaction.Kind.SCAN_REFUND,
    ).exists():
        return None

    if scan_job.is_trial:
        actual_cost = 0
    else:
        actual_cost = estimate_scan_cost(max(0, int(actual_pages)), scan_job.effective_categories)
        if deep_agent_ran and _scan_is_deep(scan_job):
            # 深度附加費只看 agent 是否真的跑了，與實際爬到幾頁無關
            # （只爬到 1 頁的網站，agent 照樣花了 token）
            actual_cost += agent_deep_fee(
                scan_job.max_pages, active_authorized=True
            )
    outstanding = _sum_holds(wallet, scan_job.id)
    refund_amount = max(0, outstanding - actual_cost)

    # 統計：完成一次掃描（冪等前置檢查已擋掉重複，這裡保證只在第一次計數）
    wallet.total_scans_used = (wallet.total_scans_used or 0) + 1

    if refund_amount <= 0:
        # 建立 0 元標記交易作為冪等信號：讓 actual_pages == max_pages 情境也能被下次呼叫偵測
        wallet.save(update_fields=["total_scans_used", "updated_at"])
        return CoinTransaction.objects.create(
            wallet=wallet,
            amount=0,
            kind=CoinTransaction.Kind.SCAN_REFUND,
            balance_after=wallet.balance,
            scan_job=scan_job,
            note=f"實際 {actual_pages} 頁，無退款差額",
        )

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


def _credit_purchase(
    user,
    plan: PricingPlan,
    *,
    coin_amount: int,
    price_ntd: int,
) -> CoinTransaction:
    wallet = CoinWallet.objects.select_for_update().get_or_create(user=user)[0]
    new_balance = wallet.balance + coin_amount
    wallet.balance = new_balance
    wallet.total_purchased_ntd = (wallet.total_purchased_ntd or 0) + price_ntd
    wallet.save(update_fields=[
        "balance", "total_purchased_ntd", "updated_at",
    ])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=coin_amount,
        kind=CoinTransaction.Kind.PURCHASE,
        balance_after=new_balance,
        plan=plan,
        note=f"購買 {plan.name}（NT${price_ntd}）",
    )


@transaction.atomic
def purchase_plan(user, plan: PricingPlan) -> CoinTransaction:
    """直接以目前方案值入點；僅供非訂單流程與既有管理測試使用。"""
    return _credit_purchase(
        user,
        plan,
        coin_amount=plan.coin_amount,
        price_ntd=plan.price_ntd,
    )


@transaction.atomic
def complete_purchase_order(
    order_id: int,
    *,
    provider_trade_no: str,
) -> tuple[PurchaseOrder, bool]:
    """在綠界簽章與金額驗證後冪等完成訂單；第二次通知不重複入點。"""
    order = (
        PurchaseOrder.objects.select_for_update()
        .select_related("plan", "user")
        .get(pk=order_id)
    )
    if order.status == PurchaseOrder.Status.PAID:
        return order, False
    if order.status != PurchaseOrder.Status.PENDING:
        raise ValueError("只有 pending 訂單可以完成付款")
    coin_transaction = _credit_purchase(
        order.user,
        order.plan,
        coin_amount=order.coin_amount,
        price_ntd=order.price_ntd,
    )
    order.transaction = coin_transaction
    order.status = PurchaseOrder.Status.PAID
    order.paid_at = timezone.now()
    label = "綠界交易" if settings.ARGUS_PAYMENT_MODE == "ecpay" else "綠界測試交易"
    order.note = f"{label}：{provider_trade_no}"[:255]
    order.save(update_fields=["transaction", "status", "paid_at", "note"])
    return order, True


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


# ---------- 修正產出（Fix Output）：產生額度與計費 ----------
#
# 產生額度以交易紀錄表達（不另建模型、不動 wallet 欄位）：
# - FIXGEN_GRANT（amount=0）：付費掃描結算時附贈，同掃描只贈一次
# - FIXGEN_CHARGE：觸發產生前計費——額度內 amount=0（消耗額度）、
#   額度外扣 ARGUS_COIN_FIXGEN_GENERATION 固定點數
# - FIXGEN_REFUND：產生失敗退費——點數退點（正數）、額度返還（amount=0）
#
# 額度可用判定＝有贈與，且 0 元扣款未被 0 元退款抵銷：失敗重試後額度會回來，
# 「不為失敗的產出付費」對兩種支付方式都成立。


def _scan_net_charge(wallet: CoinWallet, scan_job) -> int:
    """該掃描實際花掉的點數（hold - refund 的淨額）。"""
    rows = CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job=scan_job,
        kind__in=[CoinTransaction.Kind.SCAN_HOLD, CoinTransaction.Kind.SCAN_REFUND],
    ).values_list("amount", flat=True)
    return -sum(rows)


def _fixgen_net_charge(wallet: CoinWallet, scan_job) -> int:
    """該掃描在修正產出上目前實扣的點數淨額。"""
    rows = CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job=scan_job,
        kind__in=[CoinTransaction.Kind.FIXGEN_CHARGE, CoinTransaction.Kind.FIXGEN_REFUND],
    ).values_list("amount", flat=True)
    return -sum(rows)


@transaction.atomic
def grant_fixgen_entitlement(user, scan_job) -> CoinTransaction | None:
    """付費掃描結算後附贈 1 次修正產出額度。

    冪等：同掃描已有 FIXGEN_GRANT → 回 None。淨扣為 0 的掃描（未付費或
    全額退款）不贈與——額度對應的是「一份付費的掃描結果」。
    """
    get_or_create_wallet(user)
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    if CoinTransaction.objects.filter(
        wallet=wallet, scan_job=scan_job, kind=CoinTransaction.Kind.FIXGEN_GRANT
    ).exists():
        return None
    if _scan_net_charge(wallet, scan_job) <= 0:
        return None
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=0,
        kind=CoinTransaction.Kind.FIXGEN_GRANT,
        balance_after=wallet.balance,
        scan_job=scan_job,
        note="付費掃描附贈修正產出額度 1 次",
    )


def fixgen_entitlement_available(user, scan_job) -> bool:
    """該掃描的產生額度是否可用（未消耗，或已因失敗返還）。"""
    wallet = CoinWallet.objects.filter(user=user).first()
    if wallet is None:
        return False
    if not CoinTransaction.objects.filter(
        wallet=wallet, scan_job=scan_job, kind=CoinTransaction.Kind.FIXGEN_GRANT
    ).exists():
        return False
    used = CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job=scan_job,
        kind=CoinTransaction.Kind.FIXGEN_CHARGE,
        amount=0,
    ).count()
    returned = CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job=scan_job,
        kind=CoinTransaction.Kind.FIXGEN_REFUND,
        amount=0,
    ).count()
    return used <= returned


@transaction.atomic
def charge_fixgen_generation(user, scan_job) -> CoinTransaction:
    """觸發修正產出前的計費：額度內 0 元消耗，額度外扣固定點數。

    點數必須在排任務之前扣（同 rebuild 規則）：餘額不足的人不能先讓
    LLM 把 token 花掉。餘額不足 raise InsufficientCoinError。
    """
    get_or_create_wallet(user)
    wallet = CoinWallet.objects.select_for_update().get(user=user)
    if fixgen_entitlement_available(user, scan_job):
        return CoinTransaction.objects.create(
            wallet=wallet,
            amount=0,
            kind=CoinTransaction.Kind.FIXGEN_CHARGE,
            balance_after=wallet.balance,
            scan_job=scan_job,
            note="使用附贈額度產生修正產出",
        )
    cost = settings.ARGUS_COIN_FIXGEN_GENERATION
    if wallet.balance < cost:
        raise InsufficientCoinError(required=cost, balance=wallet.balance)
    new_balance = wallet.balance - cost
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=-cost,
        kind=CoinTransaction.Kind.FIXGEN_CHARGE,
        balance_after=new_balance,
        scan_job=scan_job,
        note=f"修正產出產生扣款（{cost} coin）",
    )


@transaction.atomic
def refund_fixgen_generation(user, scan_job) -> CoinTransaction | None:
    """修正產出失敗退費：點數退點、額度返還。冪等（無可退回 None）。"""
    get_or_create_wallet(user)
    wallet = CoinWallet.objects.select_for_update().get(user=user)

    net_coins = _fixgen_net_charge(wallet, scan_job)
    if net_coins > 0:
        new_balance = wallet.balance + net_coins
        wallet.balance = new_balance
        wallet.save(update_fields=["balance", "updated_at"])
        return CoinTransaction.objects.create(
            wallet=wallet,
            amount=net_coins,
            kind=CoinTransaction.Kind.FIXGEN_REFUND,
            balance_after=new_balance,
            scan_job=scan_job,
            note="修正產出產生失敗，全額退點",
        )

    # 沒有實扣點數 → 看額度是否被消耗而未返還
    used = CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job=scan_job,
        kind=CoinTransaction.Kind.FIXGEN_CHARGE,
        amount=0,
    ).count()
    returned = CoinTransaction.objects.filter(
        wallet=wallet,
        scan_job=scan_job,
        kind=CoinTransaction.Kind.FIXGEN_REFUND,
        amount=0,
    ).count()
    if used <= returned:
        return None
    return CoinTransaction.objects.create(
        wallet=wallet,
        amount=0,
        kind=CoinTransaction.Kind.FIXGEN_REFUND,
        balance_after=wallet.balance,
        scan_job=scan_job,
        note="修正產出產生失敗，附贈額度返還",
    )


def is_paid_tier(user) -> bool:
    """free/paid 二級自動判定：曾購點數包或完成付費掃描即 paid。"""
    wallet = CoinWallet.objects.filter(user=user).first()
    if wallet is None:
        return False
    return (wallet.total_purchased_ntd or 0) > 0 or (wallet.total_scans_used or 0) > 0


# ---------- 輕量訂閱：lazy 結算 ----------
#
# 無週期扣款、無 celery beat：訂閱期數以 periods_remaining 預付記帳，
# 每月點數在「到期邊界被走到」時才補發（登入、wallet/subscription API 進場
# 時觸發 settle_subscription）。金額異動一律走本檔（唯一寫入入口原則）。


def _advance_month(dt: datetime, months: int = 1) -> datetime:
    """月份前進 N 個月；day 超過目標月天數時夾到最後一天（1/31 → 2/28）。

    保留原 datetime 的時分秒與 tzinfo（timezone-aware 可直接存 DB）。
    """
    total = dt.year * 12 + (dt.month - 1) + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _period_label(dt: datetime) -> str:
    """期別標籤，如 2026-09-15 → "2026-09"（last_grant_period 冪等用）。"""
    return f"{dt.year}-{dt.month:02d}"


@transaction.atomic
def grant_subscription(
    user,
    plan: SubscriptionPlan,
    periods: int,
    *,
    source: str,
    admin_actor=None,
) -> UserSubscription:
    """建立或延長訂閱（不直接發點；點數由 settle_subscription 補發）。

    - 首次建立：periods_remaining=periods、current_period_end=now、status=active
    - 既有訂閱：periods_remaining 累加、status 回 active、清 cancelled_at；
      前一輪已全部到期（current_period_end 已過）則從 now 重新起算
    - admin 操作傳 admin_actor：比照 admin_adjust 在服務層寫 AdminAuditLog
    """
    if periods < 1:
        raise ValueError("periods 必須大於 0")
    now = timezone.now()
    sub = UserSubscription.objects.select_for_update().filter(user=user).first()
    if sub is None:
        sub = UserSubscription.objects.create(
            user=user,
            plan=plan,
            periods_remaining=periods,
            current_period_end=now,
            status=UserSubscription.Status.ACTIVE,
            source=source,
        )
    else:
        sub.plan = plan
        sub.periods_remaining += periods
        sub.status = UserSubscription.Status.ACTIVE
        sub.cancelled_at = None
        sub.source = source
        if sub.current_period_end < now:
            # 前一輪已全部到期（expired）：新一輪從 now 起算，避免回填過去期數
            sub.current_period_end = now
        sub.save(update_fields=[
            "plan", "periods_remaining", "status", "cancelled_at",
            "source", "current_period_end", "updated_at",
        ])
    if admin_actor is not None:
        # 延後 import 避免 circular（admin_api 也 import billing.services）
        from apps.admin_api.models import AdminAuditLog, log_admin_action
        log_admin_action(
            admin_actor=admin_actor,
            action=AdminAuditLog.Action.SUBSCRIPTION_ADJUST,
            target_user=user,
            target_repr=f"{user.username} {plan.code} +{periods} 期",
            payload={
                "operation": "grant",
                "plan_code": plan.code,
                "periods": periods,
                "periods_remaining": sub.periods_remaining,
            },
        )
    return sub


SUBSCRIPTION_RENEWAL_GRACE = timedelta(days=3)


@transaction.atomic
def settle_subscription(user) -> list[CoinTransaction]:
    """訂閱 lazy 結算：到期未發的期數逐月補發點數。

    - active：now ≥ current_period_end 且 periods_remaining > 0 時迴圈逐月補發，
      每期發 plan.monthly_coins 點（kind=subscription_grant）、periods_remaining
      減 1、current_period_end 前進一個月、last_grant_period 更新。
    - cancelled：只補發「取消時該期已經開始」（current_period_end ≤ cancelled_at）
      的期數；取消後才開始的新期一律不發。期滿後不會再有異動。
    - periods_remaining 歸零且過了 current_period_end → status=expired。
    - 冪等：select_for_update 交易鎖＋last_grant_period 期別檢查，
      同一期重複呼叫不會重複發點。

    回傳本次實際補發的交易列表（無事可做回空 list）。
    """
    sub = (
        UserSubscription.objects.select_for_update()
        .select_related("plan")
        .filter(user=user)
        .first()
    )
    if sub is None or sub.status == UserSubscription.Status.EXPIRED:
        return []
    now = timezone.now()
    if now < sub.current_period_end:
        return []

    # 鎖定順序固定 sub → wallet，與 grant_monthly_bonus_if_needed 一致
    wallet = CoinWallet.objects.select_for_update().get_or_create(user=user)[0]
    granted: list[CoinTransaction] = []
    while sub.periods_remaining > 0 and now >= sub.current_period_end:
        if (
            sub.status == UserSubscription.Status.CANCELLED
            and sub.current_period_end > (sub.cancelled_at or now)
        ):
            # 已取消：當前到期邊界是在取消之後才到的 → 新期不發
            break
        label = _period_label(sub.current_period_end)
        if sub.last_grant_period == label:
            # 冪等防線：同期已發過（正常流程不會走到，防禦性保留）
            break
        new_balance = wallet.balance + sub.plan.monthly_coins
        wallet.balance = new_balance
        wallet.save(update_fields=["balance", "updated_at"])
        granted.append(CoinTransaction.objects.create(
            wallet=wallet,
            amount=sub.plan.monthly_coins,
            kind=CoinTransaction.Kind.SUBSCRIPTION_GRANT,
            balance_after=new_balance,
            note=f"訂閱月贈點 {sub.plan.name}（{label}）",
        ))
        sub.periods_remaining -= 1
        sub.last_grant_period = label
        sub.current_period_end = _advance_month(sub.current_period_end)
        sub.save(update_fields=[
            "periods_remaining", "last_grant_period",
            "current_period_end", "updated_at",
        ])
    # 綠界定期定額的下一期扣款可能比贈點邊界晚一點到：自動續訂中給寬限期再判定到期
    expire_at = sub.current_period_end
    if SubscriptionOrder.objects.filter(
        user=user, status=SubscriptionOrder.Status.ACTIVE
    ).exists():
        expire_at += SUBSCRIPTION_RENEWAL_GRACE
    if (
        sub.status == UserSubscription.Status.ACTIVE
        and sub.periods_remaining == 0
        and now >= expire_at
    ):
        sub.status = UserSubscription.Status.EXPIRED
        sub.save(update_fields=["status", "updated_at"])
    return granted


@transaction.atomic
def cancel_subscription(user) -> UserSubscription | None:
    """取消訂閱：status=cancelled＋cancelled_at（冪等；重複取消不動）。

    當前期權益保留到 current_period_end（settle 對已開始的期數仍可補發），
    之後不再發新期。無訂閱回 None。
    """
    sub = UserSubscription.objects.select_for_update().filter(user=user).first()
    if sub is None:
        return None
    if sub.status == UserSubscription.Status.ACTIVE:
        sub.status = UserSubscription.Status.CANCELLED
        sub.cancelled_at = timezone.now()
        sub.save(update_fields=["status", "cancelled_at", "updated_at"])
    return sub


def settle_subscription_safe(user) -> None:
    """輕量觸發 lazy 結算：失敗只記 log，不影響呼叫端（登入／API）回應。"""
    try:
        settle_subscription(user)
    except Exception:  # noqa: BLE001 — 結算失敗不該擋登入或錢包查詢
        logger.exception("訂閱 lazy 結算失敗（user_pk=%s）", getattr(user, "pk", None))


# ---------- 綠界信用卡定期定額（訂閱實際扣款） ----------


def _subscription_source() -> str:
    if settings.ARGUS_PAYMENT_MODE == "ecpay":
        return UserSubscription.Source.ECPAY
    return UserSubscription.Source.ECPAY_TEST


def has_active_recurring(user) -> bool:
    return SubscriptionOrder.objects.filter(
        user=user, status=SubscriptionOrder.Status.ACTIVE
    ).exists()


@transaction.atomic
def activate_subscription_order(
    order_id: int, *, provider_trade_no: str, amount: int, rtn_msg: str = ""
) -> tuple[SubscriptionOrder, bool]:
    """首期授權成功（ReturnURL 已驗簽章、商店、金額）：開通訂閱並發首月點數。

    冪等：同一筆委託的首期只處理一次（第二次通知回 False）。
    """
    order = (
        SubscriptionOrder.objects.select_for_update()
        .select_related("plan", "user")
        .get(pk=order_id)
    )
    if order.success_times >= 1:
        return order, False
    if order.status not in {SubscriptionOrder.Status.PENDING, SubscriptionOrder.Status.FAILED}:
        raise ValueError("只有等待付款的訂閱可以開通")
    SubscriptionCharge.objects.create(
        order=order, sequence=1, succeeded=True, amount=amount, rtn_code="1",
        rtn_msg=rtn_msg[:200], provider_ref=provider_trade_no[:40],
    )
    order.status = SubscriptionOrder.Status.ACTIVE
    order.success_times = 1
    order.activated_at = timezone.now()
    order.note = f"首期授權成功：{provider_trade_no}"[:255]
    order.save(update_fields=["status", "success_times", "activated_at", "note"])
    grant_subscription(order.user, order.plan, 1, source=_subscription_source())
    settle_subscription(order.user)
    return order, True


@transaction.atomic
def record_subscription_failure(order_id: int, *, rtn_code: str, rtn_msg: str, amount: int) -> None:
    """首期或某一期扣款失敗：只留紀錄、不發點。首期失敗的委託標成 failed。"""
    order = SubscriptionOrder.objects.select_for_update().get(pk=order_id)
    SubscriptionCharge.objects.create(
        order=order, sequence=order.success_times, succeeded=False, amount=amount,
        rtn_code=str(rtn_code)[:10], rtn_msg=rtn_msg[:200],
    )
    if order.status == SubscriptionOrder.Status.PENDING:
        order.status = SubscriptionOrder.Status.FAILED
    order.note = f"扣款失敗：{rtn_code} {rtn_msg}"[:255]
    order.save(update_fields=["status", "note"])


@transaction.atomic
def record_subscription_period_charge(
    order_id: int,
    *,
    total_success_times: int,
    amount: int,
    gwsr: str,
    process_date: str,
    rtn_msg: str = "",
) -> int:
    """第 2 期起每次成功扣款（PeriodReturnURL 已驗簽章、商店、金額）：每成功一次加一期。

    冪等：以綠界累計成功次數 TotalSuccessTimes 判斷，同一期重送不重複發點。回傳本次新增期數。
    已取消續訂後若綠界仍扣款成功（取消前已排程），使用者有付錢，照樣發點。
    """
    order = (
        SubscriptionOrder.objects.select_for_update()
        .select_related("plan", "user")
        .get(pk=order_id)
    )
    new_periods = total_success_times - order.success_times
    if new_periods <= 0:
        return 0
    SubscriptionCharge.objects.create(
        order=order, sequence=total_success_times, succeeded=True, amount=amount,
        rtn_code="1", rtn_msg=rtn_msg[:200], provider_ref=str(gwsr)[:40],
        processed_at=str(process_date)[:32],
    )
    order.success_times = total_success_times
    update_fields = ["success_times"]
    if order.status == SubscriptionOrder.Status.ACTIVE and total_success_times >= order.exec_times:
        order.status = SubscriptionOrder.Status.ENDED
        update_fields.append("status")
    order.save(update_fields=update_fields)
    grant_subscription(order.user, order.plan, new_periods, source=_subscription_source())
    settle_subscription(order.user)
    return new_periods


def stop_recurring_charges(user) -> int:
    """向綠界取消此使用者所有自動續訂中的委託；任一筆失敗丟 EcpayActionError（其餘維持原狀）。

    網路呼叫不能包在資料庫交易裡；綠界確認取消後才把委託標成 cancelled。回傳取消筆數。
    """
    from apps.billing.ecpay import cancel_period_order

    cancelled = 0
    for order in SubscriptionOrder.objects.filter(
        user=user, status=SubscriptionOrder.Status.ACTIVE
    ):
        cancel_period_order(order)
        SubscriptionOrder.objects.filter(
            pk=order.pk, status=SubscriptionOrder.Status.ACTIVE
        ).update(status=SubscriptionOrder.Status.CANCELLED, cancelled_at=timezone.now())
        cancelled += 1
    return cancelled


def cancel_subscription_and_recurring(user) -> UserSubscription | None:
    """取消訂閱：先停止綠界自動扣款（失敗丟 EcpayActionError、訂閱維持不變），再取消本地訂閱。"""
    stop_recurring_charges(user)
    return cancel_subscription(user)
