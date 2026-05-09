"""
公開流量追蹤 API（前端 SPA 主動上報頁面瀏覽）
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import PageView


class TrackPageView(APIView):
    """接收前端上報的頁面瀏覽事件（無需認證）"""
    permission_classes = [AllowAny]

    def post(self, request):
        path = request.data.get('path', '').strip()
        if path and len(path) <= 500:
            # 取得真實 IP（考慮 Nginx 代理）
            ip_raw = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            ip = ip_raw.split(',')[0].strip() if ip_raw else None
            PageView.objects.create(
                path=path,
                ip_address=ip or None,
                referer=request.META.get('HTTP_REFERER', '')[:500],
            )
        return Response({'ok': True})
