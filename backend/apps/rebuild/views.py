import secrets

from config.throttling import AnonRateThrottle
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.billing.services import (
    InsufficientCoinError,
    estimate_rebuild_hold,
    get_or_create_wallet,
    hold_for_rebuild,
)
from apps.rebuild.models import SiteRebuild
from apps.rebuild.serializers import (
    SiteRebuildCreateSerializer,
    SiteRebuildDetailSerializer,
    SiteRebuildSerializer,
    page_findings,
    public_edits,
)
from apps.rebuild.tasks import ask_rebuild_agent, run_site_rebuild
from apps.scans.models import Page

# 分享檢視的 HTML 一律在「無 script、無表單、不能導覽上層」的 sandbox 裡顯示：
# 內容來自第三方網站，不能讓它在 Argus 網域上執行程式或收集輸入（防 XSS 與釣魚）。
# 快照本來就是瀏覽器渲染後的 DOM，不執行 script 也能看到版面。
SHARE_HTML_CSP = (
    "sandbox; script-src 'none'; object-src 'none'; form-action 'none'; "
    "frame-ancestors 'self'"
)


class RebuildPagination(PageNumberPagination):
    """與 scans 家族一致的分頁：預設 100、可用 ?page_size= 調到上限 500。

    不分頁的話，帳號累積夠多產出時 list 會一次回傳全部。上限存在的理由是
    擋掉惡意的大請求，不是限制正常使用。
    """

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class SiteRebuildViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SiteRebuildSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = RebuildPagination

    def get_serializer_class(self):
        # 單筆才給 trace；列表被每秒 polling，不能每次都拖著思考流。
        if self.action == "retrieve":
            return SiteRebuildDetailSerializer
        return SiteRebuildSerializer

    def get_queryset(self):
        queryset = SiteRebuild.objects.filter(
            scan_job__user=self.request.user
        ).select_related("page")
        scan_id = self.request.query_params.get("scan_id")
        if scan_id:
            queryset = queryset.filter(scan_job_id=scan_id)
        return queryset

    def create(self, request, *args, **kwargs):
        payload = SiteRebuildCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        # 從 Page 反查 scan_job，不讓呼叫端自己指定——否則可以把別人的 page
        # 掛到自己的 scan 底下。同時這個 filter 就是擁有權檢查。
        page = Page.objects.filter(
            pk=payload.validated_data["page"], scan_job__user=request.user
        ).select_related("scan_job").first()
        if page is None:
            raise Http404("找不到頁面。")
        if page.scan_job.project_id and page.scan_job.project.is_demo:
            # 示範專案是虛構網站，複刻會連不到目標又白花點數
            return Response(
                {"detail": "示範專案不提供網頁複刻；請對你自己的網站使用。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rebuild = SiteRebuild.objects.create(scan_job=page.scan_job, page=page)
        # 先扣再排任務。反過來的話，餘額不足的人已經讓 agent 花掉真錢了才被擋。
        try:
            hold_for_rebuild(request.user, rebuild)
        except InsufficientCoinError as exc:
            rebuild.delete()
            return Response(
                {"detail": str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED
            )
        run_site_rebuild.delay(rebuild.pk)
        return Response(
            SiteRebuildSerializer(rebuild).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        """在同一個 agent session 裡追問。

        餘額檢查放在這裡而不是 task 裡：餘額為 0 的人必須在 agent 花掉真錢
        **之前**被擋下來。實際扣多少由用量決定（事後結算），這裡只確認他至少
        付得起最低消費。
        """
        rebuild = self.get_object()
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response(
                {"detail": "請輸入問題。"}, status=status.HTTP_400_BAD_REQUEST
            )
        if rebuild.status in {
            SiteRebuild.Status.PENDING,
            SiteRebuild.Status.SNAPSHOTTING,
            SiteRebuild.Status.OPTIMIZING,
            SiteRebuild.Status.ASKING,
        }:
            return Response(
                {"detail": "上一輪還在進行中，請稍候。"},
                status=status.HTTP_409_CONFLICT,
            )
        if not rebuild.opencode_session_id:
            return Response(
                {"detail": "這次複刻沒有可延續的對話。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        wallet = get_or_create_wallet(request.user)
        if wallet.balance < settings.ARGUS_COIN_REBUILD_MIN:
            return Response(
                {"detail": f"coin 不足：至少需要 {settings.ARGUS_COIN_REBUILD_MIN}"},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        ask_rebuild_agent.delay(rebuild.pk, question)
        return Response(
            SiteRebuildDetailSerializer(rebuild).data, status=status.HTTP_202_ACCEPTED
        )

    @action(detail=False, methods=["get"])
    def cost(self, request):
        """產生前先讓前端知道要預扣多少點。

        沒有這個端點，使用者只能按下去才從 402 得知額度與餘額不足——按鈕
        本身要先講清楚代價，這是 affordance 不是額外功能。

        回傳的是**預扣上限**不是最終價格：實際依 agent 用量結算後退差額，
        所以欄位名是 hold，不要改回 cost 讓前端誤以為那就是要付的錢。
        """
        return Response(
            {
                "hold": estimate_rebuild_hold(),
                "balance": get_or_create_wallet(request.user).balance,
            }
        )

    @action(detail=True, methods=["get"], url_path="turn-trace")
    def turn_trace(self, request, pk=None):
        """取某一輪對話的思考流。

        獨立成一個端點而不是塞進 detail：detail 在執行期間每秒被 polling，
        把 20 輪的思考流一起送出去等於每秒好幾 MB。使用者真的展開某一輪時
        才需要這份資料，而那是點擊觸發、一次性的。
        """
        rebuild = self.get_object()
        try:
            index = int(request.query_params.get("index", ""))
        except ValueError:
            return Response(
                {"detail": "index 必須是整數。"}, status=status.HTTP_400_BAD_REQUEST
            )

        conversation = rebuild.conversation or []
        # 負索引在 Python 會從尾端取值，這裡不是想要的行為——那會讓 index=-1
        # 悄悄回傳最後一輪，而不是告訴呼叫端索引無效。
        if index < 0 or index >= len(conversation):
            return Response(
                {"detail": "查無此對話輪次。"}, status=status.HTTP_404_NOT_FOUND
            )

        return Response({"index": index, "trace": conversation[index].get("trace") or []})

    @action(detail=True, methods=["post", "delete"])
    def share(self, request, pk=None):
        """POST {access: link|login} 開啟分享或切換權限；DELETE 關閉分享（改回僅限本人）。

        參考 Notion／Figma：連結第一次分享時產生、之後固定不變，關閉再打開仍是同一個網址；
        不過期（舊版 7 天連結的期限在重新設定權限時清除）。分享頁唯讀，不含帳號、點數或
        其他頁面。
        """
        rebuild = self.get_object()
        fields = ["share_access", "share_token", "share_expires_at", "updated_at"]
        if request.method == "DELETE":
            rebuild.share_access = SiteRebuild.ShareAccess.PRIVATE
            rebuild.save(update_fields=fields)
            return Response(SiteRebuildSerializer(rebuild).data)
        access = str(request.data.get("access") or SiteRebuild.ShareAccess.LINK)
        if access not in {SiteRebuild.ShareAccess.LINK, SiteRebuild.ShareAccess.LOGIN}:
            return Response({"access": ["只能是 link 或 login。"]}, status=400)
        if not rebuild.optimized_path:
            return Response(
                {"detail": "這次優化還沒有產出，無法分享。"}, status=status.HTTP_400_BAD_REQUEST
            )
        if not rebuild.share_token:
            rebuild.share_token = secrets.token_urlsafe(32)
        rebuild.share_access = access
        rebuild.share_expires_at = None
        rebuild.save(update_fields=fields)
        return Response(SiteRebuildSerializer(rebuild).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """下載複刻（variant=original）或優化後（variant=optimized）的 HTML。

        **一律 as_attachment**：這份 HTML 來自第三方網站、內容不受我們控制。
        若讓瀏覽器直接在 Argus 的網域上渲染，等於把任意第三方 script 放進
        我們自己的 origin——變成儲存型 XSS 與釣魚頁的載體。加上 CSP sandbox
        是第二道：即使有人硬存檔開啟，也不會帶著我們的 cookie 執行。
        """
        rebuild = self.get_object()
        variant = request.query_params.get("variant", "optimized")
        relative = (
            rebuild.snapshot_path if variant == "original" else rebuild.optimized_path
        )
        if not relative:
            return Response(
                {"detail": "此版本尚未產出。"}, status=status.HTTP_404_NOT_FOUND
            )

        path = settings.MEDIA_ROOT / relative
        if not path.is_file():
            raise Http404("檔案已不存在。")

        response = FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=f"argus-scan-{rebuild.scan_job_id}-page-{rebuild.page_id}-{variant}.html",
            content_type="text/html",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


# ------------------------------------------------------------------ 公開分享檢視


def _shared_rebuild(request, token: str) -> SiteRebuild:
    if not token or len(token) < 32:
        raise Http404
    rebuild = (
        SiteRebuild.objects.filter(share_token=token).select_related("page").first()
    )
    if rebuild is None or not rebuild.share_is_active:
        raise Http404("分享連結不存在或已關閉。")
    if (
        rebuild.share_access == SiteRebuild.ShareAccess.LOGIN
        and not request.user.is_authenticated
    ):
        # 前端據此顯示「登入後檢視」；不透露是誰分享的
        raise NotAuthenticated("這個分享需要登入 Argus 才能檢視。")
    return rebuild


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def shared_rebuild(request, token: str):
    """分享頁的資料（唯讀）：受測網址、發現的問題、修改清單、成果摘要與前後指標。

    不回傳帳號、點數、掃描 ID、修改原文等任何個人或內部資訊。
    """
    rebuild = _shared_rebuild(request, token)
    return Response(
        {
            "page_url": rebuild.page.final_url,
            "created_at": rebuild.created_at,
            "expires_at": rebuild.share_expires_at,
            "access": rebuild.share_access,
            "has_original": bool(rebuild.snapshot_path),
            "has_optimized": bool(rebuild.optimized_path),
            "reply": rebuild.reply,
            "outcome": rebuild.outcome or {},
            "findings": page_findings(rebuild),
            "edits": public_edits(rebuild),
        }
    )


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def shared_rebuild_html(request, token: str):
    """分享頁比較畫面用的 HTML。分享頁以 XHR 取回後放進 sandbox iframe 的 srcdoc；
    直接在瀏覽器開這個網址會被拒絕。"""
    rebuild = _shared_rebuild(request, token)
    # 瀏覽器會標明這次請求的用途；整頁開啟（document）一律拒絕，讓第三方內容
    # 不會以 Argus 網址單獨呈現（舊瀏覽器沒有這個標頭時仍有 CSP sandbox 保護）
    if request.headers.get("Sec-Fetch-Dest", "empty") not in {"empty", "iframe", "frame"}:
        return HttpResponse("請從分享頁檢視。", status=403, content_type="text/plain")
    variant = request.query_params.get("variant", "optimized")
    relative = rebuild.snapshot_path if variant == "original" else rebuild.optimized_path
    path = settings.MEDIA_ROOT / relative if relative else None
    if path is None or not path.is_file():
        raise Http404("此版本不存在。")
    response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = SHARE_HTML_CSP
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Cache-Control"] = "private, no-store"
    # 全站預設 X-Frame-Options: DENY；這份 HTML 本來就只給 Argus 自己的分享頁內嵌
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
