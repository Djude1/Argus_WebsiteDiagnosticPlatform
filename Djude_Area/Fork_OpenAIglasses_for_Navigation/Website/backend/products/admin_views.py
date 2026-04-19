"""
商品管理後台 API
"""

from rest_framework import generics, serializers as drf_serializers
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Product, ProductFeature, ProductSpec
from accounts.permissions import IsStaff, IsAdmin
from analytics.utils import log_activity


class AdminProductFileSerializer(drf_serializers.ModelSerializer):
    """僅用於上傳 image / model_3d 檔案（multipart）"""

    class Meta:
        model = Product
        fields = ("id", "image", "model_3d")


class AdminFeatureSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = ProductFeature
        fields = ("id", "product", "title", "description", "icon", "order")


class AdminSpecSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = ProductSpec
        fields = ("id", "product", "key", "value", "order")


class AdminProductSerializer(drf_serializers.ModelSerializer):
    features = AdminFeatureSerializer(many=True, read_only=True)
    specs = AdminSpecSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "short_description",
            "description",
            "price",
            "original_price",
            "stock",
            "is_active",
            "image",
            "model_3d",
            "camera_height",
            "features",
            "specs",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at", "image", "model_3d")


class AdminProductListView(generics.ListCreateAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminProductSerializer
    queryset = Product.objects.prefetch_related("features", "specs").all()

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(
            self.request,
            "create",
            "商品",
            serializer.instance.id,
            serializer.instance.name,
        )


class AdminProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminProductSerializer
    queryset = Product.objects.prefetch_related("features", "specs").all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(
            self.request,
            "update",
            "商品",
            serializer.instance.id,
            serializer.instance.name,
        )

    def perform_destroy(self, instance):
        log_activity(self.request, "delete", "商品", instance.id, instance.name)
        instance.delete()


class AdminProductFileUploadView(generics.UpdateAPIView):
    """上傳商品圖片或 3D 模型（multipart/form-data）"""

    permission_classes = [IsStaff]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = AdminProductFileSerializer
    queryset = Product.objects.all()
    http_method_names = ["patch"]

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(
            self.request,
            "update",
            "商品檔案",
            serializer.instance.id,
            serializer.instance.name,
        )


class AdminFeatureListView(generics.ListCreateAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminFeatureSerializer

    def get_queryset(self):
        return ProductFeature.objects.filter(product_id=self.kwargs["product_id"])

    def perform_create(self, serializer):
        serializer.save(product_id=self.kwargs["product_id"])
        log_activity(
            self.request,
            "create",
            "商品功能",
            serializer.instance.id,
            serializer.instance.title,
        )


class AdminFeatureDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminFeatureSerializer
    queryset = ProductFeature.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(
            self.request,
            "update",
            "商品功能",
            serializer.instance.id,
            serializer.instance.title,
        )

    def perform_destroy(self, instance):
        log_activity(self.request, "delete", "商品功能", instance.id, instance.title)
        instance.delete()


class AdminSpecListView(generics.ListCreateAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminSpecSerializer

    def get_queryset(self):
        return ProductSpec.objects.filter(product_id=self.kwargs["product_id"])

    def perform_create(self, serializer):
        serializer.save(product_id=self.kwargs["product_id"])
        log_activity(
            self.request,
            "create",
            "商品規格",
            serializer.instance.id,
            serializer.instance.key,
        )


class AdminSpecDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminSpecSerializer
    queryset = ProductSpec.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(
            self.request,
            "update",
            "商品規格",
            serializer.instance.id,
            serializer.instance.key,
        )

    def perform_destroy(self, instance):
        log_activity(self.request, "delete", "商品規格", instance.id, instance.key)
        instance.delete()
