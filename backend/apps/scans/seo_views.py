"""SEO 分析頁與 Google Search Console 的 API（掛在 /api/projects/<id>/ 底下）。

SiteProjectViewSet 繼承 ProjectSeoActions；callback 是獨立的函式 view（/api/gsc/callback/），
因為 Google 導回時瀏覽器沒有記憶體中的 JWT，身分改由簽章 state＋HttpOnly nonce cookie 證明。
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode, urlsplit

from config.throttling import UserRateThrottle
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponseRedirect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.scans.domain_verification import sync_owned_domains, sync_search_console_ownership
from apps.scans.models import Page, ScanJob, SearchConsoleConnection, SiteProject
from apps.scans.seo import gsc
from apps.scans.seo.keywords import normalize_keywords
from apps.scans.seo.report import page_detail, project_seo

logger = logging.getLogger(__name__)


class GscThrottle(UserRateThrottle):
    scope = "gsc"


def _gsc_error(exc: gsc.GscError, connection: SearchConsoleConnection | None = None):
    if connection is not None and exc.reconnect:
        connection.last_error = str(exc)[:255]
        connection.save(update_fields=["last_error", "updated_at"])
    return Response(
        {"detail": str(exc), "reconnect": exc.reconnect},
        status=status.HTTP_400_BAD_REQUEST,
    )


class ProjectSeoActions:
    """SiteProjectViewSet 的 SEO／GSC actions（需要 get_object 與 _requested_scan）。"""

    def _seo_scan(self, project: SiteProject) -> ScanJob | None:
        return self._requested_scan(project) or (
            project.scans.filter(status=ScanJob.Status.COMPLETED).order_by("-created_at").first()
        )

    # ---------------------------------------------------------------- SEO 分析

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def seo(self, request, pk=None):
        """SEO 分析：最新（或 ?scan= 指定）一次完成掃描的概覽、頁面、連結與關鍵字。"""
        project = self.get_object()
        data = project_seo(project, self._seo_scan(project))
        _ensure_project_connection(project)
        data["gsc"] = _gsc_status(project)
        return Response(data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path=r"seo/pages/(?P<page_id>\d+)")
    def seo_page(self, request, pk=None, page_id=None):
        """單頁證據：完整標題、圖片、連結與檢查結果。"""
        project = self.get_object()
        scan = self._seo_scan(project)
        page = Page.objects.filter(id=page_id, scan_job=scan).first() if scan else None
        if page is None:
            raise Http404("這次掃描沒有這一頁。")
        return Response(page_detail(scan, page))

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="seo/keywords")
    def seo_keywords(self, request, pk=None):
        """設定目標關鍵字（覆蓋整份清單；示範專案也可以設定，只影響這個分析頁）。"""
        project = self.get_object()
        try:
            keywords = normalize_keywords(request.data.get("keywords"))
        except ValueError as exc:
            return Response({"keywords": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        project.target_keywords = keywords
        project.save(update_fields=["target_keywords", "updated_at"])
        return Response({"keywords": keywords})

    # ---------------------------------------------------------------- Search Console

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get", "patch", "delete"], url_path="gsc")
    def gsc_connection(self, request, pk=None):
        """GET 連線狀態；PATCH {property} 選擇資源；DELETE 中斷連線並撤銷 Google 授權。"""
        project = self.get_object()
        if request.method == "GET":
            _ensure_project_connection(project)
        connection = SearchConsoleConnection.objects.filter(project=project).first()
        if request.method == "DELETE":
            if connection is not None:
                _disconnect(connection)
            return Response(status=status.HTTP_204_NO_CONTENT)
        if request.method == "PATCH":
            if connection is None:
                return Response({"detail": "尚未連接 Search Console。"}, status=400)
            chosen = str(request.data.get("property") or "")
            if not chosen:  # 更換資源：先清除，前端再列出可選資源
                connection.property_url = ""
                connection.save(update_fields=["property_url", "updated_at"])
                # 使用者要自己挑：這段期間不要又被自動選回去
                cache.set(f"gsc-auto-property:{connection.pk}", True, _MANUAL_CHOICE_SECONDS)
                return Response(_gsc_status(project))
            try:
                sites = {site["site_url"] for site in gsc.list_sites(connection)}
            except gsc.GscError as exc:
                return _gsc_error(exc, connection)
            if chosen not in sites:
                return Response({"property": ["這個 Google 帳號沒有這個資源。"]}, status=400)
            connection.property_url = chosen
            connection.last_error = ""
            connection.save(update_fields=["property_url", "last_error", "updated_at"])
        return Response(_gsc_status(project))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="gsc/connect", throttle_classes=[GscThrottle])
    def gsc_connect(self, request, pk=None):
        """回傳 Google 授權網址；nonce 寫進只在 callback 路徑送出的 HttpOnly cookie。"""
        project = self.get_object()
        if not gsc.is_enabled():
            return Response({"detail": "管理員尚未設定 Google Search Console 串接。"}, status=400)
        if project.is_demo:
            return Response({"detail": "示範專案是虛構網站，無法連接 Search Console。"}, status=400)
        url, nonce = gsc.build_authorization(request, project)
        response = Response({"authorization_url": url})
        response.set_cookie(
            gsc.NONCE_COOKIE, nonce, max_age=gsc.STATE_MAX_AGE, httponly=True,
            secure=settings.AUTH_REFRESH_COOKIE_SECURE, samesite="Lax", path=gsc.CALLBACK_PATH,
        )
        return response

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="gsc/properties",
            throttle_classes=[GscThrottle])
    def gsc_properties(self, request, pk=None):
        project = self.get_object()
        connection = _connection_or_404(project)
        try:
            sites = gsc.list_sites(connection)
        except gsc.GscError as exc:
            return _gsc_error(exc, connection)
        for site in sites:
            site["matches"] = gsc.property_matches(site["site_url"], project.origin)
        return Response({"properties": sites})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="gsc/performance",
            throttle_classes=[GscThrottle])
    def gsc_performance(self, request, pk=None):
        """搜尋成效（?days=7|28|90）。平均排名是期間內的統計值，不是即時名次。"""
        project = self.get_object()
        connection = _connection_or_404(project)
        if not connection.property_url:
            return Response({"detail": "請先選擇 Search Console 資源。"}, status=400)
        days = request.query_params.get("days", "28")
        try:
            data = gsc.performance(connection, int(days) if days.isdigit() else 28)
        except gsc.GscError as exc:
            return _gsc_error(exc, connection)
        return Response(data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="gsc/inspect",
            throttle_classes=[GscThrottle])
    def gsc_inspect(self, request, pk=None):
        """網址檢查：查詢 Google 是否已收錄這個網址（只接受本專案網站的網址）。"""
        project = self.get_object()
        connection = _connection_or_404(project)
        if not connection.property_url:
            return Response({"detail": "請先選擇 Search Console 資源。"}, status=400)
        url = str(request.data.get("url") or "")
        target, origin = urlsplit(url), urlsplit(project.origin)
        if target.scheme not in {"http", "https"} or target.hostname != origin.hostname:
            return Response({"url": ["只能檢查這個網站的網址。"]}, status=400)
        try:
            return Response(gsc.inspect_url(connection, url))
        except gsc.GscError as exc:
            return _gsc_error(exc, connection)


def _disconnect(connection: SearchConsoleConnection) -> None:
    """刪除連線；同一個 Google 授權還被其他連線共用時只刪本地，不撤銷 Google 端授權
    （否則中斷專案連線會連帶讓網域驗證頁的帳號層級連線失效）。"""
    try:
        token = gsc.decrypt_token(connection.refresh_token_encrypted)
    except gsc.GscError:
        token = ""
    shared = False
    if token:
        for other in SearchConsoleConnection.objects.filter(user=connection.user).exclude(
            pk=connection.pk
        ):
            try:
                if gsc.decrypt_token(other.refresh_token_encrypted) == token:
                    shared = True
                    break
            except gsc.GscError:
                continue
    if not shared:
        gsc.revoke(connection)
    connection.delete()


# 自動挑選資源失敗（Google 暫時錯誤、沒有相符資源）後多久再試；SEO 頁每次載入都會呼叫，
# 不能每次都打 Google API
_AUTO_PROPERTY_RETRY_SECONDS = 600
_MANUAL_CHOICE_SECONDS = 86400


def pick_property(sites: list[dict], origin: str) -> str:
    """從使用者的 Search Console 資源中選出最適合這個網站的一個；沒有相符的回空字串。

    網域資源（sc-domain:）涵蓋 http／https 與所有子網域，資料最完整，優先；
    多個網域資源時取最具體（最長）的；沒有網域資源才用協定＋主機相同的網址前置字元資源。
    """
    matches = [site["site_url"] for site in sites if gsc.property_matches(site["site_url"], origin)]
    domains = sorted((m for m in matches if m.startswith("sc-domain:")), key=len, reverse=True)
    return (domains or matches or [""])[0]


def _ensure_project_connection(project: SiteProject) -> None:
    """讓 SEO 分析頁不必再連一次 Search Console，也不必手動選資源（2026-10-06 使用者回報）。

    1. 專案還沒有自己的連線，但使用者在網域驗證頁（帳號層級）或其他專案連過 Google →
       沿用同一個授權建立專案連線。
    2. 專案連線還沒選資源 → 自動選好與網站相符的資源（`pick_property`）。
    失敗只記在快取裡稍後再試，不影響頁面。
    """
    if project.is_demo or not gsc.is_enabled():
        return
    connection = SearchConsoleConnection.objects.filter(project=project).first()
    if connection is None:
        usable = SearchConsoleConnection.objects.filter(user=project.user, last_error="")
        # 帳號層級（網域驗證頁）優先；沒有才沿用其他專案的授權
        source = (
            usable.filter(project__isnull=True).first()
            or usable.order_by("-updated_at").first()
        )
        if source is None:
            return
        connection, _ = SearchConsoleConnection.objects.get_or_create(
            project=project,
            defaults={
                "user": project.user,
                "refresh_token_encrypted": source.refresh_token_encrypted,
            },
        )
        logger.info("Search Console 沿用既有授權 project_id=%s", project.id)
    if connection.property_url or connection.last_error:
        return
    retry_key = f"gsc-auto-property:{connection.pk}"
    if cache.get(retry_key):
        return
    try:
        chosen = pick_property(gsc.list_sites(connection), project.origin)
    except gsc.GscError:
        chosen = ""
    if not chosen:
        cache.set(retry_key, True, _AUTO_PROPERTY_RETRY_SECONDS)
        return
    connection.property_url = chosen
    connection.save(update_fields=["property_url", "updated_at"])


def link_user_projects(user) -> None:
    """帳號層級剛連接 Search Console：使用者所有網站專案一併沿用授權並選好資源。"""
    for project in SiteProject.objects.filter(user=user, archived_at__isnull=True, is_demo=False):
        try:
            _ensure_project_connection(project)
        except Exception:  # noqa: BLE001 — 個別專案失敗不影響連接
            logger.warning("Search Console 專案沿用失敗 project_id=%s", project.id)


def _connection_or_404(project: SiteProject) -> SearchConsoleConnection:
    connection = SearchConsoleConnection.objects.filter(project=project).first()
    if connection is None:
        raise Http404("尚未連接 Search Console。")
    return connection


def _gsc_status(project: SiteProject) -> dict:
    connection = SearchConsoleConnection.objects.filter(project=project).first()
    return {
        "enabled": gsc.is_enabled(),
        "connected": connection is not None,
        "property": connection.property_url if connection else "",
        "property_matches": bool(
            connection and connection.property_url
            and gsc.property_matches(connection.property_url, project.origin)
        ),
        "needs_reconnect": bool(connection and connection.last_error),
        "error": connection.last_error if connection else "",
        "connected_at": connection.connected_at.isoformat() if connection else None,
    }


def _back_to_seo(project_id, **params) -> HttpResponseRedirect:
    target = f"/projects/{project_id}/seo" if project_id else "/projects"
    if params:
        target += "?" + urlencode(params)
    response = HttpResponseRedirect(target)
    response.delete_cookie(gsc.NONCE_COOKIE, path=gsc.CALLBACK_PATH)
    return response


# ------------------------------------------------ 帳號層級連線（/domains 一鍵連接，2026-10-04）


def _account_status(user) -> dict:
    connections = SearchConsoleConnection.objects.filter(user=user)
    account = connections.filter(project__isnull=True).first()
    connected = connections.exists()
    # 只有專案連線（從 SEO 分析頁連接）時，看專案連線：全部都授權失效才需要重新連接。
    # 2026-10-09 前只看帳號層級連線，專案連線失效時網域驗證頁仍顯示「已連接」，
    # 同步失敗卻沒有重新連接或中斷連線可按
    if account is not None:
        broken = account if account.last_error else None
    else:
        broken = None if connections.filter(last_error="").exists() else connections.first()
    return {
        "enabled": gsc.is_enabled(),
        # 任一連線（帳號層級或任一專案）都能用來驗證網域
        "connected": connected,
        "account_connection": account is not None,
        "needs_reconnect": broken is not None,
        "error": broken.last_error if broken else "",
        "connected_at": account.connected_at.isoformat() if account else None,
    }


def _sync_all(user) -> tuple[list[str], str]:
    """用使用者所有連線同步擁有的網站；回傳 (通過的網域, 全部失敗時的錯誤訊息)。"""
    verified: set[str] = set()
    error, ok_any = "", False
    for connection in SearchConsoleConnection.objects.filter(user=user):
        try:
            verified.update(sync_owned_domains(connection))
            ok_any = True
        except gsc.GscError as exc:
            error = str(exc)
            if exc.reconnect:
                connection.last_error = str(exc)[:255]
                connection.save(update_fields=["last_error", "updated_at"])
    return sorted(verified), "" if ok_any else error


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def domains_gsc(request):
    """GET 帳號的 Search Console 連線狀態；DELETE 中斷帳號層級連線並撤銷 Google 授權
    （專案的連線不動；已驗證的網域照常有效到期滿）。沒有帳號層級連線、只有專案連線時，
    DELETE 中斷全部專案連線——那是這一頁唯一看得到的連線，不能讓使用者無從中斷。"""
    if request.method == "DELETE":
        connections = SearchConsoleConnection.objects.filter(user=request.user)
        account = connections.filter(project__isnull=True).first()
        targets = [account] if account is not None else list(connections)
        for connection in targets:
            _disconnect(connection)
    return Response(_account_status(request.user))


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([GscThrottle])
def domains_gsc_connect(request):
    """回傳 Google 授權網址（帳號層級）；完成後導回 /domains 並自動匯入擁有的網站。"""
    if not gsc.is_enabled():
        return Response({"detail": "管理員尚未設定 Google Search Console 串接。"}, status=400)
    url, nonce = gsc.build_authorization(request)
    response = Response({"authorization_url": url})
    response.set_cookie(
        gsc.NONCE_COOKIE, nonce, max_age=gsc.STATE_MAX_AGE, httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE, samesite="Lax", path=gsc.CALLBACK_PATH,
    )
    return response


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([GscThrottle])
def domains_gsc_sync(request):
    """重新讀取 Search Console：擁有的網站全部匯入為已驗證網域。"""
    if not SearchConsoleConnection.objects.filter(user=request.user).exists():
        return Response({"detail": "尚未連接 Google Search Console。"}, status=400)
    verified, error = _sync_all(request.user)
    if error:
        return Response({"detail": error, **_account_status(request.user)}, status=400)
    return Response({"verified": verified, **_account_status(request.user)})


def _back_to_domains(**params) -> HttpResponseRedirect:
    response = HttpResponseRedirect("/domains?" + urlencode(params))
    response.delete_cookie(gsc.NONCE_COOKIE, path=gsc.CALLBACK_PATH)
    return response


def _account_callback(request, data: dict) -> HttpResponseRedirect:
    if request.query_params.get("error"):
        return _back_to_domains(gsc="error", reason="已取消 Google 授權。")
    code = request.query_params.get("code", "")
    if not code:
        return _back_to_domains(gsc="error", reason="Google 沒有回傳授權碼。")
    try:
        refresh = gsc.exchange_code(code, gsc.redirect_uri(request))
    except gsc.GscError as exc:
        return _back_to_domains(gsc="error", reason=str(exc))
    connection, _ = SearchConsoleConnection.objects.update_or_create(
        user_id=data["u"], project=None,
        defaults={"refresh_token_encrypted": gsc.encrypt_token(refresh), "last_error": ""},
    )
    logger.info("Search Console 帳號層級已連接 user_id=%s", data["u"])
    # 重新授權時，授權已失效的專案連線一併換成新授權，不必再到各專案重連
    SearchConsoleConnection.objects.filter(user_id=data["u"], project__isnull=False).exclude(
        last_error=""
    ).update(refresh_token_encrypted=connection.refresh_token_encrypted, last_error="")
    link_user_projects(connection.user)
    try:
        verified = sync_owned_domains(connection)
    except Exception:  # noqa: BLE001 — Google API 暫時失敗不該讓連接失敗
        logger.warning("Search Console 網域匯入失敗 user_id=%s", data["u"])
        return _back_to_domains(gsc="connected", synced="0")
    return _back_to_domains(gsc="connected", verified=str(len(verified)))


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([AllowAny])
def gsc_callback(request):
    """Google 授權完成後導回這裡；成功或失敗都轉回 SEO 分析頁並以 ?gsc= 告知結果。"""
    state = request.query_params.get("state", "")
    try:
        data = gsc.read_state(state, request.COOKIES.get(gsc.NONCE_COOKIE, ""))
    except gsc.GscError as exc:
        return _back_to_seo(None, gsc="error", reason=str(exc))
    if data.get("p") is None:
        return _account_callback(request, data)
    project = SiteProject.objects.filter(id=data["p"], user_id=data["u"]).first()
    if project is None:
        return _back_to_seo(None, gsc="error", reason="找不到這個專案。")
    if request.query_params.get("error"):
        return _back_to_seo(project.id, gsc="error", reason="已取消 Google 授權。")
    code = request.query_params.get("code", "")
    if not code:
        return _back_to_seo(project.id, gsc="error", reason="Google 沒有回傳授權碼。")
    try:
        refresh = gsc.exchange_code(code, gsc.redirect_uri(request))
    except gsc.GscError as exc:
        return _back_to_seo(project.id, gsc="error", reason=str(exc))
    connection, _ = SearchConsoleConnection.objects.update_or_create(
        project=project,
        defaults={
            "user_id": data["u"],
            "refresh_token_encrypted": gsc.encrypt_token(refresh),
            "last_error": "",
        },
    )
    logger.info("Search Console 已連接 project_id=%s", project.id)
    _ensure_project_connection(project)
    # 順便用 Search Console 的擁有者身分完成網域驗證（主動式資安測試的閘門）；失敗不影響連接
    verified: list[str] = []
    try:
        verified = sync_search_console_ownership(connection, project)
    except Exception:  # noqa: BLE001 — Google API 暫時失敗不該讓連接失敗
        logger.warning("Search Console 網域自動驗證失敗 project_id=%s", project.id)
    if verified:
        return _back_to_seo(project.id, gsc="connected", verified=",".join(verified))
    return _back_to_seo(project.id, gsc="connected")
