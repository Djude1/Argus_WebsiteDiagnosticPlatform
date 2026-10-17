"""OWASP ZAP 主動掃描（security/zap_active.py、scan_plan.run_zap_active、tasks 閘門）。

不需要 ZAP：以假的 ZapClient 驗證流程、授權閘門與清理。主動掃描會送攻擊 payload，
所以只在「全站＋主動＋已授權」且 ARGUS_ZAP_ACTIVE_ENABLED 時跑。
端點與告警皆為虛構測試值。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from apps.scans import tasks
from apps.scans.models import ScanJob
from apps.scans.scan_plan import build_scan_execution_plan
from apps.scans.security import zap_active
from apps.scans.security.zap_active import run_active

ORIGIN = "https://site.example.test"
User = get_user_model()


def _alert(plugin, *, risk="High", confidence="High", url=f"{ORIGIN}/x", name="SQLi"):
    return {"id": str(abs(hash((plugin, url))) % 10000), "pluginId": plugin,
            "risk": risk, "confidence": confidence, "alert": name, "url": url,
            "description": "desc", "solution": "fix", "evidence": "' OR 1=1", "param": "id",
            "cweid": "89", "reference": "https://ref"}


def _write_har(directory: Path) -> Path:
    entry = {"request": {"method": "GET", "url": f"{ORIGIN}/x", "headers": [], "cookies": []},
             "response": {"status": 200, "headers": [{"name": "Content-Type",
                          "value": "text/html"}], "cookies": [],
                          "content": {"mimeType": "text/html", "text": "<html></html>"}}}
    path = directory / "context-1.har"
    path.write_text(json.dumps({"log": {"version": "1.2", "entries": [entry]}}), encoding="utf-8")
    return path


class _FakeActiveClient:
    """記錄呼叫順序；spider/ascan 各一步就跑完（status 100）。"""

    def __init__(self, *, ascan_id="7", alerts=None, ascan_raises=False):
        self.calls: list[tuple] = []
        self._ascan_id = ascan_id
        self._alerts = alerts if alerts is not None else [_alert("40018")]
        self._ascan_raises = ascan_raises

    def version(self):
        return "2.16.1"

    def clear_origin(self, origin):
        self.calls.append(("clear", origin))

    def alerts(self, origin):
        return self._alerts

    def upload(self, name, contents):
        self.calls.append(("upload", name, contents == "{}"))
        return f"/zap/transfer/{name}"

    def action(self, component, name, **params):
        self.calls.append(("action", component, name))
        return {"Result": "OK"}

    def spider_scan(self, url):
        self.calls.append(("spider_scan", url))
        return "1"

    def spider_status(self, scan_id):
        return 100

    def spider_stop(self, scan_id):
        self.calls.append(("spider_stop", scan_id))

    def ascan_scan(self, url, *, policy=""):
        self.calls.append(("ascan_scan", url))
        if self._ascan_raises:
            from apps.scans.security.zap_passive import ZapError
            raise ZapError("does_not_exist")
        return self._ascan_id

    def ascan_status(self, scan_id):
        return 100

    def ascan_stop(self, scan_id):
        self.calls.append(("ascan_stop", scan_id))


@override_settings(
    ARGUS_ZAP_ACTIVE_TIMEOUT_SECONDS=30, ARGUS_ZAP_ACTIVE_SPIDER_SECONDS=10,
    ARGUS_ZAP_MAX_ENTRIES=100, ARGUS_ZAP_MAX_BODY_CHARS=1000,
)
class RunActiveTests(SimpleTestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        cache.delete(f"argus-zap:{ORIGIN.lower()}")

    def test_seeds_tree_from_har_then_active_scans_and_cleans_up(self):
        client = _FakeActiveClient(alerts=[_alert("40018")])
        result = run_active([_write_har(self.dir)], ORIGIN, 1, client=client)
        self.assertTrue(result.scanned)
        self.assertEqual(len(result.alerts), 1)
        names = [c[0] for c in client.calls]
        # 先 importHar 建樹、再 spider、再 ascan
        self.assertIn(("action", "exim", "importHar"), client.calls)
        self.assertLess(names.index("ascan_scan"), len(names))
        # 清理：清 origin ＋ 上傳的 HAR 被覆寫成 {}
        self.assertTrue(any(c == ("upload", "argus-active-1.har", True) for c in client.calls))
        self.assertIn(("clear", ORIGIN), client.calls)

    def test_no_scannable_node_marks_not_scanned(self):
        client = _FakeActiveClient(ascan_raises=True)
        result = run_active([_write_har(self.dir)], ORIGIN, 2, client=client)
        self.assertFalse(result.scanned)
        self.assertTrue(result.reason)

    def test_busy_lock_raises(self):
        from apps.scans.security.zap_passive import ZapBusy

        cache.add(f"argus-zap:{ORIGIN.lower()}", 999, timeout=60)
        try:
            with self.assertRaises(ZapBusy):
                run_active([_write_har(self.dir)], ORIGIN, 3, client=_FakeActiveClient())
        finally:
            cache.delete(f"argus-zap:{ORIGIN.lower()}")


class ActiveGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="zap-active", password="safe-test-password")

    def _scan(self, *, mode, authorized, pages):
        return ScanJob.objects.create(
            user=self.user, original_url=f"{ORIGIN}/", normalized_url=f"{ORIGIN}/",
            origin=ORIGIN, status=ScanJob.Status.COMPLETED, categories=["security"],
            scan_mode=mode, active_testing_authorized=authorized, max_pages=pages,
        )

    def test_plan_flag_only_on_site_active(self):
        site_active = self._scan(mode=ScanJob.ScanMode.ACTIVE, authorized=True, pages=50)
        passive = self._scan(mode=ScanJob.ScanMode.PASSIVE, authorized=False, pages=50)
        single = self._scan(mode=ScanJob.ScanMode.ACTIVE, authorized=True, pages=1)
        self.assertTrue(build_scan_execution_plan(site_active).run_zap_active)
        self.assertFalse(build_scan_execution_plan(passive).run_zap_active)
        self.assertFalse(build_scan_execution_plan(single).run_zap_active)

    @override_settings(ARGUS_ZAP_ACTIVE_ENABLED=True, ARGUS_ZAP_ENABLED=True,
                       ARGUS_ZAP_API_URL="http://zap", ARGUS_ZAP_API_KEY="k")
    def test_runs_zap_active_requires_enable_and_gate(self):
        site_active = self._scan(mode=ScanJob.ScanMode.ACTIVE, authorized=True, pages=50)
        passive = self._scan(mode=ScanJob.ScanMode.PASSIVE, authorized=False, pages=50)
        self.assertTrue(tasks._runs_zap_active(site_active))
        self.assertFalse(tasks._runs_zap_active(passive))

    @override_settings(ARGUS_ZAP_ACTIVE_ENABLED=False, ARGUS_ZAP_ENABLED=True,
                       ARGUS_ZAP_API_URL="http://zap", ARGUS_ZAP_API_KEY="k")
    def test_disabled_flag_blocks_even_when_authorized(self):
        site_active = self._scan(mode=ScanJob.ScanMode.ACTIVE, authorized=True, pages=50)
        self.assertFalse(tasks._runs_zap_active(site_active))
        self.assertFalse(zap_active.active_enabled())


class ActiveFindingSourceTests(SimpleTestCase):
    def test_alerts_to_findings_marks_active_source(self):
        from apps.scans.security.zap_passive import alerts_to_findings

        findings, _overlap = alerts_to_findings([_alert("40018")], "2.16.1", active=True)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["evidence_json"]["source"], "zap_active")
        self.assertIn("主動掃描", findings[0]["evidence_source"])
        self.assertEqual(findings[0]["rule_id"], "zap-40018")
