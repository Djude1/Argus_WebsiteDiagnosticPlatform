"""OWASP ZAP 被動分析（security/zap_passive.py、tasks.stage_zap_passive、crawler 錄 HAR）。

不需要 ZAP：以假的 ZapClient 驗證流程與清理。另有連真實 ZAP 的案例，設
ARGUS_TEST_ZAP_URL（例如 http://127.0.0.1:8090）與 ARGUS_TEST_ZAP_KEY 才跑
（ZAP 要開 api.filexfer）。
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from apps.scans import tasks
from apps.scans.coverage import COMPLETED, FAILED, SKIPPED
from apps.scans.crawler import _make_context
from apps.scans.models import Finding, ScanJob
from apps.scans.reports import _source_label
from apps.scans.scan_plan import build_scan_execution_plan
from apps.scans.security import zap_passive
from apps.scans.security.zap_passive import (
    ZapBusy,
    ZapClient,
    ZapError,
    alerts_to_findings,
    build_har,
    run_passive,
)

ORIGIN = "https://shop.example.test"
ZAP_URL = os.environ.get("ARGUS_TEST_ZAP_URL", "")
ZAP_KEY = os.environ.get("ARGUS_TEST_ZAP_KEY", "")


def _entry(url, *, body="<html></html>", mime="text/html", headers=None, req_headers=None):
    return {
        "startedDateTime": "2026-10-07T10:00:00.000Z", "time": 5,
        "request": {
            "method": "GET", "url": url, "httpVersion": "HTTP/1.1",
            "headers": req_headers or [{"name": "Cookie", "value": "sid=secret"},
                                       {"name": "Authorization", "value": "Bearer t"},
                                       {"name": "Accept", "value": "*/*"}],
            "queryString": [], "cookies": [{"name": "sid", "value": "secret"}],
            "headersSize": -1, "bodySize": 0,
        },
        "response": {
            "status": 200, "statusText": "OK", "httpVersion": "HTTP/1.1",
            "headers": headers or [{"name": "Content-Type", "value": mime},
                                   {"name": "Set-Cookie",
                                    "value": "sid=topsecret; Path=/; HttpOnly"}],
            "cookies": [{"name": "sid", "value": "topsecret"}],
            "content": {"size": len(body), "mimeType": mime, "text": body},
            "redirectURL": "", "headersSize": -1, "bodySize": len(body),
        },
        "cache": {}, "timings": {"send": 0, "wait": 5, "receive": 0},
    }


def _write_har(directory: Path, name: str, entries: list[dict]) -> Path:
    path = directory / name
    path.write_text(json.dumps({"log": {"version": "1.2", "entries": entries}}), encoding="utf-8")
    return path


def _alert(plugin, *, risk="Low", confidence="Medium", url=f"{ORIGIN}/", name="Rule", **extra):
    """與 ZAP alert/view/alerts 相同的欄位：risk 是文字，沒有數字代碼。"""
    return {"id": str(hash((plugin, url)) % 10000), "pluginId": plugin,
            "risk": risk, "confidence": confidence, "alert": name, "url": url,
            "description": "desc", "solution": "fix", "evidence": "ev", "param": "",
            "cweid": "829", "reference": "https://ref\nhttps://ref2", **extra}


class BuildHarTests(SimpleTestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_keeps_same_origin_and_strips_secrets(self):
        _write_har(self.dir, "a.har", [
            _entry(f"{ORIGIN}/"),
            _entry("https://cdn.other.test/x.js", mime="application/javascript"),
            _entry(f"{ORIGIN}/logo.png", mime="image/png", body="iVBORw0"),
        ])
        payload, count = build_har([self.dir / "a.har"], ORIGIN)
        self.assertEqual(count, 2)
        entries = json.loads(payload)["log"]["entries"]
        page = entries[0]
        names = {h["name"].lower() for h in page["request"]["headers"]}
        self.assertNotIn("cookie", names)
        self.assertNotIn("authorization", names)
        self.assertEqual(page["request"]["cookies"], [])
        set_cookie = next(h for h in page["response"]["headers"] if h["name"] == "Set-Cookie")
        # 保留屬性（ZAP 要判斷 HttpOnly／Secure），值遮蔽
        self.assertEqual(set_cookie["value"], "sid=argus-redacted; Path=/; HttpOnly")
        self.assertNotIn("topsecret", payload)
        self.assertNotIn("secret", json.dumps(page["request"]))
        # 圖片只留標頭，不送內容
        self.assertNotIn("text", entries[1]["response"]["content"])

    @override_settings(ARGUS_ZAP_MAX_ENTRIES=3, ARGUS_ZAP_MAX_BODY_CHARS=10)
    def test_limits(self):
        _write_har(self.dir, "a.har", [_entry(f"{ORIGIN}/{i}", body="x" * 50) for i in range(5)])
        _write_har(self.dir, "b.har", [_entry(f"{ORIGIN}/b")])
        payload, count = build_har(sorted(self.dir.glob("*.har")), ORIGIN)
        self.assertEqual(count, 3)
        first = json.loads(payload)["log"]["entries"][0]
        self.assertEqual(len(first["response"]["content"]["text"]), 10)

    def test_broken_files_are_ignored(self):
        (self.dir / "bad.har").write_text("{not json", encoding="utf-8")
        self.assertEqual(build_har([self.dir / "bad.har", self.dir / "missing.har"], ORIGIN)[1], 0)


class AlertsToFindingsTests(SimpleTestCase):
    def test_overlap_ignored_and_grouping(self):
        alerts = [
            _alert("10038", risk="Medium", name="CSP Header Not Set"),          # 與既有檢查重複
            _alert("10109", risk="Informational", name="Modern Web Application"),       # 雜訊
            _alert("10017", url=f"{ORIGIN}/", name="Cross-Domain JavaScript Source File Inclusion"),
            _alert("10017", url=f"{ORIGIN}/about",
                   name="Cross-Domain JavaScript Source File Inclusion"),
            _alert("10027", risk="Informational", confidence="Low", name="Suspicious Comments"),
            _alert("10040", risk="Medium", confidence="Low", name="Mixed Content"),
            _alert("99999", risk="High", confidence="High", name="Something New"),
            _alert("10024", risk="Medium", confidence="False Positive"),
        ]
        findings, overlap = alerts_to_findings(alerts, "2.16.1")
        by_rule = {f["rule_id"]: f for f in findings}
        self.assertEqual(set(by_rule), {"zap-10017", "zap-10027", "zap-10040", "zap-99999"})
        self.assertEqual(overlap, {"CSP（安全標頭）": 1})
        cross = by_rule["zap-10017"]
        self.assertEqual(cross["title"], "引用其他網域的 JavaScript")
        self.assertEqual(cross["category"], "security")
        self.assertEqual(cross["evidence_json"]["count"], 2)
        self.assertIn("2 個網址", cross["description"])
        self.assertEqual(cross["cwe_id"], "CWE-829")
        self.assertEqual(cross["evidence_source"], "OWASP ZAP 2.16.1（被動分析）")
        # 信心低的降一級；沒有中文對照的沿用 ZAP 名稱
        self.assertEqual(by_rule["zap-10040"]["severity"], "low")
        self.assertEqual(by_rule["zap-99999"]["severity"], "high")
        self.assertEqual(by_rule["zap-99999"]["title"], "ZAP：Something New")
        self.assertEqual(by_rule["zap-10027"]["severity"], "info")

    def test_report_source_label(self):
        finding = Finding(rule_id="zap-10017", evidence_source="OWASP ZAP 2.16.1（被動分析）")
        self.assertIn("OWASP ZAP 被動分析", _source_label(finding))


class _FakeClient:
    def __init__(self, *, pending=(0,), alerts=None, fail_import=False):
        self.calls: list[tuple] = []
        self._pending = list(pending)
        self._alerts = alerts if alerts is not None else [_alert("10017")]
        self.fail_import = fail_import

    def version(self):
        return "2.16.1"

    def upload(self, name, contents):
        self.calls.append(("upload", name, contents == "{}"))
        return f"/zap/transfer/{name}"

    def action(self, component, name, **params):
        self.calls.append(("action", component, name))
        if name == "importHar" and self.fail_import:
            raise ZapError("ZAP API exim/importHar 回應 HTTP 400")
        return {"Result": "OK"}

    def pending_records(self):
        return self._pending.pop(0) if self._pending else 0

    def alerts(self, origin):
        return self._alerts

    def clear_origin(self, origin):
        self.calls.append(("clear", origin))


class RunPassiveTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.dir = Path(tempfile.mkdtemp())
        self.har = _write_har(self.dir, "context-1.har", [_entry(f"{ORIGIN}/")])

    def test_success_cleans_up(self):
        client = _FakeClient()
        result = run_passive([self.har], ORIGIN, 7, client=client)
        self.assertEqual(result.entries, 1)
        self.assertEqual(len(result.alerts), 1)
        self.assertTrue(result.queue_drained)
        self.assertIn(("action", "exim", "importHar"), client.calls)
        # 匯入前後都清、上傳的檔案最後覆寫成 {}
        self.assertEqual(client.calls[0], ("clear", ORIGIN))
        self.assertEqual(client.calls[-1], ("upload", "argus-scan-7.har", True))
        self.assertIsNone(cache.get(f"argus-zap:{ORIGIN}"))

    def test_error_still_cleans_up(self):
        client = _FakeClient(fail_import=True)
        with self.assertRaises(ZapError):
            run_passive([self.har], ORIGIN, 7, client=client)
        self.assertIn(("clear", ORIGIN), client.calls[-2:])
        self.assertEqual(client.calls[-1], ("upload", "argus-scan-7.har", True))
        self.assertIsNone(cache.get(f"argus-zap:{ORIGIN}"))

    def test_cancel_propagates_and_cleans_up(self):
        class Cancelled(Exception):
            pass

        def cancel():
            raise Cancelled

        client = _FakeClient(pending=(3,))
        with self.assertRaises(Cancelled):
            run_passive([self.har], ORIGIN, 7, client=client, cancel_check=cancel)
        self.assertEqual(client.calls[-1], ("upload", "argus-scan-7.har", True))

    @override_settings(ARGUS_ZAP_TIMEOUT_SECONDS=0)
    def test_queue_timeout_is_partial(self):
        result = run_passive([self.har], ORIGIN, 7, client=_FakeClient(pending=(5, 5, 5)))
        self.assertFalse(result.queue_drained)

    def test_same_origin_lock(self):
        cache.add(f"argus-zap:{ORIGIN}", 99, timeout=60)
        with self.assertRaises(ZapBusy):
            run_passive([self.har], ORIGIN, 7, client=_FakeClient())

    def test_no_traffic_does_not_call_zap(self):
        client = _FakeClient()
        result = run_passive([], ORIGIN, 7, client=client)
        self.assertEqual(result.entries, 0)
        self.assertEqual(client.calls, [])


class ZapClientErrorTests(SimpleTestCase):
    def test_errors_never_include_key(self):
        client = ZapClient("http://zap.invalid:8090", "super-secret-key", timeout=0.01)
        import httpx
        with mock.patch.object(client.http, "request",
                               side_effect=httpx.ConnectError("refused")):
            with self.assertRaises(ZapError) as raised:
                client.version()
        self.assertNotIn("super-secret-key", str(raised.exception))
        response = httpx.Response(400, json={"code": "missing_parameter"},
                                  request=httpx.Request("GET", "http://zap"))
        with mock.patch.object(client.http, "request", return_value=response):
            with self.assertRaises(ZapError) as raised:
                client.action("exim", "importHar", filePath="x")
        self.assertIn("missing_parameter", str(raised.exception))


class CrawlerHarTests(SimpleTestCase):
    def test_context_records_only_same_origin_when_requested(self):
        context = mock.Mock()
        context.route = mock.AsyncMock()
        context.route_web_socket = mock.AsyncMock()
        browser = mock.Mock()
        browser.new_context = mock.AsyncMock(return_value=context)
        asyncio.run(_make_context(browser, ORIGIN, Path("/tmp/x.har")))
        kwargs = browser.new_context.await_args.kwargs
        self.assertEqual(kwargs["record_har_path"], "/tmp/x.har")
        pattern = kwargs["record_har_url_filter"]
        self.assertTrue(pattern.match(f"{ORIGIN}/a?b=1"))
        self.assertTrue(pattern.match(ORIGIN))
        self.assertFalse(pattern.match(f"{ORIGIN}.evil.test/"))
        self.assertFalse(pattern.match("https://cdn.other.test/x.js"))
        browser.new_context.reset_mock()
        asyncio.run(_make_context(browser, ORIGIN))
        self.assertNotIn("record_har_path", browser.new_context.await_args.kwargs)


@override_settings(ARGUS_ZAP_ENABLED=True, ARGUS_ZAP_API_URL="http://zap:8090",
                   ARGUS_ZAP_API_KEY="k")
class StageTests(TestCase):
    def setUp(self):
        cache.clear()
        user = get_user_model().objects.create_user(username="zap", password="safe-test-password")
        self.scan = ScanJob.objects.create(
            user=user, original_url=f"{ORIGIN}/", normalized_url=f"{ORIGIN}/", origin=ORIGIN,
            categories=["security"],
        )
        self.ctx = tasks.ScanRunContext(
            scan_job=self.scan, execution_plan=build_scan_execution_plan(self.scan), steps=[],
            crawl_phase_started="",
        )
        self.ctx.har_dir = Path(tempfile.mkdtemp())
        _write_har(self.ctx.har_dir, "context-1.har", [_entry(f"{ORIGIN}/")])

    def test_records_findings_and_removes_har(self):
        har_dir = self.ctx.har_dir
        fake = _FakeClient(alerts=[_alert("10017"), _alert("10038", risk="Medium")])
        with mock.patch.object(zap_passive, "ZapClient", return_value=fake):
            tasks.stage_zap_passive(self.ctx)
        self.assertFalse(har_dir.exists())
        self.assertIsNone(self.ctx.har_dir)
        rules = list(Finding.objects.filter(scan_job=self.scan).values_list("rule_id", flat=True))
        self.assertEqual(rules, ["zap-10017"])
        self.assertEqual(self.ctx.coverage.status_of("zap_passive"), COMPLETED)
        self.assertIn("zap_passive", tasks.planned_scan_steps(self.scan, self.ctx.execution_plan))

    def test_zap_down_marks_failed_and_scan_continues(self):
        har_dir = self.ctx.har_dir
        with mock.patch.object(zap_passive, "ZapClient",
                               return_value=_FakeClient(fail_import=True)):
            tasks.stage_zap_passive(self.ctx)
        self.assertFalse(har_dir.exists())
        self.assertEqual(self.ctx.coverage.status_of("zap_passive"), FAILED)
        self.assertFalse(Finding.objects.filter(scan_job=self.scan).exists())

    def test_busy_is_skipped(self):
        cache.add(f"argus-zap:{ORIGIN}", 1, timeout=60)
        tasks.stage_zap_passive(self.ctx)
        self.assertEqual(self.ctx.coverage.status_of("zap_passive"), SKIPPED)

    @override_settings(ARGUS_ZAP_ENABLED=False)
    def test_disabled_is_noop_and_discards_har(self):
        har_dir = self.ctx.har_dir
        tasks.stage_zap_passive(self.ctx)
        self.assertFalse(har_dir.exists())
        self.assertIsNone(self.ctx.coverage.status_of("zap_passive"))
        steps = tasks.planned_scan_steps(self.scan, self.ctx.execution_plan)
        self.assertNotIn("zap_passive", steps)

    def test_security_not_selected_skips(self):
        ScanJob.objects.filter(id=self.scan.id).update(categories=["seo"])
        self.scan.refresh_from_db()
        self.assertFalse(tasks._runs_zap_passive(self.scan))


@unittest.skipUnless(ZAP_URL and ZAP_KEY, "需要 ZAP（ARGUS_TEST_ZAP_URL、ARGUS_TEST_ZAP_KEY）")
class RealZapTests(SimpleTestCase):
    def test_passive_rules_run_on_imported_har_and_cleanup(self):
        cache.clear()
        directory = Path(tempfile.mkdtemp())
        body = ("<html><body><!-- TODO: remove debug account -->"
                "<script src='http://cdn.other.test/x.js'></script></body></html>")
        har = _write_har(directory, "context-1.har", [_entry(f"{ORIGIN}/", body=body)])
        client = ZapClient(ZAP_URL, ZAP_KEY)
        with override_settings(ARGUS_ZAP_TIMEOUT_SECONDS=60):
            result = run_passive([har], ORIGIN, 4242, client=client)
        self.assertTrue(result.queue_drained)
        plugins = {a["pluginId"] for a in result.alerts}
        self.assertTrue({"10017", "10040", "10027"} <= plugins, plugins)
        findings, overlap = alerts_to_findings(result.alerts, result.version)
        by_rule = {f["rule_id"]: f for f in findings}
        # 混合內容在 ZAP 是 Medium／Medium：嚴重度要對應成中風險（不是退回 info）
        self.assertEqual(by_rule["zap-10040"]["severity"], "medium")
        self.assertIn("HSTS（安全標頭）", overlap)
        # ZAP 上不留這個網站的資料
        self.assertEqual(client.alerts(ORIGIN), [])
        messages = client.view("core", "numberOfMessages", baseurl=ORIGIN)
        self.assertEqual(messages["numberOfMessages"], "0")
