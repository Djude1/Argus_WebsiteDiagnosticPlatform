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
    """

    class Meta(SiteRebuildSerializer.Meta):
        fields = [*SiteRebuildSerializer.Meta.fields, "trace", "edit_report"]
        read_only_fields = fields


class SiteRebuildCreateSerializer(serializers.Serializer):
    page = serializers.IntegerField()
