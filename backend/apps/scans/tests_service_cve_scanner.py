"""後端服務指紋→CVE scanner（service_cve_scanner）單元測試。

Seam 1：公開函式 analyze_services(pages)。注入假 DB（覆寫 _load_db）與 NVD 真實內容
脫鉤，避免 flaky；模式同 tests_js_library_scanner.py 的 TestAnalyzeJsLibraries。
"""
import pathlib

from django.test import TestCase

from apps.scans.security import owasp_mapper
from apps.scans.security import service_cve_scanner as scs


class TestParseServerHeader(TestCase):
    def test_product_slash_version(self):
        self.assertEqual(scs._parse_server("nginx/1.12.0"), ("nginx", "1.12.0"))

    def test_strips_os_suffix(self):
        # Apache/2.4.49 (Ubuntu) → product apache, version 2.4.49（停在空白）
        self.assertEqual(scs._parse_server("Apache/2.4.49 (Ubuntu)"), ("apache", "2.4.49"))

    def test_case_insensitive_product(self):
        self.assertEqual(scs._parse_server("NGINX/1.12.0"), ("nginx", "1.12.0"))

    def test_no_version_returns_none(self):
        self.assertIsNone(scs._parse_server("cloudflare"))
        self.assertIsNone(scs._parse_server("nginx"))

    def test_empty_returns_none(self):
        self.assertIsNone(scs._parse_server(""))


class TestAnalyzeServices(TestCase):
    _FAKE_DB = {
        "nginx": {
            "vulnerabilities": [
                {"below": "1.13.2", "severity": "high",
                 "identifiers": {"CVE": ["CVE-2017-7529"], "summary": "range overflow"},
                 "cwe": ["CWE-190"], "info": ["https://example/x1"]},
                {"atOrAbove": "1.15.6", "below": "1.15.8", "severity": "critical",
                 "identifiers": {"CVE": ["CVE-2018-16843"], "summary": "http/2 mem"},
                 "cwe": ["CWE-400"], "info": []},
            ],
        },
        "php": {
            "vulnerabilities": [
                {"atOrAbove": "7.4.0", "below": "7.4.30", "severity": "high",
                 "identifiers": {"CVE": ["CVE-2021-21708"], "summary": "php flaw"},
                 "cwe": ["CWE-20"], "info": []},
            ],
        },
    }

    def setUp(self):
        self._orig = scs._load_db
        scs._load_db = lambda: self._FAKE_DB  # type: ignore[assignment]

    def tearDown(self):
        scs._load_db = self._orig  # type: ignore[assignment]

    def _pages(self, server, url="https://example.com/"):
        return [{"headers": {"server": server}, "final_url": url}]

    def test_vulnerable_version_flagged_with_cve(self):
        findings = scs.analyze_services(self._pages("nginx/1.12.0"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "service-known-cve")
        vulns = findings[0]["evidence_json"]["vulnerabilities"]
        self.assertEqual(vulns[0]["cve"], ["CVE-2017-7529"])

    def test_critical_capped_to_high(self):
        # 1.15.7 落入 critical 區間 → severity 封頂 high（被動偵測未實機確認可利用）
        findings = scs.analyze_services(self._pages("nginx/1.15.7"))
        self.assertEqual(findings[0]["rule_id"], "service-known-cve")
        self.assertEqual(findings[0]["severity"], "high")

    def test_patched_version_in_db_falls_back_to_exposure(self):
        findings = scs.analyze_services(self._pages("nginx/1.20.0"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "service-version-exposed")
        self.assertEqual(findings[0]["severity"], "low")

    def test_product_not_in_db_reports_exposure(self):
        # Apache 不在 fake DB → 仍回報版本暴露（接手 header-server-version）
        findings = scs.analyze_services(self._pages("Apache/2.4.49"))
        self.assertEqual(findings[0]["rule_id"], "service-version-exposed")
        self.assertEqual(findings[0]["severity"], "low")

    def test_version_less_header_no_finding(self):
        self.assertEqual(scs.analyze_services(self._pages("nginx")), [])
        self.assertEqual(scs.analyze_services(self._pages("cloudflare")), [])

    def test_dedup_across_pages(self):
        pages = (
            self._pages("nginx/1.12.0", "https://example.com/a")
            + self._pages("nginx/1.12.0", "https://example.com/b")
        )
        findings = scs.analyze_services(pages)
        self.assertEqual(len(findings), 1)

    def test_no_pages_returns_empty(self):
        self.assertEqual(scs.analyze_services([]), [])

    def test_bad_input_returns_empty(self):
        self.assertEqual(scs.analyze_services(None), [])  # type: ignore[arg-type]

    def test_php_from_x_powered_by_reports_cve(self):
        pages = [{"headers": {"x-powered-by": "PHP/7.4.5"}, "final_url": "https://example.com/"}]
        findings = scs.analyze_services(pages)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "service-known-cve")
        self.assertEqual(findings[0]["evidence_json"]["product"], "php")
        self.assertEqual(findings[0]["evidence_json"]["via"], "X-Powered-By")

    def test_x_powered_by_without_version_no_finding(self):
        # 無版本的 X-Powered-By（如 Express）不開 finding；技術棧洩露由 header_scanner 報
        pages = [{"headers": {"x-powered-by": "Express"}, "final_url": "https://example.com/"}]
        self.assertEqual(scs.analyze_services(pages), [])

    def test_server_and_x_powered_by_yield_distinct_findings(self):
        pages = [{"headers": {"server": "nginx/1.12.0", "x-powered-by": "PHP/7.4.5"},
                  "final_url": "https://example.com/"}]
        products = {f["evidence_json"]["product"] for f in scs.analyze_services(pages)}
        self.assertEqual(products, {"nginx", "php"})

    def test_missing_db_still_reports_exposure(self):
        # DB 缺失時 CVE 比對無作用，但版本暴露仍應回報（不回歸 header-server-version）
        scs._load_db = lambda: {}
        findings = scs.analyze_services(self._pages("nginx/1.12.0"))
        self.assertEqual(findings[0]["rule_id"], "service-version-exposed")


class TestLoadDb(TestCase):
    def test_missing_db_file_returns_empty(self):
        orig = scs._DB_PATH
        scs._load_db.cache_clear()
        scs._DB_PATH = pathlib.Path("/nonexistent/backend_services.json")
        try:
            self.assertEqual(scs._load_db(), {})
        finally:
            scs._DB_PATH = orig
            scs._load_db.cache_clear()


class TestRealSeedDb(TestCase):
    """確認 shipped 種子 DB（data/backend_services.json）格式有效、含 nginx。"""

    def setUp(self):
        scs._load_db.cache_clear()

    def test_seed_db_valid_and_has_nginx(self):
        db = scs._load_db()
        self.assertIn("nginx", db)
        self.assertIsInstance(db["nginx"]["vulnerabilities"], list)
        self.assertGreater(len(db["nginx"]["vulnerabilities"]), 0)

    def test_seed_nginx_cves_carry_identifiers(self):
        db = scs._load_db()
        for vuln in db["nginx"]["vulnerabilities"]:
            self.assertIn("identifiers", vuln)
            self.assertIn(("CVE"), vuln["identifiers"])


class TestServiceCveOwaspMapping(TestCase):
    def test_known_cve_maps_to_a06_cwe1104(self):
        tagged = owasp_mapper.tag({"category": "security", "rule_id": "service-known-cve"})
        self.assertEqual(tagged["owasp_category"], "A06")
        self.assertEqual(tagged["cwe_id"], "CWE-1104")

    def test_version_exposed_maps_to_a05_cwe200(self):
        tagged = owasp_mapper.tag({"category": "security", "rule_id": "service-version-exposed"})
        self.assertEqual(tagged["owasp_category"], "A05")
        self.assertEqual(tagged["cwe_id"], "CWE-200")
