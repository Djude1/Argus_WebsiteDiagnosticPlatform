"""使用者自行刪除帳號（2026-10-04）。

決策（使用者確認）：個人資料與使用者產生的內容全部刪除；帳務紀錄匿名保留。
- 刪除：網站專案、掃描（頁面、截圖、問題、報告與防偽紀錄、授權紀錄、網頁複刻檔案）、
  Search Console 連線（先向 Google 撤銷）、網域驗證、MCP 憑證與呼叫紀錄、評論與按讚／檢舉、
  登入紀錄、密碼重設 token、大頭貼，並撤銷所有登入 token。
- 匿名保留：CoinWallet／CoinTransaction（禁止修改或刪除，見根 CLAUDE.md；掃描刪除時
  scan_job／site_rebuild 依 model 設計 SET_NULL，金額與種類不變）、PurchaseOrder（只清除
  買受人姓名、Email、公司、統編、載具，保留金額與時間）、AdminAuditLog（禁止刪除）。
- User 列保留但改成匿名且停用：username＝deleted-<id>-<亂數>、Email／姓名／handle 清空、
  密碼不可用、is_active=False。同一個 Google 帳號之後可以重新註冊。
管理員也可以刪除自己的帳號（刪除後失去管理權限）；只有「最後一位啟用中的超級管理員」不能刪，
避免沒有人能再管理後台。管理員從後台刪除使用者也走同一個函式（admin_api.views.user_delete）。
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

logger = logging.getLogger(__name__)


def _media_file(relative: str) -> Path | None:
    """只接受 MEDIA_ROOT 底下的檔案；示範專案截圖在程式碼目錄、所有帳號共用，不能刪。"""
    if not relative:
        return None
    media_root = Path(settings.MEDIA_ROOT).resolve()
    for base in (Path(settings.BASE_DIR), media_root):
        candidate = (base / relative).resolve()
        if candidate.is_relative_to(media_root):
            return candidate
    return None


def _collect_files(user) -> list[Path]:
    from apps.rebuild.models import SiteRebuild
    from apps.scans.models import Page, ScanJob
    from apps.scans.reports import report_output_path

    files: list[Path] = []
    scans = ScanJob.objects.filter(user=user)
    for path in Page.objects.filter(scan_job__in=scans).values_list("screenshot_path", flat=True):
        if target := _media_file(path):
            files.append(target)
    for rebuild in SiteRebuild.objects.filter(scan_job__in=scans).only(
        "snapshot_path", "optimized_path"
    ):
        for path in (rebuild.snapshot_path, rebuild.optimized_path):
            if target := _media_file(path):
                files.append(target)
    for scan in scans.only("id"):
        report = report_output_path(scan)
        files += [report, report.with_suffix(".docx")]
    if user.avatar:
        try:
            files.append(Path(user.avatar.path))
        except (NotImplementedError, ValueError):
            pass
    return files


def _remove_files(files: list[Path]) -> None:
    for path in files:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("刪除帳號時移除檔案失敗 path=%s", path.name)
    # 掃描截圖目錄清空後一併移除（media/scans/<id>/）
    for directory in {path.parent for path in files}:
        try:
            directory.rmdir()
        except OSError:
            pass


def _revoke_search_console(user) -> None:
    from apps.scans.models import SearchConsoleConnection
    from apps.scans.seo import gsc

    for connection in SearchConsoleConnection.objects.filter(user=user):
        gsc.revoke(connection)  # 失敗不影響刪除（使用者也可到 Google 帳號頁移除）


def delete_account(user) -> None:
    from apps.accounts.models import LoginEvent, PasswordResetToken
    from apps.billing.models import PurchaseOrder, SubscriptionOrder
    from apps.billing.services import cancel_subscription_and_recurring
    from apps.mcp_access.models import McpApiKey, McpCallLog
    from apps.reviews.models import (
        PlatformReview,
        ReviewHelpful,
        ReviewMessage,
        ReviewMessageHelpful,
        ReviewReport,
        ReviewResponseHelpful,
    )
    from apps.scans.models import ScanJob, SiteProject, VerifiedDomain

    user_model = type(user)
    if user.is_superuser and not user_model.objects.filter(
        is_superuser=True, is_active=True
    ).exclude(pk=user.pk).exists():
        raise PermissionError("這是最後一位超級管理員，不能刪除；請先指定另一位超級管理員。")

    cancel_subscription_and_recurring(user)
    _revoke_search_console(user)
    files = _collect_files(user)
    user_id = user.pk
    with transaction.atomic():
        # 評論：先刪按讚與檢舉（自己對他人的），再刪自己的評論（連帶修訂與他人對它的按讚）
        for model in (ReviewHelpful, ReviewResponseHelpful, ReviewMessageHelpful):
            model.objects.filter(user=user).delete()
        ReviewMessage.objects.filter(author=user).delete()
        ReviewReport.objects.filter(reporter=user).delete()
        PlatformReview.objects.filter(user=user).delete()

        McpCallLog.objects.filter(user=user).delete()
        McpApiKey.objects.filter(user=user).delete()
        # 掃描連帶刪除頁面、問題、報告防偽紀錄、授權紀錄、複刻；點數交易的 scan_job 依設計 SET_NULL
        ScanJob.objects.filter(user=user).delete()
        SiteProject.objects.filter(user=user).delete()  # Search Console 連線一併刪除
        VerifiedDomain.objects.filter(user=user).delete()
        LoginEvent.objects.filter(user=user).delete()
        PasswordResetToken.objects.filter(user=user).delete()

        PurchaseOrder.objects.filter(user=user).update(
            buyer_name="已刪除用戶",
            buyer_email=f"deleted-{user_id}@deleted.invalid",
            company_name="",
            tax_id="",
            carrier_id="",
        )
        SubscriptionOrder.objects.filter(user=user).update(
            buyer_name="已刪除用戶",
            buyer_email=f"deleted-{user_id}@deleted.invalid",
            company_name="",
            tax_id="",
            carrier_id="",
        )

        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        user.username = f"deleted-{user_id}-{secrets.token_hex(4)}"
        user.email = ""
        user.first_name = ""
        user.last_name = ""
        user.handle = None
        user.avatar = None
        user.set_unusable_password()
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.deleted_at = timezone.now()
        user.save()
        transaction.on_commit(lambda: _remove_files(files))
    logger.info("帳號已刪除 user_id=%s", user_id)
