"""admin_api 的 OpenAPI schema 標註工具。

admin_api 全部是 function-based view（`@api_view`），drf-spectacular 推導不出
回傳內容，產出的 OpenAPI 端點會是空的 `content`，前端因此拿不到任何型別——
而後台正是先前兩次「靜默失效」發生的地方（`?user=` 沒宣告、`user_id` 沒進
serializer，畫面都照常顯示，只是結果是錯的）。

這裡把「分頁信封」與「列表查詢參數」集中成一個 `list_schema()`，讓每個列表
端點只需要加一行裝飾器，回傳結構與可用的查詢參數就會進 schema，前端型別即可
從它生成。
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers

from apps.admin_api.serializers import AdminScanJobSerializer, AdminUserDetailSerializer


def ordering_param(allowed: dict) -> OpenApiParameter:
    """把 `_apply_ordering` 的白名單轉成 schema 的 enum（含 `-` 降冪形式）。"""
    keys = sorted(allowed)
    return OpenApiParameter(
        name="ordering",
        type=str,
        description="排序欄位；前綴 `-` 為降冪。不在白名單時回退預設排序。",
        enum=[*keys, *(f"-{k}" for k in keys)],
    )


def query_param(name: str, description: str, *, type_=str, enum=None) -> OpenApiParameter:
    return OpenApiParameter(name=name, type=type_, description=description, enum=enum)


def list_schema(*, name: str, key: str, child, ordering: dict | None = None,
                filters=(), extra_fields=None, description: str = ""):
    """列表端點的 `@extend_schema`：回傳 `{<key>: [...], page, total_pages, total}`。

    `extra_fields` 給有額外統計欄位的端點（例如評論列表的待審／檢舉計數）。

    `name` 一律用 `…Response` 結尾：drf-spectacular 會把 serializer 名稱的
    `Serializer` 後綴去掉，`AdminUserListSerializer` 就變成 `AdminUserList`，
    與信封同名時後者會覆蓋前者，陣列元素的 `$ref` 會指回信封自己（型別變成
    無意義的遞迴結構，而且不會報錯）。
    """
    params = [
        OpenApiParameter(
            name="page",
            type=int,
            description="頁碼，從 1 起算；超過總頁數時取最後一頁。",
        ),
        *([ordering_param(ordering)] if ordering else []),
        *filters,
    ]
    fields = {
        key: child(many=True),
        "page": serializers.IntegerField(),
        "total_pages": serializers.IntegerField(),
        "total": serializers.IntegerField(),
        **(extra_fields or {}),
    }
    return extend_schema(
        parameters=params,
        responses=inline_serializer(name=name, fields=fields),
        description=description or None,
    )


# ---- 文件用 serializer：只描述回傳結構給 OpenAPI，不參與實際序列化 ----
#
# user_detail 在 AdminUserDetailSerializer 的輸出上再附加三個欄位（見 views.py），
# serializer 本身描述不到，所以在這裡補一個「完整回傳長什麼樣」的描述。
# 改 views.py::user_detail 附加的欄位時，這裡要一起改（契約測試會提醒）。

class AdminAiUsageByProviderSerializer(serializers.Serializer):
    provider = serializers.CharField()
    model = serializers.CharField()
    sessions = serializers.IntegerField()
    tokens = serializers.IntegerField()


class AdminAiUsageSerializer(serializers.Serializer):
    total_tokens = serializers.IntegerField()
    total_sessions = serializers.IntegerField()
    by_provider = AdminAiUsageByProviderSerializer(many=True)


class AdminUserDetailResponseSerializer(AdminUserDetailSerializer):
    ai_usage = AdminAiUsageSerializer()
    recent_scans = AdminScanJobSerializer(many=True, help_text="最近 10 筆")
    scans_total = serializers.IntegerField()
