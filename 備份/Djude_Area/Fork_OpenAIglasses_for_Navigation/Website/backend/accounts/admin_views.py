"""
帳號管理後台 API（僅超級管理員可操作）
"""
from rest_framework import generics, serializers as drf_serializers
from .models import CustomUser
from .permissions import IsAdmin
from analytics.utils import log_activity


class AdminUserSerializer(drf_serializers.ModelSerializer):
    """帳號序列化器，包含功能權限欄位"""
    password = drf_serializers.CharField(write_only=True, required=False, allow_blank=True)
    permissions = drf_serializers.JSONField(required=False, default=list)

    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name',
                  'role', 'permissions', 'bio', 'password', 'is_active', 'date_joined')
        read_only_fields = ('date_joined',)

    def create(self, validated_data):
        password = validated_data.pop('password', '')
        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminUserListView(generics.ListCreateAPIView):
    """帳號列表與新增（僅超級管理員）"""
    permission_classes = [IsAdmin]
    serializer_class = AdminUserSerializer
    queryset = CustomUser.objects.all().order_by('-date_joined')

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(self.request, 'create', '帳號',
                     serializer.instance.id, serializer.instance.username)


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """帳號詳情、修改、刪除（僅超級管理員）"""
    permission_classes = [IsAdmin]
    serializer_class = AdminUserSerializer
    queryset = CustomUser.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(self.request, 'update', '帳號',
                     serializer.instance.id, serializer.instance.username)

    def perform_destroy(self, instance):
        log_activity(self.request, 'delete', '帳號', instance.id, instance.username)
        instance.delete()
