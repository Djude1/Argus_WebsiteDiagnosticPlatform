"""Nuclei 資安掃描整合（模板治理：roadmap §6 第 1 項，2026-10-08）。

結果要能重現，所以模板集是固定的：
- 模板版本鎖在 image 建置時（Dockerfile `NUCLEI_TEMPLATES_VERSION`，放在
  `ARGUS_NUCLEI_TEMPLATES_DIR`），執行時不更新；目錄沒有模板就算失敗，不能當成「0 項發現」。
- 只跑 CISA KEV（已知被實際利用的漏洞）模板：全部模板對單一網址約 9500 個請求，
  在 1–2 RPS 的主動預算下要跑 80 分鐘；KEV 約 630 個請求，5–10 分鐘跑得完。
- 只掃網站根網址：模板檢查的多半是網站層級路徑（例如 /wp-login.php），
  對每一頁重複掃只是同樣的探測乘以頁數。
- 每次執行記錄 Nuclei 版本、模板版本與這次選到的模板集指紋（模板數＋雜湊），
  同一指紋才代表同一組檢查。
- 逾時保留逾時前已輸出的結果，回報為部分完成，不當成「完整跑完、沒有問題」。

binary 不存在、模板目錄缺失或異常結束 → 拋 NucleiUnavailable，由 tasks.py 記為失敗。
"""
from __future__ import annotations

import functools
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

from apps.scans.cancellation import ScanCancelled
from apps.scans.process_runner import run_cancellable_process
from apps.scans.scan_logger import append_log
from apps.scans.security.redaction import redact_pii_in_text, redact_url_query_values
from apps.scans.services import allow_private_targets

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
    "default-login": "default_credentials",
    "xss": "cross_site_scripting",
    "sqli": "sql_injection",
    "ssrf": "server_side_request_forgery",
    "rce": "remote_code_execution",
}

# 模板選擇政策。注意 Nuclei 的標籤是單數（cve、misconfig、exposure），不是模板目錄名稱；
# 2026-10-08 前的快速模式寫成 cves／misconfigurations，實測只選到 3 個模板。
TEMPLATE_POLICY = {
    "name": "kev",
    "tags": "kev",
    "severity": "critical,high,medium",
    "exclude_tags": "dos,fuzz,creds-stuffing,token-spray",
    "protocol": "http",
}
# 高噪音模板（實測誤報才加入，並寫明原因）；目前沒有
EXCLUDED_TEMPLATE_IDS: tuple[str, ...] = ()

TEMPLATES_VERSION_FILE = ".argus-templates-version"
_CHECKSUM_FILE = "templates-checksum.txt"


class NucleiUnavailable(RuntimeError):
    """Nuclei 無法執行（沒有 binary、沒有模板或異常結束）。"""


@dataclass
class NucleiRun:
    findings: list[dict] = field(default_factory=list)
    timed_out: bool = False
    template_set: dict = field(default_factory=dict)


def _policy_args() -> list[str]:
    args = [
        "-tags", TEMPLATE_POLICY["tags"],
        "-severity", TEMPLATE_POLICY["severity"],
        "-etags", TEMPLATE_POLICY["exclude_tags"],
        "-pt", TEMPLATE_POLICY["protocol"],
    ]
    if EXCLUDED_TEMPLATE_IDS:
        args += ["-eid", ",".join(EXCLUDED_TEMPLATE_IDS)]
    return args


def _root_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def _engine_version() -> str:
    try:
        proc = subprocess.run(  # noqa: S603 — 固定參數
            ["nuclei", "-version", "-duc"], capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001
        return "unknown"
    match = re.search(r"Engine Version:\s*(v[\w.\-]+)", proc.stdout + proc.stderr)
    return match.group(1) if match else "unknown"


@functools.lru_cache(maxsize=4)
def _describe_template_set(templates_dir: str, checksum_mtime: float) -> dict:
    """列出這個政策實際選到的模板，算出指紋。checksum_mtime 只用來讓快取跟著模板更新失效。"""
    root = Path(templates_dir)
    proc = subprocess.run(  # noqa: S603 — 固定參數
        # 沒有 -no-stdin 時 nuclei 會等 stdin 的目標清單，在 worker 裡會一直卡到逾時
        ["nuclei", "-duc", "-no-stdin", "-t", templates_dir, *_policy_args(), "-tl", "-silent"],
        capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
    )
    selected = []
    for line in proc.stdout.splitlines():
        if not line.strip().endswith(".yaml"):
            continue  # 「Listing available…」之類的說明列
        path = Path(line.strip()).resolve()
        try:
            selected.append(path.relative_to(root.resolve()).as_posix())
        except ValueError:
            selected.append(path.as_posix())
    selected.sort()
    checksums: dict[str, str] = {}
    checksum_file = root / _CHECKSUM_FILE
    if checksum_file.exists():
        for line in checksum_file.read_text(encoding="utf-8", errors="replace").splitlines():
            path, _, digest = line.rpartition(":")
            if path:
                checksums[path] = digest
    # 內容指紋：模板路徑＋該模板的內容雜湊（沒有 checksum 檔時只用路徑）
    digest = hashlib.sha256(
        "\n".join(f"{path}:{checksums.get(path, '')}" for path in selected).encode()
    ).hexdigest()
    version_file = root / TEMPLATES_VERSION_FILE
    return {
        "policy": TEMPLATE_POLICY["name"],
        "templates_version": (
            version_file.read_text(encoding="utf-8").strip() if version_file.exists()
            else "unknown"
        ),
        "templates": len(selected),
        "sha256": digest,
    }


def template_set_info(templates_dir: str) -> dict:
    """Nuclei 版本、模板版本與這次選到的模板集；目錄沒有模板就拋 NucleiUnavailable。"""
    root = Path(templates_dir)
    if not templates_dir or not root.is_dir():
        raise NucleiUnavailable("templates_dir_missing")
    checksum_file = root / _CHECKSUM_FILE
    mtime = checksum_file.stat().st_mtime if checksum_file.exists() else 0.0
    info = dict(_describe_template_set(str(root), mtime))
    if not info["templates"]:
        raise NucleiUnavailable("no_templates_selected")
    info["engine"] = _engine_version()
    return info


def template_set_text(info: dict) -> str:
    return (
        f"Nuclei {info.get('engine', 'unknown')}、模板 {info.get('templates_version', 'unknown')}"
        f"（{info.get('policy', '')}：{info.get('templates', 0)} 個，"
        f"指紋 {str(info.get('sha256', ''))[:12]}）"
    )


def run_nuclei(
    url: str,
    scan_job_id: int,
    *,
    rate_limit: int | None = None,
) -> NucleiRun:
    """以固定模板集掃描網站根網址，回傳結果與這次的模板集紀錄。

    rate_limit：整個 Nuclei process 的每秒請求上限。
    逾時不拋例外：保留逾時前已輸出的結果並標 timed_out。
    """
    if not shutil.which("nuclei"):
        raise NucleiUnavailable("nuclei_missing")
    template_set = template_set_info(settings.ARGUS_NUCLEI_TEMPLATES_DIR)

    hard_timeout = settings.ARGUS_NUCLEI_TIMEOUT
    effective_rate_limit = max(int(rate_limit if rate_limit is not None else 2), 1)
    target = _root_url(url)

    cmd = [
        "nuclei",
        "-u", target,
        "-t", settings.ARGUS_NUCLEI_TEMPLATES_DIR,
        *_policy_args(),
        "-j",
        "-silent",
        "-no-stdin",
        "-duc",
        # -lna = -restrict-local-network-access：封鎖對私網位址的連線（SSRF 防護）。
        # 僅在本機／隔離 demo 的私網旁路（ARGUS_ALLOW_PRIVATE_TARGETS，DEBUG only）
        # 開啟時移除，讓 Nuclei 能掃 Docker 網路內的受控測試目標（例如 Juice Shop）。
        *([] if allow_private_targets() else ["-lna"]),
        "-ni",
        "-dr",
        "-or",
        "-H", f"User-Agent: {settings.ARGUS_SCANNER_USER_AGENT}",
        "-timeout", "15",
        "-rl", str(effective_rate_limit),
        "-bs", "5",
        "-c", "5",
        "-mhe", "20",
        "-rsr", str(2 * 1024 * 1024),
    ]
    append_log(scan_job_id, f"Nuclei 開始：{template_set_text(template_set)}，掃描 {target}")

    timed_out = False
    try:
        result = run_cancellable_process(cmd, scan_job_id=scan_job_id, timeout=hard_timeout)
        stdout = result.stdout or ""
    except ScanCancelled:
        raise
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.output or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
    else:
        if result.returncode != 0 and not stdout.strip():
            raise NucleiUnavailable(f"exit_{result.returncode}")

    findings = _parse_jsonl(stdout.splitlines())
    if timed_out:
        append_log(
            scan_job_id,
            f"Nuclei 逾時（{hard_timeout} 秒），保留逾時前的 {len(findings)} 項發現",
            level="warn",
        )
    else:
        append_log(scan_job_id, f"Nuclei 完成：{len(findings)} 項發現")
    return NucleiRun(findings=findings, timed_out=timed_out, template_set=template_set)


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
    safe_matched_at = redact_pii_in_text(redact_url_query_values(str(matched_at)))

    extracted = record.get("extracted-results") or []
    evidence_parts = [f"命中 URL：{safe_matched_at}", f"Template：{template_id}"]
    if extracted:
        evidence_parts.append(f"提取結果：{len(extracted)} 筆（內容已遮罩）")

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
            f"- 命中位置：{safe_matched_at}\n"
            f"請說明此問題的影響範圍、利用方式與修復優先順序。"
        ),
    }
