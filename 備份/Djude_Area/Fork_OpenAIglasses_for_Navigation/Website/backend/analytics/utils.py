"""
後台操作日誌工具函式 + 路口網格化工具
"""


def log_activity(request, action, resource_type, resource_id=None, resource_name=''):
    """記錄後台操作日誌"""
    from .models import AdminActivity
    user = request.user if request.user.is_authenticated else None
    AdminActivity.objects.create(
        user=user,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
    )


# ── 路口網格化 ──────────────────────────────────────────────────────────────
# 沒有高德路口資料時，用 30m × 30m 方格代替「路口」
# 緯度 0.0003° ≈ 33m，經度 0.0003° ≈ 30m @ 北緯 25°（台灣）
GRID_SCALE = 3000  # round(lat * 3000) 等同切成 1/3000° 方格


def latlng_to_grid_id(lat, lng):
    """把 (lat, lng) 量化成 30m 方格 ID 字串。

    回傳形如 "75312_363192" 的字串（整數對），可當資料庫 index key。
    """
    lat_q = round(float(lat) * GRID_SCALE)
    lng_q = round(float(lng) * GRID_SCALE)
    return f'{lat_q}_{lng_q}'
