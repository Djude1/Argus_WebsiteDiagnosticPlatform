from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Q
from django.utils import timezone
from .models import (
    SiteSettings, HomeContent, ProductPageContent,
    DownloadPageContent, PurchasePageContent, TeamPageContent,
    AppServerConfig, ImpactFeedback, AppAnnouncement,
)
from .serializers import (
    SiteSettingsSerializer, HomeContentSerializer,
    ProductPageContentSerializer, DownloadPageContentSerializer,
    PurchasePageContentSerializer, TeamPageContentSerializer,
    AppServerConfigSerializer, ImpactFeedbackSerializer,
    AppAnnouncementSerializer,
)


class SiteContentView(APIView):
    """回傳所有網站內容，按頁面分組"""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'site': SiteSettingsSerializer(SiteSettings.load()).data,
            'home': HomeContentSerializer(HomeContent.load()).data,
            'product': ProductPageContentSerializer(ProductPageContent.load()).data,
            'download': DownloadPageContentSerializer(DownloadPageContent.load()).data,
            'purchase': PurchasePageContentSerializer(PurchasePageContent.load()).data,
            'team': TeamPageContentSerializer(TeamPageContent.load()).data,
        })


class AppConfigView(APIView):
    """APP 啟動時讀取 AI 伺服器 URL（公開，不需認證）"""
    permission_classes = [AllowAny]

    def get(self, request):
        config = AppServerConfig.load()
        return Response({
            'server_url':    config.server_url,
            'support_phone': config.support_phone,
            'note':          config.note,
            'updated_at':    config.updated_at,
        })


class AppAnnouncementsView(APIView):
    """APP 啟動時讀取有效公告（公開，不需認證）"""
    permission_classes = [AllowAny]

    def get(self, request):
        now = timezone.now()
        qs = AppAnnouncement.objects.filter(
            is_active=True
        ).filter(
            Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=now)
        )
        serializer = AppAnnouncementSerializer(qs, many=True)
        return Response({'announcements': serializer.data})


class ImpactFeedbackCreateView(APIView):
    """APP 回報撞擊偵測結果（是否誤判），公開端點不需認證"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ImpactFeedbackSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'ok': True}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WebsiteAnnouncementsView(generics.ListAPIView):
    """
    前台網站公告列表 API
    - 僅顯示 is_active=True 且 show_on_website=True 的公告
    - 支援標籤篩選：?tag=<slug>
    """
    serializer_class = AppAnnouncementSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        now = timezone.now()
        qs = AppAnnouncement.objects.filter(
            is_active=True,
            show_on_website=True
        ).filter(
            Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=now)
        )
        tag_slug = self.request.query_params.get('tag')
        if tag_slug:
            qs = qs.filter(tags__slug=tag_slug)
        return qs.prefetch_related('tags').order_by('-created_at').distinct()
