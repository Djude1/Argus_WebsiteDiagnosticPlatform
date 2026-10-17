"""既有 AI Agent 資安觀察改用每個問題自己的代號，並重算分數（2026-10-16）。

舊版所有 Agent 資安觀察共用 rule_id `agent-observed-security`：計分與優先處理只留第一筆
（實測站台 實測「嚴重」的 Swagger 外洩因此沒進優先處理）、報告併成一張卡、歷史比較
把不同問題當成同一個。這裡把舊紀錄改成新代號（只改代號，不刪任何發現），已完成的掃描
重算分數與優先清單、刪除快取報告（下次下載時重新產生，報告編號不變）。

代號規則用目前的程式（apps.agent.findings、apps.scans.finding_normalization）：必須和新掃描
完全一致，另抄一份會隨時間分岔。資料列一律用這裡的歷史 model（之後新增欄位時，落後的資料庫
不會去查還不存在的欄位）；只有資料庫裡真的有舊代號時才匯入，全新建庫不受未來程式改動影響。
反向操作不做事（舊代號是 bug，不還原）。
"""

from django.db import migrations

LEGACY_RULE = "agent-observed-security"


def rekey(apps, schema_editor):
    Finding = apps.get_model("scans", "Finding")
    ScanJob = apps.get_model("scans", "ScanJob")
    scan_ids = list(
        Finding.objects.filter(rule_id=LEGACY_RULE)
        .values_list("scan_job_id", flat=True)
        .distinct()
    )
    if not scan_ids:
        return
    from apps.scans.finding_normalization import rekey_agent_findings_and_rescore

    for scan_job in ScanJob.objects.filter(id__in=scan_ids):
        rekey_agent_findings_and_rescore(scan_job)


class Migration(migrations.Migration):
    dependencies = [("scans", "0034_demo_target_keywords")]

    operations = [migrations.RunPython(rekey, migrations.RunPython.noop)]
