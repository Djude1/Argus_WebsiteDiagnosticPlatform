"""已知漏洞優先序補強（security/vuln_intel.py：EPSS＋OSV.dev），不連線外部服務。"""

from __future__ import annotations

import copy
from unittest import mock

import httpx
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.scans.scanners import make_finding
from apps.scans.security import vuln_intel

EPSS_ROWS = {"data": [
    {"cve": "CVE-2020-11022", "epss": "0.40000", "percentile": "0.97350", "date": "2026-10-07"},
    {"cve": "CVE-2020-11023", "epss": "0.10000", "percentile": "0.90000", "date": "2026-10-07"},
]}
OSV_BATCH = {"results": [{"vulns": [{"id": "GHSA-a"}, {"id": "GHSA-b"}]}]}
OSV_VULNS = {
    "GHSA-a": {"id": "GHSA-a", "aliases": ["CVE-2020-11022"], "affected": [{
        "package": {"ecosystem": "npm", "name": "jquery"},
        "ranges": [{"type": "SEMVER", "events": [{"introduced": "1.2.0"}, {"fixed": "3.5.0"}]}],
    }]},
    "GHSA-b": {"id": "GHSA-b", "aliases": ["CVE-2099-0001"], "affected": [{
        "package": {"ecosystem": "npm", "name": "jquery"},
        "ranges": [{"type": "SEMVER", "events": [
            {"introduced": "0"}, {"fixed": "1.9.0"},       # 不涵蓋 3.4.1，不算
            {"introduced": "3.0.0"}, {"fixed": "3.6.1"},   # 涵蓋 3.4.1
        ]}],
    }]},
}


def _js_finding():
    return make_finding(
        category="security", severity="medium", rule_id="js-lib-known-vuln",
        title="過時的第三方庫 jquery 3.4.1", description="偵測到 jquery 3.4.1。",
        remediation="升級", evidence_json={
            "library": "jquery", "version": "3.4.1", "detected_from": "https://site.test/",
            "vulnerabilities": [{"cve": ["CVE-2020-11022"]}, {"cve": ["CVE-2020-11023"]}],
        },
    )


def _service_finding():
    return make_finding(
        category="security", severity="high", rule_id="service-known-cve",
        title="nginx", description="nginx。", remediation="升級", evidence_json={
            "product": "nginx", "version": "1.18.0",
            "vulnerabilities": [{"cve": ["CVE-2021-23017"]}],
        },
    )


def _response(payload, status=200):
    return httpx.Response(status, json=payload, request=httpx.Request("GET", "https://x"))


class _FakeClient:
    def __init__(self, *, fail=False, epss=None):
        self.fail = fail
        self.epss = epss or EPSS_ROWS
        self.requests: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None):
        self.requests.append(("GET", url, params))
        if self.fail:
            raise httpx.ConnectError("down")
        if url == vuln_intel.EPSS_URL:
            return _response(self.epss)
        return _response(OSV_VULNS[url.rsplit("/", 1)[1]])

    def post(self, url, json=None):
        self.requests.append(("POST", url, json))
        if self.fail:
            raise httpx.ConnectError("down")
        return _response(OSV_BATCH)


@override_settings(ARGUS_VULN_INTEL_ENABLED=True)
class EnrichTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _enrich(self, findings, client):
        with mock.patch.object(vuln_intel, "_client", return_value=client):
            return vuln_intel.enrich_findings(findings)

    def test_epss_and_osv_added_without_changing_severity(self):
        finding = _js_finding()
        client = _FakeClient()
        self._enrich([finding], client)
        data = finding["evidence_json"]
        self.assertEqual(finding["severity"], "medium")
        self.assertEqual(data["epss"]["cve"], "CVE-2020-11022")
        self.assertEqual(data["vulnerabilities"][0]["epss"]["epss"], 0.4)
        self.assertEqual(finding["priority_score"], 50 + vuln_intel.EPSS_PRIORITY_BOOST * 0.4)
        self.assertIn("被實際利用的機率約 40.0%，高於 97% 的已知漏洞", finding["description"])
        # 修補版本取涵蓋目前版本的區間中最高的（3.6.1），不是不相干區間的 1.9.0
        self.assertEqual(data["osv"]["fixed"], "3.6.1")
        self.assertEqual(data["osv"]["extra_cves"], ["CVE-2099-0001"])
        self.assertIn("至少升級至 3.6.1", finding["remediation"])
        self.assertEqual(data["vuln_intel"], {"epss": "ok", "osv": "ok"})

    def test_only_library_names_and_cves_leave_the_server(self):
        client = _FakeClient()
        self._enrich([_js_finding(), _service_finding()], client)
        sent = repr(client.requests)
        self.assertNotIn("site.test", sent)
        self.assertIn("CVE-2021-23017", sent)
        # 後端服務沒有 npm 套件，不查 OSV
        osv_queries = [r[2] for r in client.requests if r[0] == "POST"][0]["queries"]
        self.assertEqual(osv_queries, [{"package": {"ecosystem": "npm", "name": "jquery"},
                                        "version": "3.4.1"}])

    def test_priority_never_crosses_severity_tier(self):
        finding = _service_finding()  # high＝75
        client = _FakeClient(epss={"data": [{"cve": "CVE-2021-23017", "epss": "1.0",
                                             "percentile": "1.0", "date": "2026-10-07"}]})
        self._enrich([finding], client)
        self.assertLess(finding["priority_score"], 90)  # critical 的預設

    def test_unavailable_keeps_finding_and_records_reason(self):
        finding = _js_finding()
        original = copy.deepcopy(finding)
        self._enrich([finding], _FakeClient(fail=True))
        self.assertEqual(finding["description"], original["description"])
        self.assertEqual(finding["priority_score"], original["priority_score"])
        status = finding["evidence_json"]["vuln_intel"]
        self.assertIn("EPSS 無法查詢", status["epss"])
        self.assertIn("OSV.dev 無法查詢", status["osv"])

    def test_results_are_cached(self):
        client = _FakeClient()
        self._enrich([_js_finding()], client)
        second = _FakeClient()
        self._enrich([_js_finding()], second)
        self.assertEqual(second.requests, [])

    def test_other_findings_untouched_and_disabled_noop(self):
        other = make_finding(category="security", severity="low", title="x", description="d",
                             remediation="r", rule_id="cookie-no-secure")
        client = _FakeClient()
        self._enrich([other], client)
        self.assertEqual(client.requests, [])
        with override_settings(ARGUS_VULN_INTEL_ENABLED=False):
            finding = _js_finding()
            self._enrich([finding], client)
        self.assertNotIn("vuln_intel", finding["evidence_json"])
        self.assertEqual(client.requests, [])

    def test_retire_names_map_to_npm(self):
        finding = _js_finding()
        finding["evidence_json"]["library"] = "moment.js"
        self.assertEqual(vuln_intel._npm_package(finding), ("moment", "3.4.1"))
