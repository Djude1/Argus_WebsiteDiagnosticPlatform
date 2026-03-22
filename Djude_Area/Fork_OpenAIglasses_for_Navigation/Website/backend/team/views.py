"""
團隊成員 API 視圖
"""
from rest_framework import generics
from rest_framework.permissions import AllowAny
from .models import TeamMember
from .serializers import TeamMemberSerializer


class TeamMemberListView(generics.ListAPIView):
    """取得所有團隊成員（公開）"""
    permission_classes = [AllowAny]
    serializer_class = TeamMemberSerializer

    def get_queryset(self):
        qs = TeamMember.objects.filter(is_active=True)
        member_type = self.request.query_params.get('type')
        if member_type:
            qs = qs.filter(member_type=member_type)
        return qs
