"""
帳號序列化器
"""
from rest_framework import serializers
from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    """登入使用者資料（含功能權限，供前端側欄判斷）"""
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name',
                  'role', 'permissions', 'avatar', 'bio', 'is_superuser')
        read_only_fields = ('role', 'permissions')


class UserProfileSerializer(serializers.ModelSerializer):
    """個人資料（僅顯示公開資訊）"""
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'first_name', 'last_name', 'role', 'avatar')
