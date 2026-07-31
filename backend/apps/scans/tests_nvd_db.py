"""NVD→DB 轉換（nvd_db.build_db_from_nvd）單元測試。

Seam 2：對 build_db_from_nvd 餵凍結的 NVD 2.0 CVE 片段，斷言產出的 DB entry。
不依賴網路或真實 NVD 內容；這也是 refresh 腳本的「已知答案 fixture」，防 CPE 漂移。
"""
from django.test import TestCase

from apps.scans.security.nvd_db import build_db_from_nvd, cvss_severity


def _nginx_cve(
    cve_id="CVE-2017-7529",
    severity="HIGH",
    start_incl="0.5.6",
    end_excl="1.13.2",
    cwe="CWE-190",
    desc="Nginx range filter 可因整數溢位導致敏感資訊外洩。",
):
    return {
        "id": cve_id,
        "descriptions": [{"lang": "en", "value": desc}],
        "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": severity}}]},
        "weaknesses": [{"description": [{"value": cwe}]}],
        "configurations": [{
            "nodes": [{
                "cpeMatch": [{
                    "criteria": f"cpe:2.3:a:nginx:nginx:{end_excl}:*:*:*:*:*:*:*",
                    "versionStartIncluding": start_incl,
                    "versionEndExcluding": end_excl,
                }],
            }],
        }],
    }


class TestVersionRange(TestCase):
    def test_start_including_end_excluding(self):
        db = build_db_from_nvd([_nginx_cve()])
        v = db["nginx"]["vulnerabilities"][0]
        self.assertEqual(v["atOrAbove"], "0.5.6")
        self.assertEqual(v["below"], "1.13.2")

    def test_end_including_becomes_atorbelow(self):
        cve = {
            "id": "CVE-X", "descriptions": [], "weaknesses": [],
            "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH"}}]},
            "configurations": [{"nodes": [{"cpeMatch": [{
                "criteria": "cpe:2.3:a:nginx:nginx:1.10.0:*:*:*:*:*:*:*",
                "versionStartIncluding": "1.0.0",
                "versionEndIncluding": "1.10.0",
            }]}]}],
        }
        v = build_db_from_nvd([cve])["nginx"]["vulnerabilities"][0]
        self.assertEqual(v["atOrBelow"], "1.10.0")
        self.assertNotIn("below", v)

    def test_no_bounds_skipped(self):
        # 無版本區間的 cpeMatch 無法比對，不應進 DB
        cve = {
            "id": "CVE-Y", "descriptions": [], "weaknesses": [],
            "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH"}}]},
            "configurations": [{"nodes": [{"cpeMatch": [{
                "criteria": "cpe:2.3:a:nginx:nginx:1.0.0:*:*:*:*:*:*:*",
            }]}]}],
        }
        self.assertEqual(build_db_from_nvd([cve]), {})


class TestProductFiltering(TestCase):
    def test_nginx_apache_php_all_captured(self):
        cves = [
            _nginx_cve(cve_id="CVE-N1"),
            _apache_cve(),
            _php_cve(),
        ]
        db = build_db_from_nvd(cves)
        self.assertEqual(set(db), {"nginx", "apache", "php"})

    def test_non_target_product_ignored(self):
        cve = {
            "id": "CVE-Z", "descriptions": [], "weaknesses": [],
            "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH"}}]},
            "configurations": [{"nodes": [{"cpeMatch": [{
                "criteria": "cpe:2.3:a:foo:bar:1.0.0:*:*:*:*:*:*:*",
                "versionEndExcluding": "2.0.0",
            }]}]}],
        }
        self.assertEqual(build_db_from_nvd([cve]), {})

    def test_multiple_cves_aggregate_under_product(self):
        db = build_db_from_nvd([_nginx_cve("CVE-A"), _nginx_cve("CVE-B")])
        cves = [v["identifiers"]["CVE"][0] for v in db["nginx"]["vulnerabilities"]]
        self.assertEqual(sorted(cves), ["CVE-A", "CVE-B"])


class TestEntryShape(TestCase):
    def test_severity_cwe_summary_carried(self):
        db = build_db_from_nvd([_nginx_cve(severity="CRITICAL", cwe="CWE-400")])
        v = db["nginx"]["vulnerabilities"][0]
        self.assertEqual(v["severity"], "critical")
        self.assertIn("CWE-400", v["cwe"])
        self.assertIn("CVE-2017-7529", v["identifiers"]["CVE"])
        self.assertTrue(v["identifiers"]["summary"])
        self.assertTrue(v["info"][0].endswith("CVE-2017-7529"))


class TestCvssSeverity(TestCase):
    def test_missing_metrics_defaults_medium(self):
        self.assertEqual(cvss_severity({"metrics": {}}), "medium")

    def test_v31_preferred_over_v2(self):
        cve = {"metrics": {
            "cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH"}}],
            "cvssMetricV2": [{"cvssData": {"baseSeverity": "MEDIUM"}}],
        }}
        self.assertEqual(cvss_severity(cve), "high")


# --- fixtures for apache / php ---
def _apache_cve():
    return {
        "id": "CVE-A1", "descriptions": [{"lang": "en", "value": "Apache httpd flaw."}],
        "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH"}}]},
        "weaknesses": [{"description": [{"value": "CWE-22"}]}],
        "configurations": [{"nodes": [{"cpeMatch": [{
            "criteria": "cpe:2.3:a:apache:http_server:2.4.49:*:*:*:*:*:*:*",
            "versionStartIncluding": "2.4.0",
            "versionEndExcluding": "2.4.51",
        }]}]}],
    }


def _php_cve():
    return {
        "id": "CVE-P1", "descriptions": [{"lang": "en", "value": "PHP flaw."}],
        "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "MEDIUM"}}]},
        "weaknesses": [{"description": [{"value": "CWE-20"}]}],
        "configurations": [{"nodes": [{"cpeMatch": [{
            "criteria": "cpe:2.3:a:php:php:7.4.0:*:*:*:*:*:*:*",
            "versionStartIncluding": "7.4.0",
            "versionEndExcluding": "7.4.30",
        }]}]}],
    }
