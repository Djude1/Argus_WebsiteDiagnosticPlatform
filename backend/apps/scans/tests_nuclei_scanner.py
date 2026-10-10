"""nuclei_scanner 模組的單元測試（模板治理：固定模板集、只掃根網址、逾時保留部分結果）。"""
import http.server
import json
import shutil
import subprocess
import tempfile
import textwrap
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.scans.cancellation import ScanCancelled
from apps.scans.nuclei_scanner import (
    TEMPLATE_POLICY,
    NucleiUnavailable,
    _describe_template_set,
    run_nuclei,
    template_set_info,
)

TEMPLATE_SET = {
    "policy": "kev", "templates_version": "v10.4.9", "templates": 511,
    "sha256": "a" * 64, "engine": "v3.8.0",
}


def _record(template_id="CVE-2021-44228", name="Log4Shell RCE", severity="critical"):
    return json.dumps({
        "template-id": template_id,
        "info": {"name": name, "severity": severity, "tags": ["cve", "rce"]},
        "matched-at": "https://example.com/",
    })


class RunNucleiTests(TestCase):
    """run_nuclei 的指令與結果處理（patch append_log，避免寫入 DB）。"""

    def _run(self, *, stdout="", returncode=0, side_effect=None, **kwargs):
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value="/usr/bin/nuclei"),
            patch("apps.scans.nuclei_scanner.template_set_info", return_value=TEMPLATE_SET),
            patch("apps.scans.nuclei_scanner.run_cancellable_process") as mock_run,
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            mock_run.return_value = MagicMock(stdout=stdout, returncode=returncode)
            if side_effect is not None:
                mock_run.side_effect = side_effect
            result = run_nuclei(kwargs.pop("url", "https://example.com/a/b?q=1"), 1, **kwargs)
        return result, mock_run

    @override_settings(ARGUS_NUCLEI_TEMPLATES_DIR="/opt/nuclei-templates", ARGUS_NUCLEI_TIMEOUT=660)
    def test_command_uses_pinned_templates_kev_policy_and_root_url(self):
        result, mock_run = self._run()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("-u") + 1], "https://example.com/")
        self.assertEqual(cmd[cmd.index("-t") + 1], "/opt/nuclei-templates")
        self.assertEqual(cmd[cmd.index("-tags") + 1], "kev")
        self.assertEqual(cmd[cmd.index("-severity") + 1], TEMPLATE_POLICY["severity"])
        self.assertEqual(cmd[cmd.index("-etags") + 1], TEMPLATE_POLICY["exclude_tags"])
        self.assertEqual(cmd[cmd.index("-pt") + 1], "http")
        for flag in ("-duc", "-no-stdin", "-lna", "-ni", "-dr", "-or"):
            self.assertIn(flag, cmd)
        self.assertNotIn("-l", cmd)
        self.assertEqual(cmd[cmd.index("-rl") + 1], "2")
        self.assertEqual(mock_run.call_args.kwargs["timeout"], 660)
        self.assertEqual(result.template_set, TEMPLATE_SET)
        self.assertFalse(result.timed_out)

    def test_explicit_rate_limit_is_applied(self):
        _, mock_run = self._run(rate_limit=1)
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("-rl") + 1], "1")

    def test_parses_and_deduplicates_output(self):
        stdout = "NOT_JSON\n" + _record() + "\n" + _record() + "\n"
        result, _ = self._run(stdout=stdout)
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual((finding["title"], finding["severity"]), ("Log4Shell RCE", "critical"))
        self.assertIn("Template：CVE-2021-44228", finding["evidence"])
        self.assertEqual(finding["impact_area"], "known_vulnerability")

    def test_timeout_keeps_partial_results(self):
        timeout = subprocess.TimeoutExpired(cmd="nuclei", timeout=660, output=_record() + "\n")
        result, _ = self._run(side_effect=timeout)
        self.assertTrue(result.timed_out)
        self.assertEqual(len(result.findings), 1)

    def test_abnormal_exit_without_output_is_failure_not_zero_findings(self):
        with self.assertRaises(NucleiUnavailable):
            self._run(returncode=2)

    def test_missing_binary_is_failure(self):
        with (
            patch("apps.scans.nuclei_scanner.shutil.which", return_value=None),
            self.assertRaises(NucleiUnavailable),
        ):
            run_nuclei("https://example.com", 1)

    def test_scan_cancelled_is_not_silenced(self):
        with self.assertRaises(ScanCancelled):
            self._run(side_effect=ScanCancelled())

    def test_finding_redacts_query_values_and_extracted_results(self):
        from apps.scans.nuclei_scanner import _build_finding

        finding = _build_finding(
            {
                "template-id": "sensitive-output",
                "info": {"name": "Sensitive output", "severity": "high", "tags": []},
                "matched-at": (
                    "https://example.com/api?token=super-secret-value"
                    "&email=person@example.com"
                ),
                "extracted-results": ["raw-private-marker"],
            }
        )

        serialized = json.dumps(finding, ensure_ascii=False)
        self.assertNotIn("super-secret-value", serialized)
        self.assertNotIn("person@example.com", serialized)
        self.assertNotIn("raw-private-marker", serialized)
        self.assertIn("REDACTED", finding["evidence"])
        self.assertIn("1 筆", finding["evidence"])

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


class TemplateSetInfoTests(SimpleTestCase):
    def setUp(self):
        _describe_template_set.cache_clear()
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "http").mkdir()
        for name in ("a.yaml", "b.yaml"):
            (self.dir / "http" / name).write_text("id: x\n")
        (self.dir / "templates-checksum.txt").write_text("http/a.yaml:111\nhttp/b.yaml:222\n")
        (self.dir / ".argus-templates-version").write_text("v10.4.9\n")

    def _info(self, listed):
        listing = MagicMock(
            stdout="Listing available templates\n" + "".join(f"{p}\n" for p in listed), stderr="",
        )
        version = MagicMock(stdout="", stderr="[INF] Nuclei Engine Version: v3.8.0\n")
        with patch(
            "apps.scans.nuclei_scanner.subprocess.run",
            side_effect=lambda cmd, **kw: version if "-version" in cmd else listing,
        ):
            return template_set_info(str(self.dir))

    def test_records_versions_count_and_fingerprint(self):
        info = self._info([self.dir / "http/b.yaml", self.dir / "http/a.yaml"])
        self.assertEqual(info["engine"], "v3.8.0")
        self.assertEqual(info["templates_version"], "v10.4.9")
        self.assertEqual((info["policy"], info["templates"]), ("kev", 2))
        self.assertEqual(len(info["sha256"]), 64)

    def test_fingerprint_changes_with_template_content(self):
        before = self._info([self.dir / "http/a.yaml"])["sha256"]
        _describe_template_set.cache_clear()
        (self.dir / "templates-checksum.txt").write_text("http/a.yaml:999\nhttp/b.yaml:222\n")
        after = self._info([self.dir / "http/a.yaml"])["sha256"]
        self.assertNotEqual(before, after)

    def test_no_selected_templates_is_failure(self):
        with self.assertRaises(NucleiUnavailable):
            self._info([])

    def test_missing_directory_is_failure(self):
        with self.assertRaises(NucleiUnavailable):
            template_set_info(str(self.dir / "missing"))


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/slow"):
            threading.Event().wait(30)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"argus-marker")

    def log_message(self, *args):
        pass


@override_settings(DEBUG=True, ARGUS_ALLOW_PRIVATE_TARGETS=True, ARGUS_NUCLEI_TIMEOUT=6)
class RealNucleiTimeoutTests(TestCase):
    """真的執行 nuclei：逾時前已輸出的結果要保留（需要 nuclei binary，沒有就略過）。"""

    def setUp(self):
        if not shutil.which("nuclei"):
            self.skipTest("沒有 nuclei binary")
        _describe_template_set.cache_clear()
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        for template_id, path, word in (
            ("argus-fast", "/", "argus-marker"), ("argus-slow", "/slow", "never"),
        ):
            (self.dir / f"{template_id}.yaml").write_text(textwrap.dedent(f"""\
                id: {template_id}
                info: {{name: {template_id}, author: argus, severity: high, tags: kev}}
                http:
                  - method: GET
                    path: ["{{{{RootURL}}}}{path}"]
                    matchers: [{{type: word, words: ["{word}"]}}]
            """))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_timeout_keeps_results_found_before_timeout(self):
        url = f"http://127.0.0.1:{self.server.server_address[1]}/page"
        with (
            override_settings(ARGUS_NUCLEI_TEMPLATES_DIR=str(self.dir)),
            patch("apps.scans.nuclei_scanner.append_log"),
        ):
            result = run_nuclei(url, 0, rate_limit=10)
        self.assertTrue(result.timed_out)
        self.assertEqual([f["title"] for f in result.findings], ["argus-fast"])
        self.assertEqual(result.template_set["templates"], 2)
