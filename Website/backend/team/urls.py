"""
團隊成員 URL 路由
"""
from django.urls import path
from .views import TeamMemberListView

urlpatterns = [
    path('', TeamMemberListView.as_view(), name='team-list'),
]
