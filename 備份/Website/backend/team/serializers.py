"""
團隊成員序列化器
"""
from rest_framework import serializers
from .models import TeamMember


class TeamMemberSerializer(serializers.ModelSerializer):
    member_type_display = serializers.CharField(source='get_member_type_display', read_only=True)

    class Meta:
        model = TeamMember
        fields = (
            'id', 'name', 'member_type', 'member_type_display',
            'role', 'bio', 'avatar',
            'github_url', 'linkedin_url', 'email', 'order'
        )
