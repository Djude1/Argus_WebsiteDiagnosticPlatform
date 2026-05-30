"""
公開流量追蹤 API（前端 SPA 主動上報頁面瀏覽）
+ APP 端路口停等事件群眾外包 API
"""
from datetime import timedelta, timezone as dt_timezone

from django.db.models import Avg, Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ActiveWaiter, IntersectionWaitEvent, PageView
from .utils import latlng_to_grid_id


# ── 隱私 L2 與健全性常數 ────────────────────────────────────────────────────
COORD_DECIMALS = 5          # 經緯度上傳上限位數（11m 精度）
DEVICE_HASH_LEN = 64        # SHA-256 hex 長度
MIN_WAIT_SEC = 3            # 太短的停等視為雜訊，不收
MAX_WAIT_SEC = 600          # 10 分鐘以上視為異常，不收
ACTIVE_WINDOW_SEC = 30      # 視為「目前還在等」的時間窗
INFO_LOOKBACK_DAYS = 30     # 平均停等只看近 30 天
DURATION_TOLERANCE_SEC = 5  # duration_sec 與 (ended_at - started_at) 容差


def _quantize(value):
    """把字串/數字統一轉成 float 並 round 到 5 位（多一層 server side defense）"""
    try:
        return round(float(value), COORD_DECIMALS)
    except (TypeError, ValueError):
        return None


def _valid_device(h):
    return isinstance(h, str) and len(h) == DEVICE_HASH_LEN


def _parse_iso(value):
    """安全 parse ISO8601 → aware datetime；失敗回 None。"""
    if not isinstance(value, str):
        return None
    try:
        dt = parse_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_timezone.utc)
    return dt


class TrackPageView(APIView):
    """接收前端上報的頁面瀏覽事件（無需認證）"""
    permission_classes = [AllowAny]

    def post(self, request):
        path = request.data.get('path', '').strip()
        if path and len(path) <= 500:
            ip_raw = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            ip = ip_raw.split(',')[0].strip() if ip_raw else None
            PageView.objects.create(
                path=path,
                ip_address=ip or None,
                referer=request.META.get('HTTP_REFERER', '')[:500],
            )
        return Response({'ok': True})


class IntersectionWaitReportView(APIView):
    """APP 結束停等時上傳一筆事件

    body: { lat, lng, duration_sec, device_hash, started_at(ISO8601), ended_at(ISO8601) }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        lat = _quantize(request.data.get('lat'))
        lng = _quantize(request.data.get('lng'))
        duration = request.data.get('duration_sec')
        device_hash = request.data.get('device_hash')
        started_at_raw = request.data.get('started_at')
        ended_at_raw = request.data.get('ended_at')

        if lat is None or lng is None:
            return Response({'ok': False, 'error': 'invalid_coords'}, status=400)
        if not _valid_device(device_hash):
            return Response({'ok': False, 'error': 'invalid_device'}, status=400)
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            return Response({'ok': False, 'error': 'invalid_duration'}, status=400)
        if not (MIN_WAIT_SEC <= duration <= MAX_WAIT_SEC):
            return Response({'ok': False, 'error': 'duration_out_of_range'}, status=400)

        # ISO8601 解析：失敗或不一致即拒收，避免惡意 client 灌假時序
        now = timezone.now()
        started_at = _parse_iso(started_at_raw) if started_at_raw else now
        ended_at = _parse_iso(ended_at_raw) if ended_at_raw else now
        if started_at is None or ended_at is None:
            return Response({'ok': False, 'error': 'invalid_timestamp'}, status=400)
        if started_at > ended_at:
            return Response({'ok': False, 'error': 'started_after_ended'}, status=400)
        # duration_sec 與時間差異常：容忍 ±5 秒（client 計時與 wall clock 微差）
        actual = (ended_at - started_at).total_seconds()
        if abs(actual - duration) > DURATION_TOLERANCE_SEC:
            return Response({'ok': False, 'error': 'duration_mismatch'}, status=400)

        grid_id = latlng_to_grid_id(lat, lng)
        IntersectionWaitEvent.objects.create(
            grid_id=grid_id,
            lat=lat,
            lng=lng,
            duration_sec=duration,
            device_hash=device_hash,
            started_at=started_at,
            ended_at=ended_at,
        )
        # 結束停等 → 清掉這台在這格的 active 標記
        ActiveWaiter.objects.filter(grid_id=grid_id, device_hash=device_hash).delete()
        return Response({'ok': True, 'grid_id': grid_id})


class IntersectionHeartbeatView(APIView):
    """APP 仍在停等中，每 N 秒打一次標記自己還活著

    body: { lat, lng, device_hash }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        lat = _quantize(request.data.get('lat'))
        lng = _quantize(request.data.get('lng'))
        device_hash = request.data.get('device_hash')

        if lat is None or lng is None:
            return Response({'ok': False, 'error': 'invalid_coords'}, status=400)
        if not _valid_device(device_hash):
            return Response({'ok': False, 'error': 'invalid_device'}, status=400)

        grid_id = latlng_to_grid_id(lat, lng)
        ActiveWaiter.objects.update_or_create(
            grid_id=grid_id,
            device_hash=device_hash,
            defaults={'last_seen_at': timezone.now()},
        )
        return Response({'ok': True, 'grid_id': grid_id})


class IntersectionInfoView(APIView):
    """查詢某個位置所在路口的彙整資訊

    query: ?lat=&lng=
    回 { grid_id, avg_duration_sec, sample_size, active_count }
    """
    permission_classes = [AllowAny]

    def get(self, request):
        lat = _quantize(request.query_params.get('lat'))
        lng = _quantize(request.query_params.get('lng'))
        if lat is None or lng is None:
            return Response({'ok': False, 'error': 'invalid_coords'}, status=400)

        grid_id = latlng_to_grid_id(lat, lng)
        since = timezone.now() - timedelta(days=INFO_LOOKBACK_DAYS)
        agg = IntersectionWaitEvent.objects.filter(
            grid_id=grid_id, ended_at__gte=since,
        ).aggregate(avg=Avg('duration_sec'), n=Count('id'))

        active_threshold = timezone.now() - timedelta(seconds=ACTIVE_WINDOW_SEC)
        active = ActiveWaiter.objects.filter(
            grid_id=grid_id, last_seen_at__gte=active_threshold,
        ).count()

        avg = agg['avg']
        return Response({
            'ok': True,
            'grid_id': grid_id,
            'avg_duration_sec': round(avg, 1) if avg is not None else None,
            'sample_size': agg['n'] or 0,
            'active_count': active,
        })
