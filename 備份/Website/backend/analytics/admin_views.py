"""
後台分析資料 API（需登入）
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from .models import PageView, AdminActivity
from accounts.permissions import IsStaff
from orders.models import OrderItem

ACTION_DISPLAY = {'create': '新增', 'update': '修改', 'delete': '刪除'}


class AdminTrafficView(APIView):
    """流量統計：摘要數字 + 每日趨勢 + 熱門頁面"""
    permission_classes = [IsStaff]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start  = today_start - timedelta(days=6)
        month_start = today_start - timedelta(days=29)

        total = PageView.objects.count()
        # 今日瀏覽：以獨立 IP 計算，同一 IP 只算一次
        today = (
            PageView.objects
            .filter(timestamp__gte=today_start)
            .exclude(ip_address=None)
            .values('ip_address')
            .distinct()
            .count()
        )
        week  = PageView.objects.filter(timestamp__gte=week_start).count()
        month = PageView.objects.filter(timestamp__gte=month_start).count()

        # 過去 14 天每日流量（每日以獨立 IP 計算）
        daily_qs = (
            PageView.objects
            .filter(timestamp__gte=today_start - timedelta(days=13))
            .exclude(ip_address=None)
            .annotate(date=TruncDate('timestamp'))
            .values('date')
            .annotate(count=Count('ip_address', distinct=True))
            .order_by('date')
        )
        daily = [{'date': str(d['date']), 'count': d['count']} for d in daily_qs]

        # 熱門頁面 Top 10
        top_pages = list(
            PageView.objects
            .values('path')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        # 各商品銷售統計（購買次數 = 訂單明細筆數，總數量 = 實際購買件數）
        product_sales = list(
            OrderItem.objects
            .values('product__id', 'product__name')
            .annotate(
                order_count=Count('id'),
                total_qty=Sum('quantity'),
            )
            .order_by('-total_qty')
        )

        return Response({
            'summary': {'total': total, 'today': today, 'week': week, 'month': month},
            'daily': daily,
            'top_pages': top_pages,
            'product_sales': [
                {
                    'id': p['product__id'],
                    'name': p['product__name'],
                    'order_count': p['order_count'],
                    'total_qty': p['total_qty'],
                }
                for p in product_sales
            ],
        })


class AdminActivityLogView(APIView):
    """後台操作日誌（最近 200 筆）"""
    permission_classes = [IsStaff]

    def get(self, request):
        action_filter = request.query_params.get('action', '')
        qs = AdminActivity.objects.select_related('user').order_by('-timestamp')
        if action_filter:
            qs = qs.filter(action=action_filter)
        qs = qs[:200]

        data = [{
            'id': l.id,
            'user': l.user.username if l.user else '系統',
            'action': l.action,
            'action_display': ACTION_DISPLAY.get(l.action, l.action),
            'resource_type': l.resource_type,
            'resource_id': l.resource_id,
            'resource_name': l.resource_name,
            'timestamp': l.timestamp.isoformat(),
        } for l in qs]

        return Response(data)
