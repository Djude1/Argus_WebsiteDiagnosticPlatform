"""
頁面內容管理後台 API
"""
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.permissions import IsStaff
from analytics.utils import log_activity
from .models import (
    SiteSettings, HomeContent, ProductPageContent,
    DownloadPageContent, DownloadFeature, DownloadStep,
    PurchasePageContent, TeamPageContent, AppServerConfig,
    ImpactFeedback, AppAnnouncement,
)
from .serializers import (
    SiteSettingsSerializer, HomeContentSerializer,
    ProductPageContentSerializer, DownloadPageContentSerializer,
    DownloadFeatureSerializer, DownloadStepSerializer,
    PurchasePageContentSerializer, TeamPageContentSerializer,
    AppServerConfigSerializer, ImpactFeedbackSerializer,
    AppAnnouncementSerializer,
)

# 對應 section 名稱 → (模型類別, 序列化器, 顯示名稱)
SECTION_MAP = {
    'site':       (SiteSettings,       SiteSettingsSerializer,       '全站設定'),
    'home':       (HomeContent,        HomeContentSerializer,        '首頁'),
    'product':    (ProductPageContent, ProductPageContentSerializer, '產品介紹頁'),
    'download':   (DownloadPageContent,DownloadPageContentSerializer,'APP 下載頁'),
    'purchase':   (PurchasePageContent,PurchasePageContentSerializer,'購買頁'),
    'team':       (TeamPageContent,    TeamPageContentSerializer,    '團隊頁'),
    'app-config': (AppServerConfig,    AppServerConfigSerializer,    'APP 伺服器設定'),
}


class AdminContentSectionView(APIView):
    """統一處理所有 Singleton 頁面內容的讀取與更新"""
    permission_classes = [IsStaff]

    def get(self, request, section):
        if section not in SECTION_MAP:
            return Response({'error': '無效的頁面區塊'}, status=status.HTTP_404_NOT_FOUND)
        model_cls, serializer_cls, _ = SECTION_MAP[section]
        return Response(serializer_cls(model_cls.load()).data)

    def patch(self, request, section):
        if section not in SECTION_MAP:
            return Response({'error': '無效的頁面區塊'}, status=status.HTTP_404_NOT_FOUND)
        model_cls, serializer_cls, display_name = SECTION_MAP[section]
        obj = model_cls.load()
        serializer = serializer_cls(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_activity(request, 'update', '頁面內容', 1, display_name)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminDownloadFeatureListView(generics.ListCreateAPIView):
    permission_classes = [IsStaff]
    serializer_class = DownloadFeatureSerializer
    queryset = DownloadFeature.objects.all()

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(self.request, 'create', 'APP 功能特色',
                     serializer.instance.id, serializer.instance.title)


class AdminDownloadFeatureDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsStaff]
    serializer_class = DownloadFeatureSerializer
    queryset = DownloadFeature.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(self.request, 'update', 'APP 功能特色',
                     serializer.instance.id, serializer.instance.title)

    def perform_destroy(self, instance):
        log_activity(self.request, 'delete', 'APP 功能特色', instance.id, instance.title)
        instance.delete()


class AdminDownloadStepListView(generics.ListCreateAPIView):
    permission_classes = [IsStaff]
    serializer_class = DownloadStepSerializer
    queryset = DownloadStep.objects.all()

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(self.request, 'create', '安裝步驟',
                     serializer.instance.id, serializer.instance.title)


class AdminDownloadStepDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsStaff]
    serializer_class = DownloadStepSerializer
    queryset = DownloadStep.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(self.request, 'update', '安裝步驟',
                     serializer.instance.id, serializer.instance.title)

    def perform_destroy(self, instance):
        log_activity(self.request, 'delete', '安裝步驟', instance.id, instance.title)
        instance.delete()


class AdminAnnouncementListView(generics.ListCreateAPIView):
    """APP 公告列表 + 新增"""
    permission_classes = [IsStaff]
    serializer_class   = AppAnnouncementSerializer
    queryset           = AppAnnouncement.objects.all()

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(self.request, 'create', 'APP 公告',
                     serializer.instance.id, serializer.instance.title)


class AdminAnnouncementDetailView(generics.RetrieveUpdateDestroyAPIView):
    """APP 公告單筆讀取 + 更新 + 刪除"""
    permission_classes = [IsStaff]
    serializer_class   = AppAnnouncementSerializer
    queryset           = AppAnnouncement.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(self.request, 'update', 'APP 公告',
                     serializer.instance.id, serializer.instance.title)

    def perform_destroy(self, instance):
        log_activity(self.request, 'delete', 'APP 公告', instance.id, instance.title)
        instance.delete()


class AdminImpactFeedbackView(generics.ListAPIView):
    """管理員查詢撞擊回饋記錄（最新在前）"""
    permission_classes = [IsStaff]
    serializer_class   = ImpactFeedbackSerializer

    def get_queryset(self):
        qs = ImpactFeedback.objects.all()
        # 支援 ?false_only=1 只看誤判
        if self.request.query_params.get('false_only'):
            qs = qs.filter(is_false_positive=True)
        return qs

    def list(self, request, *args, **kwargs):
        qs       = self.get_queryset()
        total    = qs.count()
        false_ct = qs.filter(is_false_positive=True).count()
        serializer = self.get_serializer(qs[:100], many=True)
        return Response({
            'total':          total,
            'false_positive': false_ct,
            'records':        serializer.data,
        })
