from django.db.models import Q
from rest_framework import serializers

from apps.rebuild.models import SiteRebuild
from apps.scans.models import Finding

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_EDIT_FIELDS = ("why", "applied", "rejected", "layer", "category", "impact")


def page_findings(rebuild: SiteRebuild, limit: int = 40) -> list[dict]:
    """這一頁（含站台層級）在掃描中發現的問題：結果頁「發現的問題」一欄。

    只給標題、嚴重度、分類，不帶證據——分享頁是公開的，證據可能含個資。
    """
    rows = (
        Finding.objects.filter(scan_job_id=rebuild.scan_job_id)
        .filter(Q(page_id=rebuild.page_id) | Q(page__isnull=True))
        .values("title", "severity", "category")
    )
    seen, out = set(), []
    for row in sorted(rows, key=lambda r: _SEVERITY_ORDER.get(r["severity"], 9)):
        key = (row["title"], row["category"])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out[:limit]


def public_edits(rebuild: SiteRebuild) -> list[dict]:
    """修改清單的公開欄位；不含 find 原文（那是頁面原始碼片段）。"""
    return [
        {field: item.get(field, "" if field != "applied" else 0) for field in _EDIT_FIELDS}
        for item in rebuild.edit_report or []
    ]


class SiteRebuildSerializer(serializers.ModelSerializer):
    page_url = serializers.CharField(source="page.final_url", read_only=True)
    has_snapshot = serializers.SerializerMethodField()
    has_optimized = serializers.SerializerMethodField()
    share_path = serializers.SerializerMethodField()
    share_active = serializers.SerializerMethodField()
    result_summary = serializers.SerializerMethodField()

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
            "share_path",
            "share_access",
            "share_active",
            "share_expires_at",
            "result_summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_snapshot(self, obj) -> bool:
        return bool(obj.snapshot_path)

    def get_has_optimized(self, obj) -> bool:
        return bool(obj.optimized_path)

    def get_share_path(self, obj) -> str:
        """穩定的分享網址（只回給擁有者；queryset 已限定本人）。

        第一次分享後就固定不變，關閉分享時仍回同一個路徑，前端據 share_active 顯示狀態。
        """
        return f"/optimized/{obj.share_token}" if obj.share_token else ""

    def get_share_active(self, obj) -> bool:
        return obj.share_is_active

    def get_result_summary(self, obj) -> dict:
        """「頁面」分頁每列的成果摘要：一句話＋視覺／技術修改數＋可量測改善數。"""
        applied = [e for e in obj.edit_report or [] if e.get("applied")]
        visual = sum(1 for e in applied if e.get("layer") == "visual")
        outcome = obj.outcome or {}
        return {
            "summary": outcome.get("summary", ""),
            "visual": visual,
            "technical": len(applied) - visual,
            "improved": sum(1 for m in outcome.get("metrics") or [] if m.get("improved")),
        }


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
    findings = serializers.SerializerMethodField()

    class Meta(SiteRebuildSerializer.Meta):
        fields = [
            *SiteRebuildSerializer.Meta.fields,
            "trace",
            "edit_report",
            "reply",
            "conversation",
            "outcome",
            "findings",
        ]
        read_only_fields = fields

    def get_findings(self, obj) -> list[dict]:
        return page_findings(obj)

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
