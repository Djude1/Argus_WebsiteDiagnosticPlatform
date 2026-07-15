"""kali-runner/runner.py 的單元測試。

策略：所有外部 I/O（subprocess、socket.getaddrinfo、檔案讀取）皆以 mock 注入；
不依賴 K8s Secret、DNS 或 sqlmap binary。測試涵蓋 brief 列舉的全部情境：
never-leak、timeout、malformed input、>3 targets、duplicate indices、cross-origin
batch、private DNS、queryless URL、nonzero return code、16384-byte size guard、
--self-test，再加上命令形狀、schema 契約與正向驗證。
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# 無論從 repo root（brief 指定的 `uv run python -m unittest discover -s
# kali-runner/tests`）或從 kali-runner/ 目錄執行，都能讓 `import runner`
# 找到 runner 模組。不加這行時，unittest 只把 start dir（kali-runner/tests）
# 加入 sys.path，import runner 會 ModuleNotFoundError。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import runner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_targets(path: Path, document: object) -> None:
    """把任意物件以 JSON 寫入暫存 targets 檔。"""
    path.write_text(
        json.dumps(document) if not isinstance(document, str) else document,
        encoding="utf-8",
    )


def _run_main(argv: list[str]) -> tuple[int, str]:
    """擷取 main() 的 return code 與 stdout 內容。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = runner.main(argv)
    return rc, buf.getvalue()


def _public_ipv4() -> list[tuple]:
    """回傳一組模擬的公開 IPv4 getaddrinfo 結果。"""
    return [
        (socket_af, socket_sock, socket_proto, "", ("93.184.216.34", 0))
        for socket_af, socket_sock, socket_proto in [
            (2, 1, 6),  # AF_INET, SOCK_STREAM, IPPROTO_TCP
        ]
    ]


# ---------------------------------------------------------------------------
# Command shape
# ---------------------------------------------------------------------------

class CommandForTests(unittest.TestCase):
    def test_returns_pinned_arguments_with_sys_executable_and_indexed_output_dir(self):
        cmd = runner.command_for(7, "https://example.com/?id=1")
        self.assertEqual(cmd[0], runner.sys.executable)
        self.assertIn("/opt/sqlmap/sqlmap.py", cmd)
        self.assertIn("--level=1", cmd)
        self.assertIn("--risk=1", cmd)
        self.assertIn("--threads=1", cmd)
        self.assertIn("--batch", cmd)
        # 不同 index 必須對應不同 output dir，避免 session 交叉污染。
        self.assertIn("--output-dir=/tmp/sqlmap-7", cmd)
        self.assertNotIn("--output-dir=/tmp/sqlmap-0", cmd)

    def test_user_agent_is_pinned_to_authorized_audit_string(self):
        cmd = runner.command_for(0, "https://example.com/?id=1")
        self.assertIn(
            "--user-agent=SiteSense-AI-Scanner/1.0 (authorized-audit)",
            cmd,
        )


# ---------------------------------------------------------------------------
# parse_sqlmap_stdout
# ---------------------------------------------------------------------------

class ParseSqlmapStdoutTests(unittest.TestCase):
    def test_extracts_parameter_techniques_dbms_and_confirmed_flag(self):
        stdout = (
            "Parameter: id (GET)\n"
            "    Type: boolean-based blind\n"
            "    Type: union query\n"
            "Parameter 'id' is vulnerable\n"
            "back-end DBMS: MySQL 5.0\n"
        )
        parameter, techniques, dbms, confirmed = runner.parse_sqlmap_stdout(stdout)
        self.assertEqual(parameter, "id")
        self.assertEqual(
            techniques, ["boolean-based blind", "union query"],
        )
        # DBMS 安全字元集為 [A-Za-z0-9 ._-]，整段都會通過。
        self.assertEqual(dbms, "MySQL 5.0")
        self.assertTrue(confirmed)

    def test_drops_unknown_technique_names_silently(self):
        stdout = (
            "Parameter: id (GET)\n"
            "    Type: evil-technique-not-in-whitelist\n"
            "    Type: time-based blind\n"
        )
        _, techniques, _, _ = runner.parse_sqlmap_stdout(stdout)
        self.assertEqual(techniques, ["time-based blind"])

    def test_truncates_overlong_dbms_and_parameter_safely(self):
        huge_param = "a" * 200
        huge_dbms = "X" * 200
        stdout = (
            f"Parameter: {huge_param} (GET)\n"
            f"back-end DBMS: {huge_dbms}\n"
        )
        parameter, _, dbms, _ = runner.parse_sqlmap_stdout(stdout)
        self.assertLessEqual(len(parameter), 64)
        self.assertLessEqual(len(dbms), 64)
        # 安全字元集：parameter 必須符合 [A-Za-z0-9_.-]{0,64}，dbms 必須
        # 符合 [A-Za-z0-9 ._-]{0,64}。
        import re
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_.-]{0,64}", parameter))
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9 ._-]{0,64}", dbms))

    def test_dbms_with_realistic_invalid_chars_is_sanitized(self):
        # sqlmap 實際輸出常含 '>='、版本號等不在安全字元集 [A-Za-z0-9 ._-]
        # 內的符號；runner 必須截斷至安全前綴，不可讓 '>'、'=' 洩入輸出。
        import re
        stdout = (
            "Parameter: id (GET)\n"
            "Parameter 'id' is vulnerable\n"
            "back-end DBMS: MySQL >= 5.0.12\n"
        )
        _, _, dbms, _ = runner.parse_sqlmap_stdout(stdout)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9 ._-]{0,64}", dbms))
        self.assertNotIn(">", dbms)
        self.assertNotIn("=", dbms)
        self.assertTrue(dbms.startswith("MySQL"))

    def test_no_injection_marker_leaves_confirmed_false(self):
        parameter, techniques, dbms, confirmed = runner.parse_sqlmap_stdout(
            "sqlmap finished without finding anything\n"
        )
        self.assertFalse(confirmed)
        self.assertEqual(parameter, "")
        self.assertEqual(techniques, [])
        self.assertEqual(dbms, "")


# ---------------------------------------------------------------------------
# run_target
# ---------------------------------------------------------------------------

class RunTargetTests(unittest.TestCase):
    def _completed(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        return subprocess.CompletedProcess(
            args=["sqlmap"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_never_prints_raw_stdout_or_target_url(self):
        completed = self._completed(
            stdout=(
                "Parameter: id (GET)\n"
                "    Type: boolean-based blind\n"
                "Parameter 'id' is vulnerable\n"
                "back-end DBMS: MySQL\n"
                "secret-row-value"
            ),
        )
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            result = runner.run_target(0, "https://fixture.test/?id=secret")
        encoded = json.dumps(result)
        self.assertTrue(result["confirmed"])
        self.assertNotIn("secret", encoded)
        self.assertNotIn("fixture.test", encoded)

    def test_zero_return_code_without_injection_is_ok_not_confirmed(self):
        completed = self._completed(
            stdout="sqlmap scanned the target and found no injection\n",
            returncode=0,
        )
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            result = runner.run_target(0, "https://example.com/?id=1")
        self.assertTrue(result["ok"])
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["error_code"], "")

    def test_nonzero_return_code_marked_runner_failure(self):
        completed = self._completed(
            stdout="usage: sqlmap.py [options]\n",
            returncode=1,
        )
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            result = runner.run_target(2, "https://example.com/?id=1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["returncode"], 1)
        self.assertEqual(result["error_code"], "runner_failure")
        self.assertFalse(result["confirmed"])

    def test_timeout_returns_safe_failure_without_raw_output(self):
        def _raise(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="sqlmap", timeout=120)

        with mock.patch.object(runner.subprocess, "run", side_effect=_raise):
            result = runner.run_target(0, "https://example.com/?id=1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "runner_timeout")
        self.assertIsNone(result["returncode"])
        # 結果 dict 不得帶任何 hint about the URL 或 sqlmap stdout。
        encoded = json.dumps(result)
        self.assertNotIn("example.com", encoded)

    def test_unexpected_exception_marked_runner_failure(self):
        def _raise(*args, **kwargs):
            raise OSError("disk full")

        with mock.patch.object(runner.subprocess, "run", side_effect=_raise):
            result = runner.run_target(0, "https://example.com/?id=1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "runner_failure")

    def test_result_keys_exactly_match_eight_field_contract(self):
        completed = self._completed(stdout="")
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            result = runner.run_target(0, "https://example.com/?id=1")
        self.assertEqual(
            set(result),
            {
                "index", "ok", "confirmed", "returncode",
                "parameter", "techniques", "dbms", "error_code",
            },
        )


# ---------------------------------------------------------------------------
# validate_batch
# ---------------------------------------------------------------------------

class ValidateBatchTests(unittest.TestCase):
    def setUp(self):
        # 預設讓 DNS 解析回傳一組公開 IPv4；個別測試可覆寫。
        self._dns = mock.patch.object(
            runner.socket, "getaddrinfo",
            return_value=_public_ipv4(),
        )
        self._dns.start()
        self.addCleanup(self._dns.stop)

    def test_valid_public_batch_passes(self):
        targets = [
            (0, "https://example.com/path?id=1"),
            (1, "https://example.com/other?id=2"),
        ]
        self.assertIsNone(runner.validate_batch(targets))

    def test_invalid_scheme_marked_invalid_scheme(self):
        targets = [(0, "file:///etc/passwd?id=1")]
        self.assertEqual(runner.validate_batch(targets), "invalid_scheme")

    def test_userinfo_in_url_marked_userinfo_forbidden(self):
        targets = [(0, "https://user:pw@example.com/?id=1")]
        self.assertEqual(
            runner.validate_batch(targets), "userinfo_forbidden",
        )

    def test_non_80_443_port_marked_invalid_port(self):
        targets = [(0, "https://example.com:8080/?id=1")]
        self.assertEqual(runner.validate_batch(targets), "invalid_port")

    def test_queryless_url_marked_no_query_parameter(self):
        targets = [(0, "https://example.com/path")]
        self.assertEqual(
            runner.validate_batch(targets), "no_query_parameter",
        )

    def test_private_dns_marked_target_not_public(self):
        private = [(2, 1, 6, "", ("10.0.0.1", 0))]
        with mock.patch.object(runner.socket, "getaddrinfo", return_value=private):
            result = runner.validate_batch(
                [(0, "https://internal.example/?id=1")],
            )
        self.assertEqual(result, "target_not_public")

    def test_loopback_ipv6_marked_target_not_public(self):
        loopback = [
            (10, 1, 6, "", ("::1", 0, 0, 0)),
        ]
        with mock.patch.object(runner.socket, "getaddrinfo", return_value=loopback):
            result = runner.validate_batch(
                [(0, "https://localhost/?id=1")],
            )
        self.assertEqual(result, "target_not_public")

    def test_dns_failure_marked_target_not_public(self):
        with mock.patch.object(
            runner.socket, "getaddrinfo", side_effect=runner.socket.gaierror,
        ):
            result = runner.validate_batch(
                [(0, "https://nonexistent.invalid/?id=1")],
            )
        self.assertEqual(result, "target_not_public")

    def test_cross_origin_batch_marked_cross_origin_forbidden(self):
        targets = [
            (0, "https://a.example/?id=1"),
            (1, "https://b.example/?id=2"),
        ]
        self.assertEqual(
            runner.validate_batch(targets), "cross_origin_forbidden",
        )

    def test_different_scheme_same_host_marked_cross_origin_forbidden(self):
        targets = [
            (0, "http://example.com/?id=1"),
            (1, "https://example.com/?id=2"),
        ]
        self.assertEqual(
            runner.validate_batch(targets), "cross_origin_forbidden",
        )

    def test_different_port_same_host_marked_cross_origin_forbidden(self):
        targets = [
            (0, "http://example.com/?id=1"),    # implicit port 80
            (1, "https://example.com/?id=2"),   # implicit port 443
        ]
        self.assertEqual(
            runner.validate_batch(targets), "cross_origin_forbidden",
        )

    def test_explicit_default_port_matches_implicit(self):
        # 顯示指定 443 與 https 預設 443 應視為同源。
        targets = [
            (0, "https://example.com:443/?id=1"),
            (1, "https://example.com/?id=2"),
        ]
        self.assertIsNone(runner.validate_batch(targets))

    def test_malformed_url_marked_malformed_url(self):
        targets = [(0, "not a url at all")]
        self.assertEqual(runner.validate_batch(targets), "malformed_url")


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._targets_path = Path(self._tmpdir.name) / "targets.json"
        self._patch_path = mock.patch.object(
            runner, "TARGETS_PATH", str(self._targets_path),
        )
        self._patch_path.start()
        self.addCleanup(self._patch_path.stop)
        # 預設讓 DNS 回公開 IPv4，避免測試真的去查 DNS。
        self._dns = mock.patch.object(
            runner.socket, "getaddrinfo",
            return_value=_public_ipv4(),
        )
        self._dns.start()
        self.addCleanup(self._dns.stop)

    def _write(self, document):
        _write_targets(self._targets_path, document)

    def test_self_test_prints_canonical_payload_without_reading_secret(self):
        # 故意不寫 targets 檔；--self-test 必須不讀檔就印出固定 payload。
        rc, stdout = _run_main(["--self-test"])
        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            '{"schema_version":1,"tool":"sqlmap","results":[]}',
        )

    def test_malformed_json_input_emits_empty_results_document(self):
        self._targets_path.write_text("not json {", encoding="utf-8")
        rc, stdout = _run_main([])
        self.assertEqual(rc, 0)
        document = json.loads(stdout)
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["tool"], "sqlmap")
        self.assertEqual(document["results"], [])

    def test_more_than_three_targets_emits_empty_results_document(self):
        self._write({
            "schema_version": 1,
            "scan_id": 1,
            "targets": [
                {"index": i, "url": f"https://example.com/?id={i}"}
                for i in range(4)
            ],
        })
        rc, stdout = _run_main([])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(stdout)["results"], [])

    def test_duplicate_indices_emits_empty_results_document(self):
        self._write({
            "schema_version": 1,
            "scan_id": 1,
            "targets": [
                {"index": 0, "url": "https://example.com/?id=1"},
                {"index": 0, "url": "https://example.com/?id=2"},
            ],
        })
        rc, stdout = _run_main([])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(stdout)["results"], [])

    def test_cross_origin_batch_marks_all_items_cross_origin_forbidden(self):
        self._write({
            "schema_version": 1,
            "scan_id": 1,
            "targets": [
                {"index": 0, "url": "https://a.example/?id=1"},
                {"index": 1, "url": "https://b.example/?id=2"},
            ],
        })
        rc, stdout = _run_main([])
        self.assertEqual(rc, 0)
        document = json.loads(stdout)
        for item in document["results"]:
            self.assertFalse(item["ok"])
            self.assertEqual(item["error_code"], "cross_origin_forbidden")

    def test_private_dns_batch_marks_all_items_target_not_public(self):
        self._dns.stop()
        private = [(2, 1, 6, "", ("10.0.0.1", 0))]
        with mock.patch.object(runner.socket, "getaddrinfo", return_value=private):
            self._write({
                "schema_version": 1,
                "scan_id": 1,
                "targets": [{"index": 0, "url": "https://internal.test/?id=1"}],
            })
            rc, stdout = _run_main([])
        self.assertEqual(rc, 0)
        item = json.loads(stdout)["results"][0]
        self.assertFalse(item["ok"])
        self.assertEqual(item["error_code"], "target_not_public")

    def test_happy_path_emits_one_result_per_target(self):
        completed = subprocess.CompletedProcess(
            args=["sqlmap"], returncode=0,
            stdout=(
                "Parameter: id (GET)\n"
                "    Type: boolean-based blind\n"
                "Parameter 'id' is vulnerable\n"
                "back-end DBMS: MySQL\n"
            ),
            stderr="",
        )
        self._write({
            "schema_version": 1,
            "scan_id": 1,
            "targets": [
                {"index": 0, "url": "https://example.com/?id=1"},
                {"index": 1, "url": "https://example.com/?id=2"},
            ],
        })
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            rc, stdout = _run_main([])
        self.assertEqual(rc, 0)
        document = json.loads(stdout)
        self.assertEqual(
            [r["index"] for r in document["results"]], [0, 1],
        )
        for item in document["results"]:
            self.assertTrue(item["ok"])
            self.assertTrue(item["confirmed"])
            self.assertEqual(item["parameter"], "id")
            self.assertEqual(item["techniques"], ["boolean-based blind"])
            self.assertEqual(item["dbms"], "MySQL")

    def test_output_never_contains_full_query_value(self):
        completed = subprocess.CompletedProcess(
            args=["sqlmap"], returncode=0,
            stdout=(
                "Parameter: id (GET)\n"
                "    Type: boolean-based blind\n"
                "Parameter 'id' is vulnerable\n"
                "back-end DBMS: MySQL\n"
                "leaked-database-row-content"
            ),
            stderr="",
        )
        self._write({
            "schema_version": 1,
            "scan_id": 1,
            "targets": [
                {"index": 0, "url": "https://example.com/?id=ULTRA_SECRET_VALUE"},
            ],
        })
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            rc, stdout = _run_main([])
        self.assertNotIn("ULTRA_SECRET_VALUE", stdout)
        self.assertNotIn("leaked-database-row-content", stdout)

    def test_output_top_level_keys_exactly_match_contract(self):
        self._write({
            "schema_version": 1,
            "scan_id": 1,
            "targets": [{"index": 0, "url": "https://example.com/?id=1"}],
        })
        completed = subprocess.CompletedProcess(
            args=["sqlmap"], returncode=0, stdout="", stderr="",
        )
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            rc, stdout = _run_main([])
        document = json.loads(stdout)
        self.assertEqual(set(document), {"schema_version", "tool", "results"})


# ---------------------------------------------------------------------------
# serialize_output() size guard
# ---------------------------------------------------------------------------

class SerializeSizeGuardTests(unittest.TestCase):
    def test_normal_payload_passes_through_unchanged(self):
        items = [{
            "index": 0, "ok": True, "confirmed": False, "returncode": 0,
            "parameter": "id", "techniques": [], "dbms": "", "error_code": "",
        }]
        encoded = runner.serialize_output(items)
        self.assertLessEqual(len(encoded), 16384)
        document = json.loads(encoded.decode("utf-8"))
        self.assertEqual(document["results"][0]["parameter"], "id")

    def test_oversized_payload_replaced_with_runner_output_too_large(self):
        # 構造一份遠超 16384 bytes 的 results，驗證 size guard 改寫成 placeholder。
        # 3 個 items × 6000-byte parameter 必定超過 16384 bytes 上限。
        huge_param = "X" * 6000  # 通過 [A-Za-z0-9_.-] 但串起來會爆
        items = [
            {
                "index": i, "ok": True, "confirmed": False, "returncode": 0,
                "parameter": huge_param, "techniques": [], "dbms": "",
                "error_code": "",
            }
            for i in range(3)
        ]
        encoded = runner.serialize_output(items)
        self.assertLessEqual(len(encoded), 16384)
        document = json.loads(encoded.decode("utf-8"))
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["tool"], "sqlmap")
        self.assertEqual(len(document["results"]), 3)
        for item in document["results"]:
            self.assertFalse(item["ok"])
            self.assertEqual(item["error_code"], "runner_output_too_large")
            self.assertEqual(item["parameter"], "")
            self.assertEqual(item["techniques"], [])
            self.assertEqual(item["dbms"], "")
            self.assertIsNone(item["returncode"])

    def test_placeholder_still_carries_original_index(self):
        items = [
            {
                "index": idx, "ok": True, "confirmed": False, "returncode": 0,
                "parameter": "Y" * 6000, "techniques": [], "dbms": "",
                "error_code": "",
            }
            for idx in (3, 7, 11)
        ]
        encoded = runner.serialize_output(items)
        document = json.loads(encoded.decode("utf-8"))
        self.assertEqual([r["index"] for r in document["results"]], [3, 7, 11])


if __name__ == "__main__":
    unittest.main()
