from rest_framework import serializers
from .models import (
    SiteSettings, HomeContent, ProductPageContent,
    DownloadPageContent, DownloadFeature, DownloadStep,
    PurchasePageContent, TeamPageContent, AppServerConfig,
    ImpactFeedback, AppAnnouncement, AnnouncementTag,
)


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        exclude = ('id',)


class HomeContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeContent
        exclude = ('id',)


class ProductPageContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPageContent
        exclude = ('id',)


class DownloadFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = DownloadFeature
        fields = ('id', 'icon_svg', 'title', 'description', 'order')


class DownloadStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = DownloadStep
        fields = ('id', 'step_number', 'title', 'description', 'order')


class DownloadPageContentSerializer(serializers.ModelSerializer):
    features = serializers.SerializerMethodField()
    steps = serializers.SerializerMethodField()

    class Meta:
        model = DownloadPageContent
        exclude = ('id',)

    def get_features(self, obj):
        return DownloadFeatureSerializer(DownloadFeature.objects.all(), many=True).data

    def get_steps(self, obj):
        return DownloadStepSerializer(DownloadStep.objects.all(), many=True).data


class PurchasePageContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchasePageContent
        exclude = ('id',)


class TeamPageContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamPageContent
        exclude = ('id',)


class AppServerConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppServerConfig
        exclude = ('id',)


class ImpactFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ImpactFeedback
        fields = ('id', 'magnitude', 'outcome', 'is_false_positive', 'note', 'created_at')


class AnnouncementTagSerializer(serializers.ModelSerializer):
    """公告標籤序列化器"""
    class Meta:
        model = AnnouncementTag
        fields = ('id', 'name', 'slug', 'color', 'created_at')


class AppAnnouncementSerializer(serializers.ModelSerializer):
    """公告序列化器（支援標籤關聯）"""
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    # 可寫入的標籤欄位（接收 ID 陣列）
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=AnnouncementTag.objects.all(),
        required=False
    )
    # 讀取時回傳完整標籤資料
    tags_detail = AnnouncementTagSerializer(source='tags', many=True, read_only=True)

    class Meta:
        model  = AppAnnouncement
        fields = ('id', 'title', 'body', 'type', 'type_display',
                  'is_active', 'scheduled_at', 'tags', 'tags_detail',
                  'show_on_website', 'created_at', 'updated_at')
