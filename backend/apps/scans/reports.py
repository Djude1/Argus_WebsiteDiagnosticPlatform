from collections import OrderedDict
from pathlib import Path

from django.conf import settings
from docx import Document

from apps.scans.models import ScanJob
from apps.scans.security.redaction import redact_pii_in_text


def get_severity_display(severity: str) -> str:
    severity_map = {
        "critical": "嚴重風險",
        "high": "高風險",
        "medium": "中風險",
        "low": "低風險",
        "info": "資訊提示",
    }
    return severity_map.get(severity, severity or "未知")

def get_finding_description_label(severity: str) -> str:
    if severity in {"critical", "high"}:
        return "風險描述"
    elif severity == "medium":
        return "改善重點"
    return "建議優化"


def get_remediation_label(severity: str) -> str:
    if severity in {"critical", "high"}:
        return "修補方向"
    return "建議修補"


def mask_pii_evidence(text: str) -> str:
    """報告展示層遮罩：evidence 含原始個資（email/手機/身分證/信用卡）就地遮罩，
    這份 .docx 會被下載、轉寄、存檔，直接印出原始內容有明確合規風險。只保留頭尾供
    人工比對，不修改 DB 內的原始 Finding 記錄。

    對「所有」finding 的 evidence 都套用（不靠 rule_id 前綴判斷是否為 PII finding）：
    除了 scanners.py::analyze_data_exposure() 產生的 SECURITY_PII_* finding，
    security/exposure_scanner.py 的敏感檔案外洩 finding 也會把命中檔案的原始內容
    片段放進 evidence，一樣可能含未遮罩個資，用 rule_id 白名單很容易漏掉這類來源；
    正則對不含 PII 樣式的文字（如 header 名稱、URL）是無操作，不會誤傷正常內容。"""
    return redact_pii_in_text(text)


def _group_findings_for_report(findings) -> list[dict]:
    """同一個 rule_id + evidence 完全相同的 finding（例如同一份 PII 或同一組缺 header
    的問題出現在多個頁面）合併成一筆，受影響頁面收斂成清單。只影響 .docx 呈現順序與
    分組，不改資料庫裡的原始 Finding 記錄。"""
    groups: OrderedDict[tuple[str, str], dict] = OrderedDict()
    for finding in findings:
        key = (finding.rule_id or "", finding.evidence or "")
        group = groups.get(key)
        if group is None:
            group = {"finding": finding, "pages": []}
            groups[key] = group
        group["pages"].append(finding.page.final_url if finding.page else "站台層級")
    return list(groups.values())


def build_scan_report(scan_job: ScanJob) -> str:
    report_dir = Path(settings.MEDIA_ROOT) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"scan-{scan_job.id}-report.docx"

    document = Document()
    document.add_heading("Argus 網站健檢報告", 0)
    document.add_paragraph(f"掃描網址：{scan_job.normalized_url}")
    document.add_paragraph(f"掃描狀態：{scan_job.get_status_display()}")
    if scan_job.completed_at:
        document.add_paragraph(
            f"掃描完成時間：{scan_job.completed_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    overall_score = scan_job.overall_score if scan_job.overall_score is not None else "尚未產生"
    document.add_paragraph(f"整體分數：{overall_score}")

    document.add_heading("摘要", level=1)
    for category, score in (scan_job.category_scores or {}).items():
        document.add_paragraph(f"{category.upper()}：{score}")

    document.add_heading("優先改善建議（依影響程度排序）", level=1)
    for action in scan_job.top_actions or []:
        severity = action.get("severity", "")
        severity_display = get_severity_display(severity)
        document.add_paragraph(
            f"{severity_display} / {action.get('category', '').upper()}："
            f"{action.get('title', '')}",
            style="List Bullet",
        )

    document.add_heading("發現項目", level=1)
    grouped_findings = _group_findings_for_report(
        scan_job.findings.select_related("page").all()
    )
    for item in grouped_findings:
        finding = item["finding"]
        pages = item["pages"]
        severity_display = get_severity_display(finding.severity)

        document.add_heading(finding.title, level=2)
        document.add_paragraph(
            f"分類：{finding.category.upper()} / 嚴重度：{severity_display}"
        )
        document.add_paragraph(f"規則 ID：{finding.rule_id or '未標示'}")
        if finding.owasp_category or finding.cwe_id:
            owasp = finding.owasp_category or "—"
            cwe = finding.cwe_id or "—"
            document.add_paragraph(f"OWASP：{owasp} / CWE：{cwe}")

        if len(pages) > 1:
            document.add_paragraph(f"受影響頁面（共 {len(pages)} 處）：{'、'.join(pages)}")
        else:
            document.add_paragraph(f"頁面：{pages[0]}")

        document.add_paragraph(get_finding_description_label(finding.severity))
        document.add_paragraph(finding.description or "（無）")

        document.add_paragraph(get_remediation_label(finding.severity))
        document.add_paragraph(finding.remediation or "（無）")

        if finding.evidence:
            document.add_paragraph("Deterministic Evidence")
            if finding.evidence_source:
                document.add_paragraph(f"證據來源：{finding.evidence_source}")
            if finding.evidence_type:
                document.add_paragraph(f"證據型態：{finding.evidence_type}")
            # 先在完整字串上遮罩、再截斷顯示長度：反過來做的話，PII 數值可能剛好被
            # 1000 字截斷點切一半，殘缺數字長度不足以命中 regex，反而以明文殘留。
            masked_evidence = mask_pii_evidence(finding.evidence)
            if masked_evidence != finding.evidence:
                document.add_paragraph(
                    "⚠️ 以下內容為偵測到之敏感樣本部分遮罩後的結果，請依個資法妥善保管本報告。"
                )
            evidence_text = masked_evidence[:1000]
            truncated_note = "…（證據過長已截斷）" if len(masked_evidence) > 1000 else ""
            document.add_paragraph(f"{evidence_text}{truncated_note}")

        if finding.ai_explanation or finding.ai_remediation:
            document.add_paragraph("AI 解釋與改善建議")
            if finding.llm_model:
                document.add_paragraph(f"模型：{finding.llm_model}")
            if finding.ai_explanation:
                document.add_paragraph(finding.ai_explanation)
            if finding.ai_remediation:
                document.add_paragraph(finding.ai_remediation)

    document.add_heading("附錄", level=1)
    document.add_paragraph(
        "本報告採 Evidence-first 原則：SEO、AEO、GEO 與資安建議均先由爬蟲與規則引擎"
        "產生可驗證之 Deterministic Evidence，再交由 AI 進行自然語言解釋與改善建議撰寫。"
        "AI 不直接判斷網站好壞，也不得新增未被掃描器驗證的證據。"
    )
    document.save(output_path)
    return str(output_path)
