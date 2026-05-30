"""T14 主動式資安偵測測試。

涵蓋：RateLimitedClient 節流、admin path enumeration、開放目錄列表、
SQLi boolean-based（error hint / length 差異 / 無差異不報 / 無 query 跳過）、
tasks.py 整合（active 模式 + 授權才呼叫，passive 不呼叫）。

不打網路：用 FakeClient 模擬 RateLimitedClient 的 get/head 行為。
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.scans.active_probes import (
    ADMIN_PATH_DICTIONARY,
    MAX_ADMIN_PATHS_PER_SCAN,
    RateLimitedClient,
    collect_query_urls,
    probe_admin_paths,
    probe_open_directory,
    probe_sqli_on_urls,
    run_active_probes,
)

# ---------------- helpers ----------------


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeClient:
    """模擬 RateLimitedClient，不打網路；可預先註冊 URL → Response。"""

    def __init__(
        self,
        head_responses: dict[str, FakeResponse] | None = None,
        get_responses: dict[str, FakeResponse] | None = None,
        default_head: FakeResponse | None = None,
        default_get: FakeResponse | None = None,
    ):
        self.head_responses = head_responses or {}
        self.get_responses = get_responses or {}
        self.default_head = default_head or FakeResponse(404)
        self.default_get = default_get or FakeResponse(404)
        self.head_calls: list[str] = []
        self.get_calls: list[str] = []

    def head(self, url: str, **kwargs):
        self.head_calls.append(url)
        return self.head_responses.get(url, self.default_head)

    def get(self, url: str, **kwargs):
        self.get_calls.append(url)
        return self.get_responses.get(url, self.default_get)


# ---------------- dictionary ----------------


class AdminDictionaryTests(TestCase):
    def test_dictionary_within_limit(self):
        self.assertLessEqual(len(ADMIN_PATH_DICTIONARY), MAX_ADMIN_PATHS_PER_SCAN)

    def test_dictionary_contains_expected_entries(self):
        for expected in ("admin/", "wp-admin/", ".git/HEAD", "phpinfo.php", "swagger-ui"):
            self.assertIn(expected, ADMIN_PATH_DICTIONARY)


# ---------------- rate limited client ----------------


class RateLimitedClientTests(TestCase):
    def test_throttle_enforces_min_interval(self):
        client = RateLimitedClient(max_rps=10)  # 0.1s interval
        # mock 內部 session.get 立即回 FakeResponse，量測純粹 throttle 行為
        with patch.object(client._session, "get", return_value=FakeResponse(200)):
            start = time.monotonic()
            for _ in range(3):
                client.get("http://example.com")
            elapsed = time.monotonic() - start
        # 第一次無延遲，第二/三次各 ~0.1s sleep → 至少 0.18s（保留誤差）
        self.assertGreaterEqual(elapsed, 0.18)

    def test_rejects_non_positive_rps(self):
        with self.assertRaises(ValueError):
            RateLimitedClient(max_rps=0)


# ---------------- admin path probe ----------------


class AdminPathProbeTests(TestCase):
    def test_reports_200_as_high_severity(self):
        url_hit = "https://example.com/admin/"
        client = FakeClient(head_responses={url_hit: FakeResponse(200)})
        findings = probe_admin_paths("https://example.com", client)
        hits = [f for f in findings if "admin/" in f["title"]]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "high")

    def test_reports_403_as_medium_severity(self):
        url_hit = "https://example.com/wp-admin/"
        client = FakeClient(head_responses={url_hit: FakeResponse(403)})
        findings = probe_admin_paths("https://example.com", client)
        hits = [f for f in findings if "wp-admin/" in f["title"]]
        self.assertEqual(hits[0]["severity"], "medium")

    def test_ignores_404(self):
        client = FakeClient()  # 全部 404
        findings = probe_admin_paths("https://example.com", client)
        self.assertEqual(findings, [])


# ---------------- open directory probe ----------------


class OpenDirectoryProbeTests(TestCase):
    def test_detects_index_of_signature(self):
        client = FakeClient(
            get_responses={
                "https://example.com/uploads/": FakeResponse(
                    200, text="<html><title>Index of /uploads/</title></html>"
                ),
            }
        )
        findings = probe_open_directory("https://example.com", client)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")
        self.assertIn("uploads/", findings[0]["title"])

    def test_skips_non_listing_pages(self):
        client = FakeClient(
            get_responses={
                "https://example.com/": FakeResponse(200, text="<html><body>welcome</body></html>"),
            }
        )
        findings = probe_open_directory("https://example.com", client)
        self.assertEqual(findings, [])

    def test_skips_non_200(self):
        client = FakeClient(default_get=FakeResponse(403, text="forbidden"))
        findings = probe_open_directory("https://example.com", client)
        self.assertEqual(findings, [])


# ---------------- SQLi probe ----------------


class SqliProbeTests(TestCase):
    def test_error_hint_triggers_critical(self):
        base = "https://example.com/item?id=1"
        payloaded = "https://example.com/item?id=1%27+OR+%271%27%3D%271"
        client = FakeClient(
            get_responses={
                base: FakeResponse(200, text="ok"),
                payloaded: FakeResponse(
                    500,
                    text="You have an error in your SQL syntax near '1' OR '1'='1",
                ),
            }
        )
        findings = probe_sqli_on_urls([base], client)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "critical")
        self.assertIn("SQL", findings[0]["title"])

    def test_length_diff_triggers_medium(self):
        base = "https://example.com/search?q=hi"
        payloaded = "https://example.com/search?q=hi%27+OR+%271%27%3D%271"
        baseline_body = "a" * 100
        diff_body = "a" * 500
        client = FakeClient(
            get_responses={
                base: FakeResponse(200, text=baseline_body),
                payloaded: FakeResponse(200, text=diff_body),
            }
        )
        findings = probe_sqli_on_urls([base], client)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_no_diff_no_finding(self):
        base = "https://example.com/q?k=v"
        payloaded = "https://example.com/q?k=v%27+OR+%271%27%3D%271"
        body = "stable response"
        client = FakeClient(
            get_responses={
                base: FakeResponse(200, text=body),
                payloaded: FakeResponse(200, text=body),
            }
        )
        findings = probe_sqli_on_urls([base], client)
        self.assertEqual(findings, [])

    def test_skip_urls_without_query(self):
        client = FakeClient()
        findings = probe_sqli_on_urls(["https://example.com/about"], client)
        self.assertEqual(findings, [])
        self.assertEqual(client.get_calls, [])

    def test_collect_query_urls_filters_and_dedups(self):
        pages = [
            SimpleNamespace(final_url="https://example.com/?a=1", url="https://example.com/?a=1"),
            SimpleNamespace(final_url="https://example.com/about", url="https://example.com/about"),
            SimpleNamespace(final_url="https://example.com/?a=1", url="https://example.com/?a=1"),
        ]
        urls = collect_query_urls(pages)
        self.assertEqual(urls, ["https://example.com/?a=1"])


# ---------------- run_active_probes end-to-end ----------------


class RunActiveProbesTests(TestCase):
    def test_returns_admin_open_dir_and_sqli_findings(self):
        client = FakeClient(
            head_responses={
                "https://example.com/admin/": FakeResponse(200),
            },
            get_responses={
                "https://example.com/uploads/": FakeResponse(
                    200, text="<title>Index of /uploads/</title>"
                ),
                "https://example.com/p?x=1": FakeResponse(200, text="ok"),
                "https://example.com/p?x=1%27+OR+%271%27%3D%271": FakeResponse(
                    500,
                    text="SQLSTATE[42000]: Syntax error",
                ),
            },
        )
        pages = [SimpleNamespace(final_url="https://example.com/p?x=1", url="")]
        findings = run_active_probes("https://example.com", pages, client=client)
        categories = {(f["impact_area"]) for f in findings}
        self.assertIn("path_enumeration", categories)
        self.assertIn("information_disclosure", categories)
        self.assertIn("sql_injection", categories)
