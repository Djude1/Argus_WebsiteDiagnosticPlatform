from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.content.models import AppRelease, ProjectFeature, ProjectMilestone, TeamMember
from apps.content.serializers import (
    AppReleaseSerializer,
    ProjectFeatureSerializer,
    ProjectMilestoneSerializer,
    TeamMemberSerializer,
)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def features_list(request):
    qs = ProjectFeature.objects.filter(is_active=True).order_by("sort_order", "id")
    return Response({"features": ProjectFeatureSerializer(qs, many=True).data})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def team_list(request):
    qs = TeamMember.objects.filter(is_active=True).order_by("sort_order", "id")
    return Response({"members": TeamMemberSerializer(qs, many=True).data})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def releases_list(request):
    qs = AppRelease.objects.filter(is_active=True).order_by("-released_at")
    return Response({"releases": AppReleaseSerializer(qs, many=True).data})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def milestones_list(request):
    qs = ProjectMilestone.objects.filter(is_active=True).order_by("sort_order", "-date")
    return Response({"milestones": ProjectMilestoneSerializer(qs, many=True).data})
