from config.throttling import UserRateThrottle
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from apps.content.models import AppRelease, ProjectFeature, ProjectMilestone, TeamMember
from apps.content.serializers import (
    AppReleaseSerializer,
    PartnerInquiryCreateSerializer,
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


class PartnerInquiryThrottle(UserRateThrottle):
    """洽談表單專屬額度（`partner_inquiry` scope）；登入與否都計（登入者以帳號、訪客以 IP）。"""

    scope = "partner_inquiry"


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([PartnerInquiryThrottle])
def partner_inquiry_create(request):
    """公開的商業合作洽談表單（/partners）。"""
    serializer = PartnerInquiryCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    ok = {"detail": "已收到你的洽談需求，我們會以 Email 與你聯繫。"}
    # 誘餌欄位有值＝機器人：回同樣的成功訊息但不寫入，不讓對方知道被擋
    if serializer.validated_data.get("website"):
        return Response(ok, status=status.HTTP_201_CREATED)
    serializer.save()
    return Response(ok, status=status.HTTP_201_CREATED)
