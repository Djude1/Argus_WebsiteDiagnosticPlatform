from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import (
    SiteSettings, HomeContent, ProductPageContent,
    DownloadPageContent, PurchasePageContent, TeamPageContent,
    AppServerConfig,
)
from .serializers import (
    SiteSettingsSerializer, HomeContentSerializer,
    ProductPageContentSerializer, DownloadPageContentSerializer,
    PurchasePageContentSerializer, TeamPageContentSerializer,
    AppServerConfigSerializer,
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
            'server_url': config.server_url,
            'note':       config.note,
            'updated_at': config.updated_at,
        })
