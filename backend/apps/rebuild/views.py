from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.rebuild.models import SiteRebuild
from apps.rebuild.serializers import SiteRebuildCreateSerializer, SiteRebuildSerializer
from apps.rebuild.tasks import run_site_rebuild
from apps.scans.models import Page


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

        rebuild = SiteRebuild.objects.create(scan_job=page.scan_job, page=page)
        run_site_rebuild.delay(rebuild.pk)
        return Response(
            SiteRebuildSerializer(rebuild).data, status=status.HTTP_201_CREATED
        )

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
