"""security/kali_tools.py 的單元測試。

策略：mock subprocess 與 _container_running，不實際呼叫 docker；
重點驗證三重授權鎖、輸入驗證、silent-fail、回傳結構。
"""
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.scans.models import ScanJob
from apps.scans.security import kali_tools, owasp_mapper


def _make_scan(scan_mode="active", authorized=True):
    user = get_user_model().objects.create_user(
        username=f"user_{uuid.uuid4().hex[:8]}",
        password="testpass123",
    )
    return ScanJob.objects.create(
        user=user,
        original_url="https://target.local/",
        normalized_url="https://target.local/",
        origin="https://target.local",
        scan_mode=scan_mode,
        active_testing_authorized=authorized,
    )


@override_settings(ARGUS_KALI_ENABLED=True, ARGUS_KALI_CONTAINER="argus-kali-1")
class TestAuthorizationLock(TestCase):
    """三重授權鎖：任一不符就 blocked，不呼叫 docker。"""

    @override_settings(ARGUS_KALI_ENABLED=False)
    def test_kali_disabled_blocks(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_sqlmap("https://target.local", scan.id)
        self.assertFalse(res["ok"])
        self.assertEqual(res["blocked_reason"], "kali_disabled")
        m.assert_not_called()

    def test_passive_mode_blocks(self):
        scan = _make_scan(scan_mode="passive", authorized=True)
        with mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_sqlmap("https://target.local", scan.id)
        self.assertEqual(res["blocked_reason"], "scan_mode_not_active")
        m.assert_not_called()

    def test_unauthorized_blocks(self):
        # active 但未授權；繞過 model.clean 直接寫 DB 以模擬異常狀態
        scan = _make_scan(scan_mode="active", authorized=True)
        ScanJob.objects.filter(pk=scan.id).update(active_testing_authorized=False)
        with mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_sqlmap("https://target.local", scan.id)
        self.assertEqual(res["blocked_reason"], "active_testing_unauthorized")
        m.assert_not_called()

    def test_scan_not_found_blocks(self):
        with mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_sqlmap("https://target.local", 999999)
        self.assertEqual(res["blocked_reason"], "scan_not_found")
        m.assert_not_called()

    def test_container_not_running_blocks(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_container_running", return_value=False), \
                mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_sqlmap("https://target.local", scan.id)
        self.assertEqual(res["blocked_reason"], "container_not_running")
        m.assert_not_called()


@override_settings(ARGUS_KALI_ENABLED=True)
class TestRunSqlmap(TestCase):
    def test_invalid_target_url_rejected(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_sqlmap("ftp://evil", scan.id)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "invalid_target_url")
        m.assert_not_called()

    def test_success_returns_stdout(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(
                    kali_tools, "_docker_exec",
                    return_value=(0, "Parameter id is vulnerable", ""),
                ):
            res = kali_tools.run_sqlmap("https://target.local/?id=1", scan.id)
        self.assertTrue(res["ok"])
        self.assertEqual(res["returncode"], 0)
        self.assertIn("vulnerable", res["stdout"])

    def test_timeout_is_silent_fail(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(
                    kali_tools, "_docker_exec", return_value=(None, "", "timeout")
                ):
            res = kali_tools.run_sqlmap("https://target.local", scan.id)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "timeout")

    def test_stdout_truncated(self):
        scan = _make_scan()
        long_out = "A" * 9999
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(
                    kali_tools, "_docker_exec", return_value=(0, long_out, "")
                ):
            res = kali_tools.run_sqlmap("https://target.local", scan.id)
        self.assertLessEqual(len(res["stdout"]), kali_tools.MAX_STDOUT_CHARS)


@override_settings(ARGUS_KALI_ENABLED=True)
class TestRunMetasploit(TestCase):
    def test_invalid_module_rejected(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_metasploit("evil; rm -rf /", {}, scan.id)
        self.assertEqual(res["error"], "invalid_module")
        m.assert_not_called()

    def test_injection_in_option_rejected(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(kali_tools, "_docker_exec") as m:
            res = kali_tools.run_metasploit(
                "exploit/multi/misc/log4shell",
                {"RHOSTS": "1.2.3.4; cat /etc/passwd"},
                scan.id,
            )
        self.assertEqual(res["error"], "invalid_option")
        m.assert_not_called()

    def test_success_builds_resource_and_runs(self):
        scan = _make_scan()
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(
                    kali_tools, "_docker_exec", return_value=(0, "session opened", "")
                ) as m:
            res = kali_tools.run_metasploit(
                "exploit/multi/misc/log4shell",
                {"RHOSTS": "10.0.0.5", "LHOST": "10.0.0.1"},
                scan.id,
            )
        self.assertTrue(res["ok"])
        # 確認 docker exec 收到組好的 -x resource 字串
        called_args = m.call_args[0][0]
        resource = called_args[-1]
        self.assertIn("use exploit/multi/misc/log4shell", resource)
        self.assertIn("set RHOSTS 10.0.0.5", resource)
        self.assertIn("run; exit", resource)


class TestValidateFindingsWithKali(TestCase):
    """validate_findings_with_kali 編排層：候選挑選、gating 早停、漏洞→Finding。"""

    def test_no_param_urls_returns_empty(self):
        urls = ["https://t.local/", "https://t.local/about"]
        with mock.patch.object(kali_tools, "run_sqlmap") as m:
            out = kali_tools.validate_findings_with_kali(1, urls)
        self.assertEqual(out, [])
        m.assert_not_called()

    def test_blocked_on_first_stops_early(self):
        urls = ["https://t.local/?id=1", "https://t.local/?p=2"]
        with mock.patch.object(
            kali_tools, "run_sqlmap",
            return_value={"ok": False, "blocked_reason": "kali_disabled",
                          "stdout": "", "error": "", "tool": "sqlmap",
                          "returncode": None},
        ) as m:
            out = kali_tools.validate_findings_with_kali(1, urls)
        self.assertEqual(out, [])
        self.assertEqual(m.call_count, 1)  # 第一個被擋就停

    def test_vulnerable_produces_critical_finding(self):
        urls = ["https://t.local/?id=1"]
        vuln = {"ok": True, "blocked_reason": "", "returncode": 0,
                "stdout": "Parameter 'id' is vulnerable. ", "error": "", "tool": "sqlmap"}
        with mock.patch.object(kali_tools, "run_sqlmap", return_value=vuln):
            out = kali_tools.validate_findings_with_kali(1, urls)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["severity"], "critical")
        self.assertEqual(out[0]["rule_id"], "kali-sqlmap-sqli")
        self.assertEqual(out[0]["category"], "security")

    def test_not_vulnerable_no_finding(self):
        urls = ["https://t.local/?id=1"]
        clean = {"ok": True, "blocked_reason": "", "returncode": 0,
                 "stdout": "all tested parameters do not appear to be injectable",
                 "error": "", "tool": "sqlmap"}
        with mock.patch.object(kali_tools, "run_sqlmap", return_value=clean):
            out = kali_tools.validate_findings_with_kali(1, urls)
        self.assertEqual(out, [])

    def test_max_targets_cap(self):
        urls = [f"https://t.local/?id={i}" for i in range(10)]
        clean = {"ok": True, "blocked_reason": "", "returncode": 0,
                 "stdout": "not injectable", "error": "", "tool": "sqlmap"}
        with mock.patch.object(kali_tools, "run_sqlmap", return_value=clean) as m:
            kali_tools.validate_findings_with_kali(1, urls, max_targets=2)
        self.assertEqual(m.call_count, 2)


class TestKaliOwaspMapping(TestCase):
    def test_sqlmap_finding_maps_to_a03(self):
        self.assertEqual(owasp_mapper._lookup("kali-sqlmap-sqli"), ("A03", "CWE-89"))
