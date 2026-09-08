from rest_framework import serializers

from apps.rebuild.models import SiteRebuild


class SiteRebuildSerializer(serializers.ModelSerializer):
    page_url = serializers.CharField(source="page.final_url", read_only=True)
    has_snapshot = serializers.SerializerMethodField()
    has_optimized = serializers.SerializerMethodField()

    class Meta:
        model = SiteRebuild
        # 明確白名單。opencode_session_id 與 cost_usd 是維運資訊，不對外送。
        fields = [
            "id",
            "scan_job",
            "page",
            "page_url",
            "status",
            "has_snapshot",
            "has_optimized",
            "coins_charged",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_snapshot(self, obj) -> bool:
        return bool(obj.snapshot_path)

    def get_has_optimized(self, obj) -> bool:
        return bool(obj.optimized_path)


class SiteRebuildDetailSerializer(SiteRebuildSerializer):
    """單筆檢視才帶 trace。

    思考流可以到上百 KB，而列表端點會被每秒 polling——放進 list 等於每次都
    把所有紀錄的思考流一起撈出來。

    `trace` 只有**進行中那一輪**的思考流。已結束的每一輪把自己的思考流歸檔在
    conversation 裡，但**不隨這個端點送出**：detail 在執行期間同樣每秒被 polling，
    20 輪 × 單輪上限傳出去等於每秒好幾 MB。改成只送 has_trace 旗標，使用者真的
    展開某一輪時再用 turn-trace 端點取。
    """

    conversation = serializers.SerializerMethodField()

    class Meta(SiteRebuildSerializer.Meta):
        fields = [
            *SiteRebuildSerializer.Meta.fields,
            "trace",
            "edit_report",
            "reply",
            "conversation",
        ]
        read_only_fields = fields

    def get_conversation(self, obj) -> list[dict]:
        return [
            {
                "role": turn.get("role", "agent"),
                "text": turn.get("text", ""),
                "has_trace": bool(turn.get("trace")),
            }
            for turn in (obj.conversation or [])
        ]


class SiteRebuildCreateSerializer(serializers.Serializer):
    page = serializers.IntegerField()
