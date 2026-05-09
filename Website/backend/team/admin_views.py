"""
團隊成員管理後台 API
"""
from rest_framework import generics
from .models import TeamMember
from .serializers import TeamMemberSerializer
from accounts.permissions import IsStaff
from analytics.utils import log_activity


class AdminTeamListView(generics.ListCreateAPIView):
    permission_classes = [IsStaff]
    serializer_class = TeamMemberSerializer
    queryset = TeamMember.objects.all()

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(self.request, 'create', '團隊成員',
                     serializer.instance.id, serializer.instance.name)


class AdminTeamDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsStaff]
    serializer_class = TeamMemberSerializer
    queryset = TeamMember.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_activity(self.request, 'update', '團隊成員',
                     serializer.instance.id, serializer.instance.name)

    def perform_destroy(self, instance):
        log_activity(self.request, 'delete', '團隊成員', instance.id, instance.name)
        instance.delete()
