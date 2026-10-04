"""SEO 分析頁與 Google Search Console 的 API（掛在 /api/projects/<id>/ 底下）。

SiteProjectViewSet 繼承 ProjectSeoActions；callback 是獨立的函式 view（/api/gsc/callback/），
因為 Google 導回時瀏覽器沒有記憶體中的 JWT，身分改由簽章 state＋HttpOnly nonce cookie 證明。
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode, urlsplit

from config.throttling import UserRateThrottle
from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
        connection = SearchConsoleConnection.objects.filter(project=project).first()
        if request.method == "DELETE":
            if connection is not None:
                gsc.revoke(connection)
                connection.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        if request.method == "PATCH":
            if connection is None:
                return Response({"detail": "尚未連接 Search Console。"}, status=400)
            chosen = str(request.data.get("property") or "")
            if not chosen:  # 更換資源：先清除，前端再列出可選資源
                connection.property_url = ""
                connection.save(update_fields=["property_url", "updated_at"])
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
    SearchConsoleConnection.objects.update_or_create(
        project=project,
        defaults={
            "user_id": data["u"],
            "refresh_token_encrypted": gsc.encrypt_token(refresh),
            "last_error": "",
        },
    )
    logger.info("Search Console 已連接 project_id=%s", project.id)
    return _back_to_seo(project.id, gsc="connected")
