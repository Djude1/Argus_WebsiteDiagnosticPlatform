"""security/ 被動安全 scanner 套件的單元測試。"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scans.models import Finding, ScanJob
from apps.scans.security import (
    cookie_scanner,
    dns_scanner,
    header_scanner,
    owasp_mapper,
    sri_scanner,
    ssl_scanner,
)
from apps.scans.serializers import FindingSerializer


def _make_scan():
    """建立測試用 ScanJob（含必填 user / normalized_url / origin）。"""
    user = get_user_model().objects.create_user(
        username=f"user_{uuid.uuid4().hex[:8]}",
        password="testpass123",
    )
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
    )


class TestFindingOwaspFields(TestCase):
    def test_finding_has_owasp_and_cwe_fields(self):
        scan = _make_scan()
        finding = Finding.objects.create(
            scan_job=scan,
            category="security",
            severity="medium",
            title="t",
            description="d",
            remediation="r",
            ai_handoff_prompt="p",
            owasp_category="A05",
            cwe_id="CWE-200",
        )
        finding.refresh_from_db()
        self.assertEqual(finding.owasp_category, "A05")
        self.assertEqual(finding.cwe_id, "CWE-200")


class TestSslScanner(TestCase):
    def test_cert_expiry_high_when_within_30_days(self):
        import ssl as _ssl
        import time
        not_after = _ssl.cert_time_to_seconds  # noqa: F841 — 確認 API 存在
        future = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() + 20 * 86400))
        findings = ssl_scanner._eval_cert_expiry(future)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["rule_id"], "ssl-cert-expiring")

    def test_cert_expiry_critical_when_expired(self):
        import time
        past = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() - 86400))
        findings = ssl_scanner._eval_cert_expiry(past)
        self.assertEqual(findings[0]["severity"], "critical")
        self.assertEqual(findings[0]["rule_id"], "ssl-cert-expired")

    def test_cert_expiry_none_when_far(self):
        import time
        far = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() + 365 * 86400))
        self.assertEqual(ssl_scanner._eval_cert_expiry(far), [])

    def test_protocol_old_tls_is_high(self):
        findings = ssl_scanner._eval_protocol("TLSv1")
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["rule_id"], "ssl-weak-protocol")

    def test_protocol_modern_tls_empty(self):
        self.assertEqual(ssl_scanner._eval_protocol("TLSv1.3"), [])

    def test_cipher_weak_is_high(self):
        findings = ssl_scanner._eval_cipher("ECDHE-RSA-RC4-SHA")
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["rule_id"], "ssl-weak-cipher")

    def test_cipher_strong_empty(self):
        self.assertEqual(ssl_scanner._eval_cipher("ECDHE-RSA-AES128-GCM-SHA256"), [])

    def test_analyze_ssl_empty_host_returns_empty(self):
        self.assertEqual(ssl_scanner.analyze_ssl(""), [])

    def test_analyze_ssl_connection_error_returns_empty(self):
        self.assertEqual(ssl_scanner.analyze_ssl("invalid.invalid", port=443), [])

    def test_verify_error_expired_is_critical(self):
        findings = ssl_scanner._eval_cert_verify_error("certificate has expired")
        self.assertEqual(findings[0]["severity"], "critical")
        self.assertEqual(findings[0]["rule_id"], "ssl-cert-expired")

    def test_verify_error_self_signed_is_medium(self):
        findings = ssl_scanner._eval_cert_verify_error("self signed certificate")
        self.assertEqual(findings[0]["severity"], "medium")
        self.assertEqual(findings[0]["rule_id"], "ssl-self-signed")

    def test_verify_error_unknown_returns_empty(self):
        self.assertEqual(ssl_scanner._eval_cert_verify_error("some other error"), [])


class TestCookieScanner(TestCase):
    def test_missing_secure_on_https_is_medium(self):
        headers = {"set-cookie": "sid=abc; Path=/; HttpOnly"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        rules = {f["rule_id"]: f for f in findings}
        self.assertIn("cookie-no-secure", rules)
        self.assertEqual(rules["cookie-no-secure"]["severity"], "medium")

    def test_missing_httponly_is_low(self):
        headers = {"set-cookie": "sid=abc; Path=/; Secure"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["cookie-no-httponly"]["severity"], "low")

    def test_samesite_none_without_secure_is_medium(self):
        headers = {"set-cookie": "sid=abc; SameSite=None"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        rules = {f["rule_id"] for f in findings}
        self.assertIn("cookie-samesite-none", rules)

    def test_secure_httponly_strict_no_findings(self):
        headers = {"set-cookie": "sid=abc; Secure; HttpOnly; SameSite=Strict"}
        self.assertEqual(cookie_scanner.analyze_cookies(headers, "https://example.com"), [])

    def test_no_set_cookie_returns_empty(self):
        self.assertEqual(cookie_scanner.analyze_cookies({}, "https://example.com"), [])

    def test_multiple_cookies_split_by_newline(self):
        headers = {"set-cookie": "a=1; HttpOnly\nb=2; Secure"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        self.assertGreaterEqual(len(findings), 2)

    def test_bad_input_returns_empty(self):
        self.assertEqual(cookie_scanner.analyze_cookies(None, "https://example.com"), [])


class TestHeaderScanner(TestCase):
    def _page(self, headers):
        return [{"headers": headers, "final_url": "https://example.com", "url": "https://example.com"}]

    def test_server_version_leak_is_low(self):
        findings = header_scanner.analyze_headers(self._page({"server": "Apache/2.4.49"}))
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["header-server-version"]["severity"], "low")

    def test_x_powered_by_is_low(self):
        findings = header_scanner.analyze_headers(self._page({"x-powered-by": "PHP/7.4.3"}))
        self.assertIn("header-x-powered-by", {f["rule_id"] for f in findings})

    def test_cors_wildcard_is_medium(self):
        findings = header_scanner.analyze_headers(self._page({"access-control-allow-origin": "*"}))
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["header-cors-wildcard"]["severity"], "medium")

    def test_cors_wildcard_with_credentials_is_high(self):
        findings = header_scanner.analyze_headers(self._page({
            "access-control-allow-origin": "*",
            "access-control-allow-credentials": "true",
        }))
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["header-cors-credentials"]["severity"], "high")

    def test_csp_unsafe_inline_is_medium(self):
        findings = header_scanner.analyze_headers(self._page({
            "content-security-policy": "default-src 'self'; script-src 'unsafe-inline'",
        }))
        self.assertIn("header-csp-unsafe", {f["rule_id"] for f in findings})

    def test_clean_headers_no_findings(self):
        findings = header_scanner.analyze_headers(self._page({"server": "cloudflare"}))
        self.assertEqual(findings, [])

    def test_no_pages_returns_empty(self):
        self.assertEqual(header_scanner.analyze_headers([]), [])

    def test_bad_input_returns_empty(self):
        self.assertEqual(header_scanner.analyze_headers(None), [])


class TestOwaspMapper(TestCase):
    def test_tag_security_finding_fills_fields(self):
        finding = {"category": "security", "rule_id": "ssl-weak-cipher"}
        tagged = owasp_mapper.tag(finding)
        self.assertEqual(tagged["owasp_category"], "A02")
        self.assertEqual(tagged["cwe_id"], "CWE-327")

    def test_tag_unknown_rule_empty_strings(self):
        finding = {"category": "security", "rule_id": "totally-unknown"}
        tagged = owasp_mapper.tag(finding)
        self.assertEqual(tagged["owasp_category"], "")
        self.assertEqual(tagged["cwe_id"], "")

    def test_tag_non_security_untouched(self):
        finding = {"category": "seo", "rule_id": "x"}
        tagged = owasp_mapper.tag(finding)
        self.assertNotIn("owasp_category", tagged)

    def test_backfill_updates_existing_security_findings(self):
        scan = _make_scan()
        f = Finding.objects.create(
            scan_job=scan, category="security", severity="medium",
            rule_id="cookie-no-secure", title="t", description="d",
            remediation="r", ai_handoff_prompt="p",
        )
        owasp_mapper.backfill(scan)
        f.refresh_from_db()
        self.assertEqual(f.owasp_category, "A05")
        self.assertEqual(f.cwe_id, "CWE-614")

    def test_backfill_skips_non_security(self):
        scan = _make_scan()
        f = Finding.objects.create(
            scan_job=scan, category="seo", severity="low",
            rule_id="cookie-no-secure", title="t", description="d",
            remediation="r", ai_handoff_prompt="p",
        )
        owasp_mapper.backfill(scan)
        f.refresh_from_db()
        self.assertEqual(f.owasp_category, "")


class TestFindingSerializerOwasp(TestCase):
    def test_serializer_includes_owasp_cwe(self):
        scan = _make_scan()
        f = Finding.objects.create(
            scan_job=scan, category="security", severity="medium",
            rule_id="cookie-no-secure", title="t", description="d",
            remediation="r", ai_handoff_prompt="p",
            owasp_category="A05", cwe_id="CWE-614",
        )
        data = FindingSerializer(f).data
        self.assertEqual(data["owasp_category"], "A05")
        self.assertEqual(data["cwe_id"], "CWE-614")


class TestOwaspMapperExistingFindings(TestCase):
    """既有 analyze_security 的 SECURITY_<token>_<hash> rule_id 也要被涵蓋。"""

    def test_keyword_lookup_covers_passive_security_rule_ids(self):
        cases = {
            "SECURITY_HSTS_6A08D9EE20": ("A05", "CWE-319"),
            "SECURITY_CSP_BD010B5BE0": ("A05", "CWE-693"),
            "SECURITY_X_FRAME_OPTIONS_A7A326FEA9": ("A05", "CWE-1021"),
            "SECURITY_X_CONTENT_TYPE_OPTIONS_89053405E6": ("A05", "CWE-693"),
            "SECURITY_HTTPS_1234567890": ("A02", "CWE-319"),
            "SECURITY_PII_8B24BB8B28": ("A02", "CWE-359"),
            "SECURITY_CSRF_TOKEN_DEADBEEF12": ("A01", "CWE-352"),
        }
        for rule_id, expected in cases.items():
            self.assertEqual(owasp_mapper._lookup(rule_id), expected, rule_id)

    def test_exact_match_takes_priority_over_keyword(self):
        # 新 scanner 的乾淨 rule_id 走精確比對
        self.assertEqual(owasp_mapper._lookup("header-csp-unsafe"), ("A05", "CWE-1021"))

    def test_backfill_tags_existing_passive_security_finding(self):
        scan = _make_scan()
        f = Finding.objects.create(
            scan_job=scan, category="security", severity="medium",
            rule_id="SECURITY_HSTS_6A08D9EE20", title="缺少 HSTS",
            description="d", remediation="r", ai_handoff_prompt="p",
        )
        owasp_mapper.backfill(scan)
        f.refresh_from_db()
        self.assertEqual(f.owasp_category, "A05")
        self.assertEqual(f.cwe_id, "CWE-319")

    def test_unmappable_rule_id_stays_empty(self):
        self.assertEqual(owasp_mapper._lookup("SECURITY_SOMETHING_NEW_AABBCC1122"), ("", ""))


class TestSriScanner(TestCase):
    def _page(self, html):
        return {"html": html, "final_url": "https://example.com/"}

    def test_cross_origin_script_without_integrity_flagged(self):
        html = '<script src="https://cdn.other.com/a.js"></script>'
        findings = sri_scanner.analyze_sri([self._page(html)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "sri-missing-integrity")
        self.assertEqual(findings[0]["severity"], "low")

    def test_cross_origin_link_stylesheet_without_integrity_flagged(self):
        html = '<link rel="stylesheet" href="https://cdn.other.com/a.css">'
        findings = sri_scanner.analyze_sri([self._page(html)])
        self.assertEqual(len(findings), 1)

    def test_script_with_integrity_not_flagged(self):
        html = '<script src="https://cdn.other.com/a.js" integrity="sha384-x"></script>'
        self.assertEqual(sri_scanner.analyze_sri([self._page(html)]), [])

    def test_same_origin_script_not_flagged(self):
        html = '<script src="https://example.com/a.js"></script>'
        self.assertEqual(sri_scanner.analyze_sri([self._page(html)]), [])

    def test_relative_path_not_flagged(self):
        html = '<script src="/static/a.js"></script>'
        self.assertEqual(sri_scanner.analyze_sri([self._page(html)]), [])

    def test_same_external_url_deduped_across_pages(self):
        html = '<script src="https://cdn.other.com/a.js"></script>'
        findings = sri_scanner.analyze_sri([self._page(html), self._page(html)])
        self.assertEqual(len(findings), 1)

    def test_empty_html_returns_empty(self):
        page = {"html": "", "final_url": "https://example.com/"}
        self.assertEqual(sri_scanner.analyze_sri([page]), [])

    def test_no_pages_returns_empty(self):
        self.assertEqual(sri_scanner.analyze_sri([]), [])


class TestDnsEval(TestCase):
    # --- SPF ---
    def test_spf_missing_medium(self):
        findings = dns_scanner._eval_spf(None, "example.com")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "dns-spf-missing")
        self.assertEqual(findings[0]["severity"], "medium")

    def test_spf_permissive_all_high(self):
        findings = dns_scanner._eval_spf("v=spf1 +all", "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-spf-permissive")
        self.assertEqual(findings[0]["severity"], "high")

    def test_spf_strict_no_finding(self):
        result = dns_scanner._eval_spf("v=spf1 include:_spf.google.com -all", "example.com")
        self.assertEqual(result, [])

    # --- DMARC ---
    def test_dmarc_missing_low(self):
        findings = dns_scanner._eval_dmarc(None, "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-dmarc-missing")
        self.assertEqual(findings[0]["severity"], "low")

    def test_dmarc_policy_none_low(self):
        findings = dns_scanner._eval_dmarc("v=DMARC1; p=none", "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-dmarc-policy-weak")
        self.assertEqual(findings[0]["severity"], "low")

    def test_dmarc_policy_reject_no_finding(self):
        self.assertEqual(dns_scanner._eval_dmarc("v=DMARC1; p=reject", "example.com"), [])

    def test_dmarc_policy_parser(self):
        self.assertEqual(dns_scanner._dmarc_policy("v=DMARC1; p=quarantine; pct=100"), "quarantine")

    # --- DNSSEC ---
    def test_dnssec_missing_low(self):
        findings = dns_scanner._eval_dnssec(False, "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-dnssec-missing")
        self.assertEqual(findings[0]["severity"], "low")

    def test_dnssec_present_no_finding(self):
        self.assertEqual(dns_scanner._eval_dnssec(True, "example.com"), [])

    def test_dnssec_unknown_no_finding(self):
        self.assertEqual(dns_scanner._eval_dnssec(None, "example.com"), [])

    # --- org domain 退一層 ---
    def test_org_domain_strips_subdomain(self):
        self.assertEqual(dns_scanner._org_domain("www.example.com"), "example.com")

    def test_org_domain_keeps_two_label(self):
        self.assertEqual(dns_scanner._org_domain("example.com"), "example.com")


class TestAnalyzeDnsWiring(TestCase):
    def test_all_missing_produces_three_findings(self):
        orig_txt, orig_key = dns_scanner._query_txt, dns_scanner._has_dnskey
        dns_scanner._query_txt = lambda name: []
        dns_scanner._has_dnskey = lambda name: False
        try:
            findings = dns_scanner.analyze_dns("example.com")
        finally:
            dns_scanner._query_txt, dns_scanner._has_dnskey = orig_txt, orig_key
        rule_ids = {f["rule_id"] for f in findings}
        self.assertEqual(rule_ids, {"dns-spf-missing", "dns-dmarc-missing", "dns-dnssec-missing"})

    def test_empty_host_returns_empty(self):
        self.assertEqual(dns_scanner.analyze_dns(""), [])


class TestOwaspMappingNew(TestCase):
    def test_new_rule_ids_mapped(self):
        cases = {
            "sri-missing-integrity": ("A08", "CWE-353"),
            "dns-spf-missing": ("A07", "CWE-290"),
            "dns-spf-permissive": ("A07", "CWE-290"),
            "dns-dmarc-missing": ("A07", "CWE-290"),
            "dns-dmarc-policy-weak": ("A07", "CWE-290"),
            "dns-dnssec-missing": ("A05", "CWE-345"),
        }
        for rule_id, (owasp, cwe) in cases.items():
            tagged = owasp_mapper.tag({"category": "security", "rule_id": rule_id})
            self.assertEqual(tagged["owasp_category"], owasp, rule_id)
            self.assertEqual(tagged["cwe_id"], cwe, rule_id)
