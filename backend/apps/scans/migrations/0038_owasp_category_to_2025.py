"""把既有 Finding.owasp_category 由 OWASP Top 10:2021 代號回填成 2025 代號。

2026-10-18：系統改為原生 2025（owasp_mapper 對映表已直接產 2025）。既有資料仍是 2021，依官方
2021→2025 對照轉換（CWE-209 錯誤訊息洩漏歸 2025 新類別 A10）。只動 category=security 且有代號者。
"""
from django.db import migrations

# OWASP Top 10 2021 → 2025 類別對照（官方調整）
_MAP_2021_TO_2025 = {
    "A01": "A01", "A02": "A04", "A03": "A05", "A04": "A06", "A05": "A02",
    "A06": "A03", "A07": "A07", "A08": "A08", "A09": "A09", "A10": "A01",
}


def to_2025(apps, schema_editor):
    Finding = apps.get_model("scans", "Finding")
    updated = []
    qs = Finding.objects.filter(category="security").exclude(owasp_category="").only(
        "id", "owasp_category", "cwe_id"
    )
    for f in qs.iterator():
        code_2021 = (f.owasp_category or "").strip().upper()
        # 錯誤訊息洩漏敏感資訊（堆疊追蹤）在 2025 歸到新類別 A10 例外狀況處理不當
        new_code = "A10" if (f.cwe_id or "").strip().upper() == "CWE-209" else \
            _MAP_2021_TO_2025.get(code_2021, code_2021)
        if new_code != f.owasp_category:
            f.owasp_category = new_code
            updated.append(f)
    if updated:
        Finding.objects.bulk_update(updated, ["owasp_category"], batch_size=500)


def noop_reverse(apps, schema_editor):
    # 不可逆（2025 多對一到 2021，無法精確還原）；保留資料不動
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0037_scanjob_agent_findings_summary"),
    ]

    operations = [
        migrations.RunPython(to_2025, noop_reverse),
    ]
