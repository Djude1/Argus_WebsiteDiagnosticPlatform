"""Hermes-Agent / 掃描流程呼叫 Kali container 的主動驗證工具（Phase 3 攻擊鏈）。

設計原則（嚴格遵守 security/CLAUDE.md）：
- **三重授權鎖**：ARGUS_KALI_ENABLED（全域開關）且 scan_mode=active 且
  active_testing_authorized=True 才會真正執行；任一不符 → 回傳 blocked，不呼叫 docker。
- 透過 `docker exec <container> <tool>` 呼叫，工具本身（sqlmap/metasploit）裝在 Kali container 內，
  本機/worker 不安裝攻擊工具（職責分離）。
- 任何例外 silent-fail，回傳結構化 dict，不丟出例外、不影響主掃描流程。
- 所有呼叫（含被擋）都記錄進 ScanJob.scan_log（append_log）。
- subprocess 一律用 list 形式（非 shell=True），避免命令注入。
- stdout 截短，避免吃光 Agent context / DB。

回傳格式統一為 dict：
  {"ok": bool, "tool": str, "blocked_reason": str, "returncode": int|None,
   "stdout": str, "error": str}
"""

from __future__ import annotations

import shutil
import subprocess
from urllib.parse import urlparse

from django.conf import settings

from apps.scans.scan_logger import append_log
from apps.scans.scanners import make_finding

MAX_STDOUT_CHARS = 3000

# sqlmap 確認注入點時的輸出特徵（小寫比對）
# 注意：不可用 "injectable" 當特徵——sqlmap 找不到時會印
# "do not appear to be injectable"，會造成假陽性。
_SQLI_MARKERS = ("is vulnerable", "injection point")


def _result(
    tool: str,
    ok: bool = False,
    blocked_reason: str = "",
    returncode: int | None = None,
    stdout: str = "",
    error: str = "",
) -> dict:
    """統一回傳結構。"""
    return {
        "ok": ok,
        "tool": tool,
        "blocked_reason": blocked_reason,
        "returncode": returncode,
        "stdout": stdout[:MAX_STDOUT_CHARS],
        "error": error,
    }


def _authorization_block_reason(scan_job_id: int) -> str:
    """檢查三重授權鎖；通過回空字串，否則回擋下原因（不含任何機密）。"""
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
    try:
        proc = subprocess.run(
            ["docker", "exec", container, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    except Exception as exc:  # noqa: BLE001
        return None, "", exc.__class__.__name__


def _preflight(tool: str, scan_job_id: int) -> dict | None:
    """授權鎖 + container 檢查；可執行回 None，否則回 blocked result（已寫 log）。"""
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


def run_sqlmap(target_url: str, scan_job_id: int) -> dict:
    """docker exec <kali> sqlmap -u <target_url> --batch，驗證 SQL injection。

    三重授權鎖未通過或 container 未運行時回傳 blocked，不會呼叫 docker。
    """
    tool = "sqlmap"
    blocked = _preflight(tool, scan_job_id)
    if blocked is not None:
        return blocked

    parsed = urlparse(target_url or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        append_log(scan_job_id, f"Kali {tool} 目標 URL 不合法", level="warn")
        return _result(tool, ok=False, error="invalid_target_url")

    timeout = getattr(settings, "ARGUS_KALI_TIMEOUT", 120)
    append_log(scan_job_id, f"Kali {tool} 開始驗證：{parsed.netloc}", level="info")
    rc, out, err = _docker_exec(
        ["sqlmap", "-u", target_url, "--batch", "--output-dir=/tmp/sqlmap"],
        timeout=timeout,
    )
    if rc is None:
        append_log(scan_job_id, f"Kali {tool} 逾時/失敗（{err}）", level="warn")
        return _result(tool, ok=False, error=err)
    append_log(scan_job_id, f"Kali {tool} 完成（returncode={rc}）", level="info")
    return _result(tool, ok=(rc == 0), returncode=rc, stdout=out)


def _stdout_indicates_sqli(stdout: str) -> bool:
    """從 sqlmap 輸出判斷是否確認存在 SQL injection。"""
    low = (stdout or "").lower()
    return any(m in low for m in _SQLI_MARKERS)


def validate_findings_with_kali(
    scan_job_id: int, candidate_urls: list[str], max_targets: int = 3
) -> list[dict]:
    """對帶參數的候選 URL 跑 sqlmap 主動驗證，回傳已確認漏洞的 Finding dict list。

    - gating 完全交給 run_sqlmap 的三重授權鎖；未啟用/未授權時第一次即被擋 → 直接停、回 []。
    - 只挑帶 query 參數的 URL（sqlmap 需要可注入點），最多 max_targets 個，避免拖長掃描。
    - 只在 sqlmap 確認可注入時產出 Finding（critical）；找不到則僅由 run_sqlmap 記 log。
    - 任何例外 silent-fail，不影響主掃描流程。
    """
    try:
        targets = [
            u for u in (candidate_urls or [])
            if "?" in str(u) and "=" in str(u)
        ][:max_targets]
        if not targets:
            return []
        findings: list[dict] = []
        for url in targets:
            res = run_sqlmap(url, scan_job_id)
            # 第一個就被授權鎖擋下 → 全域未啟用，沒必要繼續
            if res.get("blocked_reason"):
                break
            if not res.get("ok"):
                continue
            if _stdout_indicates_sqli(res.get("stdout", "")):
                findings.append(make_finding(
                    category="security", severity="critical",
                    rule_id="kali-sqlmap-sqli",
                    title="SQL Injection 已由 sqlmap 主動驗證可利用",
                    description=(
                        f"在授權的主動測試中，sqlmap 確認 {url} 存在可被利用的 "
                        "SQL injection 注入點。此為已驗證漏洞，非僅靜態判斷。"
                    ),
                    remediation=(
                        "使用參數化查詢（prepared statements）或 ORM，"
                        "對所有使用者輸入做嚴格驗證與轉義，並以最小權限資料庫帳號連線。"
                    ),
                    evidence=res.get("stdout", "")[:1000],
                    impact_area="vulnerability", confidence=1.0,
                ))
        return findings
    except Exception:
        return []


def run_metasploit(module: str, options: dict, scan_job_id: int) -> dict:
    """docker exec <kali> msfconsole -q -x "use <module>; set ...; run; exit"，執行指定 module。

    options 為 {key: value} 會轉成 `set key value`；三重授權鎖未通過時回 blocked。
    """
    tool = "metasploit"
    blocked = _preflight(tool, scan_job_id)
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
