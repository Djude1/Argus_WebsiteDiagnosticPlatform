"""Nuclei 資安掃描整合。

以本機 nuclei binary 執行弱點掃描，支援兩種模式：
- fast（免費）：精選模板 + 6 分鐘上限
- deep（付費）：全部模板 + 12 分鐘上限

任何錯誤皆靜默回傳 []，不影響主掃描流程。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from apps.scans.scan_logger import append_log

_PRIORITY: dict[str, float] = {
    "critical": 90.0,
    "high": 75.0,
    "medium": 55.0,
    "low": 30.0,
    "info": 10.0,
}

_TAG_IMPACT: dict[str, str] = {
    "cve": "known_vulnerability",
    "misconfig": "misconfiguration",
    "exposure": "information_exposure",
    "default-logins": "default_credentials",
    "xss": "cross_site_scripting",
    "sqli": "sql_injection",
    "ssrf": "server_side_request_forgery",
    "rce": "remote_code_execution",
}


def run_nuclei(
    url: str,
    scan_job_id: int,
    *,
    deep: bool = False,
    extra_urls: list[str] | None = None,
) -> list[dict]:
    """執行 Nuclei 掃描並回傳 Finding dict 列表。

    deep=False：精選模板
    （cves/vulnerabilities/misconfigurations/exposures/default-logins），6 分鐘硬限。
    deep=True：全部模板，12 分鐘硬限。
    extra_urls：額外的掃描目標（如已爬取的頁面列表），與 url 合併後整批掃描。
    binary 不存在或任何例外皆 silent-fail 回傳 []。
    """
    if not shutil.which("nuclei"):
        append_log(scan_job_id, "Nuclei binary 未安裝，略過", level="warn")
        return []

    hard_timeout = 720 if deep else 360
    mode_label = "深度（付費）" if deep else "快速（免費）"

    # 合併並去重 URL 列表（保留插入順序，入口 URL 在最前）
    all_urls: list[str] = list(dict.fromkeys([url, *(extra_urls or [])]))

    # 決定目標參數：單 URL 用 -u，多 URL 寫 temp file 用 -l
    url_file: str | None = None
    if len(all_urls) == 1:
        target_args = ["-u", all_urls[0]]
    else:
        fd, url_file = tempfile.mkstemp(suffix=".txt", prefix="nuclei_urls_")
        os.close(fd)
        with open(url_file, "w") as f:
            f.write("\n".join(all_urls))
        target_args = ["-l", url_file]

    cmd = [
        "nuclei",
        *target_args,
        "-j",
        "-silent",
        "-timeout", "30" if deep else "15",
        "-c", "50" if deep else "25",
    ]
    if not deep:
        cmd += ["-tags", "cves,vulnerabilities,misconfigurations,exposures,default-logins"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=hard_timeout,
        )
    except subprocess.TimeoutExpired:
        append_log(scan_job_id, f"Nuclei 超時（{hard_timeout}s），略過", level="warn")
        return []
    except Exception as exc:  # noqa: BLE001
        append_log(scan_job_id, f"Nuclei 失敗（{exc.__class__.__name__}），略過", level="warn")
        return []
    finally:
        if url_file and os.path.exists(url_file):
            os.unlink(url_file)

    if result.returncode != 0 and not result.stdout.strip():
        append_log(scan_job_id, f"Nuclei 異常退出（exit={result.returncode}），略過", level="warn")
        return []

    findings = _parse_jsonl(result.stdout.splitlines())
    append_log(scan_job_id, f"Nuclei 完成（{mode_label}）：{len(findings)} 項發現")
    return findings


def _parse_jsonl(lines: list[str]) -> list[dict]:
    """解析 Nuclei JSONL 輸出，回傳去重後的 Finding dict 列表。"""
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        template_id = record.get("template-id", "")
        matched_at = record.get("matched-at", "")
        key = (template_id, matched_at)
        if key in seen:
            continue
        seen.add(key)

        finding = _build_finding(record)
        findings.append(finding)

    return findings


def _build_finding(record: dict) -> dict:
    """將 Nuclei JSONL 記錄轉為 Argus Finding dict。"""
    info = record.get("info") or {}
    template_id = record.get("template-id", "unknown")
    name = info.get("name") or template_id
    raw_severity = (info.get("severity") or "info").lower()
    severity = raw_severity if raw_severity in _PRIORITY else "info"

    description = info.get("description") or f"Nuclei 模板 {template_id} 偵測到安全問題。"
    remediation = info.get("remediation") or "請參考官方修補建議或對應 CVE 詳情。"
    matched_at = record.get("matched-at") or record.get("host", "")

    extracted = record.get("extracted-results") or []
    evidence_parts = [f"命中 URL：{matched_at}", f"Template：{template_id}"]
    if extracted:
        evidence_parts.append(f"提取結果：{'; '.join(str(r) for r in extracted[:3])}")

    raw_tags = info.get("tags") or []
    tags: list[str] = (
        raw_tags if isinstance(raw_tags, list)
        else [t.strip() for t in str(raw_tags).split(",")]
    )
    impact_area = "vulnerability"
    for tag in tags:
        if tag in _TAG_IMPACT:
            impact_area = _TAG_IMPACT[tag]
            break

    return {
        "category": "security",
        "severity": severity,
        "title": name,
        "description": description,
        "remediation": remediation,
        "evidence": "；".join(evidence_parts),
        "selector": "",
        "bounding_box": None,
        "impact_area": impact_area,
        "confidence": 0.85,
        "priority_score": _PRIORITY[severity],
        "ai_handoff_prompt": (
            f"Nuclei 在你的網站偵測到資安問題，請協助分析：\n"
            f"- 問題：{name}\n"
            f"- 嚴重度：{severity}\n"
            f"- 命中位置：{matched_at}\n"
            f"請說明此問題的影響範圍、利用方式與修復優先順序。"
        ),
    }
