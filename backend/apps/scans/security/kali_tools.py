"""Hermes-Agent / 掃描流程呼叫 Kali container 的主動驗證工具（Phase 3 攻擊鏈）。

設計原則（嚴格遵守 security/CLAUDE.md）：
- **授權與預算統一由 kali_policy.reserve_sqlmap_targets 把關**：本模組不再自做
  scan_mode / active_testing_authorized 檢查；run_sqlmap / run_sqlmap_batch 一律
  先 reserve，再依 backend dispatcher 派發給 executor。
- **executor 不外露 raw stdout**：DockerSqlmapExecutor 在 process 內解析 sqlmap
  raw 輸出，回傳 KaliResult（stdout 固定為 ""），evidence_summary 僅含 parameter、
  techniques、dbms 與 settings.ARGUS_KALI_SQLMAP_VERSION。
- **任何例外 silent-fail**：回傳結構化 KaliResult/dict，不影響主掃描流程；唯一例外
  是 ScanCancelled 必須原樣重拋，讓合作式取消流程正確傳遞。
- 所有呼叫（含被擋）都記錄進 ScanJob.scan_log（append_log）。
- subprocess 一律用 list 形式（非 shell=True），避免命令注入。
- run_metasploit 僅在 docker backend 支援；kubernetes / 未知 backend 一律回
  blocked_reason=tool_not_supported_by_backend，不會呼叫 docker。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from urllib.parse import urlparse

from django.conf import settings

from apps.scans.cancellation import ScanCancelled
from apps.scans.scan_logger import append_log
from apps.scans.scanners import make_finding

from .kali_contracts import (
    KaliResult,
    ReservedSqlmapTarget,
    SqlmapExecution,
    SqlmapExecutor,
    redact_url_query_values,
)
from .kali_policy import reserve_sqlmap_targets

MAX_STDOUT_CHARS = 3000

# sqlmap 確認注入點時的輸出特徵（小寫比對）
# 注意：不可用 "injectable" 當特徵——sqlmap 找不到時會印
# "do not appear to be injectable"，會造成假陽性。
_SQLI_MARKERS = ("is vulnerable", "injection point")

# raw stdout 解析用（僅在 Docker executor process 內使用，不持久化）。
# parameter / dbms 字元集與 kali_contracts 的安全契約一致；width 上限 64。
_PARAM_RE = re.compile(r"Parameter:\s*([A-Za-z0-9_.\-]{1,64})", re.IGNORECASE)
_DBMS_RE = re.compile(r"back-end DBMS:\s*([A-Za-z0-9 ._-]{1,64})", re.IGNORECASE)
_SAFE_TECHNIQUES = (
    "boolean-based blind",
    "error-based",
    "inline query",
    "stacked queries",
    "time-based blind",
    "union query",
)


def _result(
    tool: str = "sqlmap",
    *,
    ok: bool = False,
    blocked_reason: str = "",
    returncode: int | None = None,
    stdout: str = "",
    error: str = "",
    confirmed: bool = False,
    evidence_summary: dict | None = None,
) -> dict:
    """facade 層統一回傳結構（與 agent/tools.py 既有 dict 契約相容）。"""
    return {
        "ok": ok,
        "tool": tool,
        "blocked_reason": blocked_reason,
        "returncode": returncode,
        "stdout": stdout[:MAX_STDOUT_CHARS],
        "error": error,
        "confirmed": confirmed,
        "evidence_summary": dict(evidence_summary or {}),
    }


def _stdout_indicates_sqli(stdout: str) -> bool:
    """從 sqlmap raw 輸出字串判斷是否確認可注入。

    保留給尚未遷移到 evidence_summary 的呼叫端（例如 agent/tools.py 的
    probe_sql_injection）；新流程應直接信任 KaliResult.confirmed。
    """
    low = (stdout or "").lower()
    return any(marker in low for marker in _SQLI_MARKERS)


# ---------------------------------------------------------------------------
# 授權鎖、container 檢查與 docker exec（保留給 Docker backend 與 metasploit）
# ---------------------------------------------------------------------------
def _authorization_block_reason(scan_job_id: int) -> str:
    """檢查三重授權鎖；通過回空字串，否則回擋下原因（不含任何機密）。

    run_sqlmap / run_sqlmap_batch 已改由 reserve_sqlmap_targets 統一把關，本函式
    僅剩 metasploit（docker 專屬工具）使用。
    """
    if not getattr(settings, "ARGUS_KALI_ENABLED", False):
        return "kali_disabled"
    from apps.scans.models import ScanJob

    try:
        job = ScanJob.objects.only(
            "scan_mode", "active_testing_authorized"
        ).get(pk=scan_job_id)
    except ScanJob.DoesNotExist:
        return "scan_not_found"
    if job.scan_mode != ScanJob.ScanMode.ACTIVE:
        return "scan_mode_not_active"
    if not job.active_testing_authorized:
        return "active_testing_unauthorized"
    return ""


def _container_running() -> bool:
    """確認 Kali container 存在且運行中（docker inspect）。docker 不存在則回 False。"""
    if not shutil.which("docker"):
        return False
    container = getattr(settings, "ARGUS_KALI_CONTAINER", "argus-kali-1")
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _docker_exec(args: list[str], timeout: int) -> tuple[int | None, str, str]:
    """執行 docker exec <container> <args>，回傳 (returncode, stdout, stderr)。"""
    container = getattr(settings, "ARGUS_KALI_CONTAINER", "argus-kali-1")
    docker_args = ["docker", "exec"]
    proxy_url = getattr(settings, "ARGUS_EGRESS_PROXY_URL", "")
    if proxy_url:
        no_proxy = os.environ.get("NO_PROXY", "")
        for name, value in (
            ("HTTP_PROXY", proxy_url),
            ("HTTPS_PROXY", proxy_url),
            ("NO_PROXY", no_proxy),
            ("http_proxy", proxy_url),
            ("https_proxy", proxy_url),
            ("no_proxy", no_proxy),
        ):
            docker_args.extend(["-e", f"{name}={value}"])
    docker_args.extend([container, *args])
    try:
        proc = subprocess.run(
            docker_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    except Exception as exc:  # noqa: BLE001
        return None, "", exc.__class__.__name__


def _metasploit_preflight(tool: str, scan_job_id: int) -> dict | None:
    """metasploit 專用 preflight：backend 必須是 docker，再走既有授權鎖。"""
    if getattr(settings, "ARGUS_KALI_BACKEND", "disabled") != "docker":
        append_log(
            scan_job_id,
            f"Kali {tool} 不支援此 backend"
            f"（{getattr(settings, 'ARGUS_KALI_BACKEND', 'disabled')}）",
            level="info",
        )
        return _result(
            tool, ok=False, blocked_reason="tool_not_supported_by_backend",
        )
    blocked = _authorization_block_reason(scan_job_id)
    if blocked:
        append_log(scan_job_id, f"Kali {tool} 已略過（{blocked}）", level="info")
        return _result(tool, ok=False, blocked_reason=blocked)
    if not _container_running():
        append_log(
            scan_job_id, f"Kali {tool} 已略過（container 未運行）", level="warn"
        )
        return _result(tool, ok=False, blocked_reason="container_not_running")
    return None


# ---------------------------------------------------------------------------
# DockerSqlmapExecutor：raw stdout 只在 process 內解析，不外露
# ---------------------------------------------------------------------------
def _parse_sqlmap_stdout(raw: str) -> tuple[bool, str, list[str], str]:
    """從 sqlmap raw stdout 抽出 (confirmed, parameter, techniques, dbms)。

    只接受 SAFE_TECHNIQUES 內的技術名稱；parameter / dbms 字元與長度限制對齊
    kali_contracts 的安全契約，避免不可信輸出直接進入 evidence_summary。
    """
    text = raw or ""
    lowered = text.lower()
    confirmed = any(marker in lowered for marker in _SQLI_MARKERS)
    param_match = _PARAM_RE.search(text)
    parameter = param_match.group(1) if param_match else ""
    techniques = [name for name in _SAFE_TECHNIQUES if name in lowered]
    dbms_match = _DBMS_RE.search(text)
    dbms = dbms_match.group(1).strip() if dbms_match else ""
    return confirmed, parameter, techniques, dbms


class DockerSqlmapExecutor:
    """Docker backend 的 SQLmap executor。

    每個 target 獨立執行；單一 target 失敗會變成單一 KaliResult，不會中斷 batch。
    raw stdout 永不離開本物件——只把解析後的安全 summary 放進 evidence_summary。
    """

    def execute(
        self,
        scan_job_id: int,
        targets: Sequence[ReservedSqlmapTarget],
    ) -> tuple[KaliResult, ...]:
        return tuple(self._execute_one(scan_job_id, target) for target in targets)

    def _execute_one(
        self, scan_job_id: int, target: ReservedSqlmapTarget,
    ) -> KaliResult:
        timeout = getattr(settings, "ARGUS_KALI_TIMEOUT", 120)
        append_log(
            scan_job_id,
            f"Kali sqlmap 開始驗證：{urlparse(target.url).netloc}",
            level="info",
        )
        # --flush-session + per-scan/per-target output dir：sqlmap 的 output dir 僅以
        # hostname 為 key（忽略 port），若沿用舊 session，同 host 前次失敗的判定會
        # 被 resume 而短路成「not injectable」，污染後續掃描。強制每次掃描獨立且
        # 不吃舊 session。
        rc, out, err = _docker_exec(
            [
                "sqlmap", "-u", target.url, "--batch", "--flush-session",
                f"--output-dir=/tmp/sqlmap_{scan_job_id}_{target.index}",
            ],
            timeout=timeout,
        )
        if rc is None:
            append_log(scan_job_id, f"Kali sqlmap 逾時/失敗（{err}）", level="warn")
            return KaliResult(ok=False, error=err)

        confirmed, parameter, techniques, dbms = _parse_sqlmap_stdout(out)
        append_log(
            scan_job_id,
            f"Kali sqlmap 完成（returncode={rc}, confirmed={confirmed}）",
            level="info",
        )
        return KaliResult(
            ok=(rc == 0),
            returncode=rc,
            confirmed=confirmed,
            evidence_summary={
                "parameter": parameter,
                "techniques": techniques,
                "dbms": dbms,
                "sqlmap_version": getattr(
                    settings, "ARGUS_KALI_SQLMAP_VERSION", "",
                ),
            },
        )


def _executor_for_backend() -> SqlmapExecutor | None:
    """依 settings.ARGUS_KALI_BACKEND 選擇 executor；未知 backend 回 None。

    Kubernetes executor 於 Task 4 加入；目前 lazy import 預期 .kali_kubernetes
    已存在，否則會在實際使用時 ImportError——保留給後續 Task 接線。
    """
    backend = getattr(settings, "ARGUS_KALI_BACKEND", "disabled")
    if backend == "docker":
        return DockerSqlmapExecutor()
    if backend == "kubernetes":
        from .kali_kubernetes import KubernetesSqlmapExecutor
        return KubernetesSqlmapExecutor()
    return None


# ---------------------------------------------------------------------------
# Facade：run_sqlmap / run_sqlmap_batch / validate_findings_with_kali
# ---------------------------------------------------------------------------
def _log_kali_decision(
    scan_job_id: int, reason: str, *, level: str = "info",
) -> None:
    """把 facade 的 Kali 決策寫入 scan_log，留下 audit trail。

    只記錄**固定 structured reason** 與安全 lifecycle 文案；呼叫端嚴禁傳入 target
    URL、query value、raw stdout 或 exception body。reason 一律來自 policy／facade
    內部的固定列舉字串（kali_disabled / scan_mode_not_active / backend_misconfigured
    等），不與不可信輸入拼接。
    """
    append_log(
        scan_job_id, f"Kali sqlmap 已略過（{reason}）", level=level,
    )


def run_sqlmap(target_url: str, scan_job_id: int) -> dict:
    """單目標 SQLmap 主動驗證。

    授權、公網、同源、query parameter 與去重預算完全交由
    reserve_sqlmap_targets(max_count=1) 統一把關；通過後才派發給 backend 的
    executor。回傳 dict 形狀與 agent/tools.py 既有契約相容（ok / blocked_reason /
    stdout / error / confirmed / evidence_summary），且 stdout 固定為 ""。

    所有 blocked / 失敗分支都會寫一筆安全 audit log（不含 URL/query value）。
    """
    outcome = reserve_sqlmap_targets(
        scan_job_id, [target_url], max_count=1,
    )
    if outcome.blocked_reason:
        _log_kali_decision(scan_job_id, outcome.blocked_reason)
        return _result(blocked_reason=outcome.blocked_reason)
    if not outcome.targets:
        _log_kali_decision(scan_job_id, "target_already_tested")
        return _result(blocked_reason="target_already_tested")

    executor = _executor_for_backend()
    if executor is None:
        _log_kali_decision(scan_job_id, "backend_misconfigured", level="warn")
        return _result(blocked_reason="backend_misconfigured")

    results = executor.execute(scan_job_id, outcome.targets)
    if len(results) != len(outcome.targets):
        append_log(scan_job_id, "Kali sqlmap executor 結果數量不符", level="warn")
        return _result(error="runner_failed")
    return results[0].as_dict()


def run_sqlmap_batch(
    scan_job_id: int,
    candidate_urls: list[str],
    max_targets: int = 3,
) -> dict:
    """批次 SQLmap 主動驗證。

    - 預算：max_count = min(max_targets, 3)，與 kali_policy 的全域上限一致。
    - 每個 admitted target 都會被執行一次；單一 target 失敗僅影響自身 KaliResult。
    - 若 executor 回傳的結果數與 admitted target 數不符（runner 契約失衡），每一個
      admitted target 都換成 runner_failed KaliResult，避免部分遺漏被誤判為安全。
    - 所有 blocked / 失敗分支都會寫一筆安全 audit log（不含 URL/query value）。
    - 回傳 {"blocked_reason": str, "executions": tuple[SqlmapExecution, ...]}。
    """
    budget = min(max(0, max_targets), 3)
    outcome = reserve_sqlmap_targets(
        scan_job_id, candidate_urls, max_count=budget,
    )
    if outcome.blocked_reason:
        _log_kali_decision(scan_job_id, outcome.blocked_reason)
        return {"blocked_reason": outcome.blocked_reason, "executions": ()}
    if not outcome.targets:
        _log_kali_decision(scan_job_id, "target_already_tested")
        return {"blocked_reason": "target_already_tested", "executions": ()}

    executor = _executor_for_backend()
    if executor is None:
        _log_kali_decision(scan_job_id, "backend_misconfigured", level="warn")
        return {"blocked_reason": "backend_misconfigured", "executions": ()}

    results = executor.execute(scan_job_id, outcome.targets)
    if len(results) != len(outcome.targets):
        append_log(scan_job_id, "Kali sqlmap batch 結果數量不符", level="warn")
        results = tuple(
            KaliResult(ok=False, error="runner_failed")
            for _ in outcome.targets
        )
    executions = tuple(
        SqlmapExecution(target=target, result=result)
        for target, result in zip(outcome.targets, results, strict=True)
    )
    return {"blocked_reason": "", "executions": executions}


def validate_findings_with_kali(
    scan_job_id: int, candidate_urls: list[str], max_targets: int = 3,
) -> list[dict]:
    """對帶參數的候選 URL 跑批次 sqlmap 主動驗證，回傳已確認漏洞的 Finding dict list。

    - 透過 run_sqlmap_batch 統一編排（單一呼叫）； gating 完全交給
      reserve_sqlmap_targets。
    - 呼叫 batch 前先挑出具 query parameter 的候選：爬蟲結果通常以入口頁（無 query）
      排第一筆，原樣交給 policy 會在第一筆就被截斷成 no_query_parameter，使後續合法
      帶 query 的 URL 永遠不執行。policy 仍會對每個 admitted target 再做 same-origin
      / public / query 檢查，這裡只做粗範。
    - 只信任 KaliResult.confirmed；未確認不產 Finding。
    - description 內的 URL 一律經 redact_url_query_values 遮罩 query value。
    - Finding 的 evidence_json 只放 evidence_summary，永不放 raw stdout。
    - ScanCancelled 必須原樣重拋；其他例外 silent-fail 回 []。
    """
    query_candidates = [
        url for url in (candidate_urls or [])
        if "?" in str(url) and "=" in str(url)
    ]
    if not query_candidates:
        return []
    try:
        batch = run_sqlmap_batch(scan_job_id, query_candidates, max_targets)
        if batch["blocked_reason"]:
            return []
        findings: list[dict] = []
        for execution in batch["executions"]:
            if not execution.result.confirmed:
                continue
            safe_url = redact_url_query_values(execution.target.url)
            findings.append(make_finding(
                category="security",
                severity="critical",
                rule_id="kali-sqlmap-sqli",
                title="SQL Injection 已由 sqlmap 主動驗證可利用",
                description=(
                    f"在授權的主動測試中，sqlmap 確認 {safe_url} 存在可被利用的 "
                    "SQL injection 注入點。此為已驗證漏洞，非僅靜態判斷。"
                ),
                remediation=(
                    "使用參數化查詢（prepared statements）或 ORM，"
                    "對所有使用者輸入做嚴格驗證與轉義，並以最小權限資料庫帳號連線。"
                ),
                evidence="",
                evidence_json={"evidence_summary": dict(execution.result.evidence_summary)},
                impact_area="vulnerability",
                confidence=1.0,
            ))
        return findings
    except ScanCancelled:
        raise
    except Exception:  # noqa: BLE001
        return []


def run_metasploit(module: str, options: dict, scan_job_id: int) -> dict:
    """docker exec <kali> msfconsole -q -x "use <module>; set ...; run; exit"。

    僅在 docker backend 支援；kubernetes / 未知 backend 一律回
    blocked_reason=tool_not_supported_by_backend，不會呼叫 docker。
    options 為 {key: value} 會轉成 `set key value`。
    """
    tool = "metasploit"
    blocked = _metasploit_preflight(tool, scan_job_id)
    if blocked is not None:
        return blocked

    if not module or any(c in module for c in (";", "&", "|", "`", "\n")):
        append_log(scan_job_id, f"Kali {tool} module 名稱不合法", level="warn")
        return _result(tool, ok=False, error="invalid_module")

    set_cmds = ""
    for key, value in (options or {}).items():
        skey = str(key).strip()
        sval = str(value).strip()
        if not skey or any(c in skey + sval for c in (";", "&", "|", "`", "\n")):
            append_log(scan_job_id, f"Kali {tool} option 不合法（{skey}）", level="warn")
            return _result(tool, ok=False, error="invalid_option")
        set_cmds += f"set {skey} {sval}; "

    resource = f"use {module}; {set_cmds}run; exit"
    timeout = getattr(settings, "ARGUS_KALI_TIMEOUT", 120)
    append_log(scan_job_id, f"Kali {tool} 執行 module：{module}", level="info")
    rc, out, err = _docker_exec(
        ["msfconsole", "-q", "-x", resource], timeout=timeout
    )
    if rc is None:
        append_log(scan_job_id, f"Kali {tool} 逾時/失敗（{err}）", level="warn")
        return _result(tool, ok=False, error=err)
    append_log(scan_job_id, f"Kali {tool} 完成（returncode={rc}）", level="info")
    return _result(tool, ok=(rc == 0), returncode=rc, stdout=out)
