from collections import OrderedDict
from pathlib import Path

from django.conf import settings
from docx import Document

from apps.scans.models import Finding, ScanJob
from apps.scans.scan_plan import build_scan_execution_plan
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
    """同一個 rule_id 的 finding 合併成一筆，受影響頁面收斂成清單。

    合併鍵只用 rule_id。rule_id 由 scanners._default_rule_id() 從 category + title
    的雜湊產生，同一種問題不論出現在哪一頁都一致。舊版把 evidence 也放進鍵裡，
    但 evidence 帶的是該頁專屬內容（例如那一頁實際的 title 文字），於是同一個問題
    出現在 N 頁就被拆成 N 筆顯示——scan 25 的報告因此把「Meta title 長度不理想」
    列了 4 次、「核心內容高度依賴 JavaScript 渲染」列了 3 次。

    rule_id 為空時退回 finding.pk，避免不同問題只因為「都沒有 rule_id」被錯誤
    合併成一筆。只影響 .docx 呈現順序與分組，不改資料庫裡的原始 Finding 記錄。
    """
    groups: OrderedDict[str, dict] = OrderedDict()
    for finding in findings:
        key = finding.rule_id or f"_finding:{finding.pk}"
        group = groups.get(key)
        if group is None:
            group = {"finding": finding, "pages": []}
            groups[key] = group
        page_label = finding.page.final_url if finding.page else "站台層級"
        if page_label not in group["pages"]:
            group["pages"].append(page_label)
    return list(groups.values())


def _add_scan_scope_section(document, scan_job: ScanJob) -> None:
    """掃描範圍。收件者要能判斷這份報告涵蓋了什麼，「沒發現問題」才有意義。

    scope 一律取自 scan_plan.build_scan_execution_plan()，不要在這裡重複
    「max_pages==1 代表單頁」的慣例，避免兩邊漂移。
    """
    document.add_heading("掃描範圍", level=1)
    scope_label = "單頁" if build_scan_execution_plan(scan_job).scope == "single" else "全網站"
    document.add_paragraph(f"掃描範圍：{scope_label}")
    document.add_paragraph(f"探測模式：{scan_job.get_scan_mode_display()}")
    document.add_paragraph(f"頁數上限：{scan_job.max_pages}　連結深度上限：{scan_job.max_depth}")
    document.add_paragraph(f"實際掃描頁數：{scan_job.pages.count()}")
    document.add_paragraph(
        f"遵守 robots.txt：{'是' if scan_job.respect_robots else '否'}"
    )


def _add_scan_warnings_section(document, scan_job: ScanJob) -> None:
    """掃描過程的警示。

    只挑對收件者有意義的項目：爬 0 頁（分數只反映站台層級檢查，不能解讀成
    網站安全）、被 robots 略過與擷取失敗的頁數、偵測到的技術棧。內部運維資訊
    （settlement_error 的計費結算、agent 的 token 用量）刻意不寫進對外報告。
    """
    warnings = scan_job.warning_summary or {}
    lines: list[str] = []

    if warnings.get("scan_effectiveness") == "no_pages_crawled":
        lines.append(
            "掃描有效性警示：本次未抓到任何頁面（目標可能不可達或全部逾時）。"
            "SEO 與 AEO 未評估，分數僅反映站台層級檢查，不應解讀為「網站沒有問題」。"
        )

    blocked = warnings.get("blocked_urls") or []
    if isinstance(blocked, list) and blocked:
        lines.append(f"依 robots.txt 或掃描範圍限制，略過 {len(blocked)} 個頁面未檢查。")

    failed = warnings.get("failed_urls") or []
    if isinstance(failed, list) and failed:
        lines.append(f"有 {len(failed)} 個頁面擷取失敗（逾時或回應異常），未納入本次分析。")

    tech_stack = warnings.get("tech_stack") or []
    if isinstance(tech_stack, list) and tech_stack:
        lines.append(f"偵測到的技術棧：{'、'.join(str(t) for t in tech_stack)}")

    if not lines:
        return
    document.add_heading("掃描警示", level=1)
    for line in lines:
        document.add_paragraph(line, style="List Bullet")


def _add_authorization_section(document, scan_job: ScanJob) -> None:
    """掃描授權聲明。

    Argus 是授權式掃描平台，一份對外的資安報告必須記載這次掃描的授權依據，
    否則等於放棄本專案最核心的合規主張。

    刻意不寫入 AuthorizationConsent 的 ip_address 與 user_agent，也不寫授權
    帳號：這份 .docx 會被下載、轉寄、存檔給第三方，授權人的 IP 與瀏覽器指紋
    是個資，寫進去沒有任何對收件者的價值，只增加外洩面。需要稽核時查 DB 與
    AdminAuditLog。
    """
    document.add_heading("掃描授權聲明", level=2)
    consent = getattr(scan_job, "authorization_consent", None)
    if consent is None:
        document.add_paragraph(
            "查無授權紀錄：本次掃描在資料庫中沒有對應的授權同意紀錄。"
            "若這份報告要作為稽核依據，請先確認授權來源。"
        )
        return
    document.add_paragraph(f"授權網域：{consent.authorized_domain}")
    document.add_paragraph(
        f"授權時間：{consent.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    document.add_paragraph(
        f"主動測試授權：{'是' if consent.active_testing_authorized else '否（僅被動偵測）'}"
    )
    document.add_paragraph("授權聲明內容：")
    document.add_paragraph(consent.statement)


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

    _add_scan_scope_section(document, scan_job)

    document.add_heading("摘要", level=1)
    # 逐一列出全部 5 個分類，缺鍵的顯示「未評估」而非略過。calculate_scores() 只把
    # 實際執行過檢查的分類寫進 category_scores，缺鍵即代表沒測（例如 Hermes-Agent
    # 停用時的 UX）。舊版一律回傳 100，報告印出「UX：100」會被讀成「UX 完美」。
    # 同時說明整體分數的算法：舊版列 5 個分數卻只平均其中 4 個，使用者對不出總分。
    document.add_paragraph(
        "整體分數為下列「已評估」分類分數的平均，標示「未評估」的分類不納入計算。"
        "同一個問題出現在多個頁面只扣一次分；資訊提示（例如「偵測到 WAF 保護」）"
        "屬正向或中性訊息，不扣分。"
    )
    category_scores = scan_job.category_scores or {}
    for category in Finding.Category.values:
        score = category_scores.get(category)
        if isinstance(score, (int, float)):
            document.add_paragraph(f"{category.upper()}：{score}")
        else:
            document.add_paragraph(f"{category.upper()}：未評估（本次掃描未執行此項檢查）")

    _add_scan_warnings_section(document, scan_job)

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

        if finding.ai_handoff_prompt:
            # 報告不做 AI 解釋（ai_explanation 從未被實作），但每筆 finding 都已經有
            # 一段組好的提示詞，使用者可以直接貼進 ChatGPT / Claude 取得深入說明。
            # 必須跟 evidence 一樣遮罩：build_ai_handoff_prompt() 內嵌了原始 evidence，
            # 不遮罩等於從後門把個資漏回這份會被轉寄的報告。
            document.add_paragraph("AI 提示詞（可直接複製貼給 AI 助手取得進一步說明）")
            masked_prompt = mask_pii_evidence(finding.ai_handoff_prompt)
            prompt_text = masked_prompt[:1500]
            prompt_note = "…（提示詞過長已截斷）" if len(masked_prompt) > 1500 else ""
            document.add_paragraph(f"{prompt_text}{prompt_note}")

        if finding.ai_explanation or finding.ai_remediation:
            document.add_paragraph("AI 解釋與改善建議")
            if finding.llm_model:
                document.add_paragraph(f"模型：{finding.llm_model}")
            if finding.ai_explanation:
                document.add_paragraph(finding.ai_explanation)
            if finding.ai_remediation:
                document.add_paragraph(finding.ai_remediation)

    document.add_heading("附錄", level=1)
    _add_authorization_section(document, scan_job)
    document.add_heading("本報告如何產生", level=2)
    # 原文寫「再交由 AI 進行自然語言解釋與改善建議撰寫」，但 Finding.ai_explanation
    # 與 ai_remediation 在整個 backend 只被寫入空字串，該功能從未實作——這是一份
    # 對外交付文件裡的不實陳述。改為只描述實際做到的事。
    document.add_paragraph(
        "本報告採 Evidence-first 原則：SEO、AEO、GEO 與資安判斷全部來自爬蟲與規則引擎"
        "產生的可驗證證據，每一項發現都附上當下實際觀測到的內容。"
        "報告產生過程不使用 AI 改寫或推論結論，因此不會出現無法追溯到掃描證據的說法。"
    )
    document.save(output_path)
    return str(output_path)
