"""網站概況：CDN／反向代理辨識與「做得好的地方」（2026-10-06 ntubimdbirc.tw／ils.org.tw 實測）。"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from docx import Document
from jsonschema import Draft7Validator

from apps.scans import report_render
from apps.scans.models import ScanJob
from apps.scans.reports import build_report_payload, render_report_docx
from apps.scans.security import infra_scanner
from apps.scans.site_profile import build_site_profile, collect_strengths

CF_HEADERS = {
    "server": "cloudflare",
    "cf-ray": "a461daa0facd3913-IAD",
    "strict-transport-security": "max-age=15552000; includeSubDomains; preload",
    "x-content-type-options": "nosniff",
}


class InfrastructureTests(SimpleTestCase):
    def _analyze(self, hostname, headers, answers):
        with (
            mock.patch.object(
                infra_scanner, "_query", side_effect=lambda n, t: answers.get((n, t), [])
            ),
            mock.patch.object(
                infra_scanner, "_reverse", side_effect=lambda ip: answers.get(("ptr", ip), "")
            ),
        ):
            return infra_scanner.analyze_infrastructure(hostname, headers)

    def test_cloudflare_edge_is_detected_with_notice(self):
        profile = self._analyze(
            "ntubimdbirc.tw",
            CF_HEADERS,
            {
                ("ntubimdbirc.tw", "A"): ["104.21.4.142", "172.67.154.32"],
                ("ntubimdbirc.tw", "AAAA"): ["2606:4700:3034::6815:48e"],
                ("ntubimdbirc.tw", "NS"): ["rob.ns.cloudflare.com", "teagan.ns.cloudflare.com"],
            },
        )
        self.assertEqual(profile["scan_target"], "edge")
        self.assertEqual(profile["edge"]["provider"], "Cloudflare")
        self.assertTrue(profile["edge"]["waf_capable"])
        self.assertEqual([a["network"] for a in profile["addresses"]], ["Cloudflare"] * 3)
        self.assertIn(
            "目前掃描目標位於 Cloudflare Edge，而非直接掃描 Origin Server", profile["notice"]
        )

    def test_direct_host_keeps_rdns_and_is_origin(self):
        profile = self._analyze(
            "www.ils.org.tw",
            {"server": "Apache"},
            {
                ("www.ils.org.tw", "A"): ["211.75.1.204"],
                ("ptr", "211.75.1.204"): "211-75-1-204.hinet-ip.hinet.net",
            },
        )
        self.assertEqual(profile["scan_target"], "origin")
        self.assertIsNone(profile["edge"])
        self.assertEqual(profile["addresses"][0]["rdns"], "211-75-1-204.hinet-ip.hinet.net")
        self.assertEqual(profile["notice"], "")

    def test_cname_to_cloudfront_is_edge(self):
        profile = self._analyze(
            "shop.example.tw",
            {},
            {
                ("shop.example.tw", "CNAME"): ["d111111abcdef8.cloudfront.net"],
                ("shop.example.tw", "A"): ["13.35.1.1"],
            },
        )
        self.assertEqual(profile["edge"]["provider"], "Amazon CloudFront")

    def test_dns_failure_never_raises(self):
        with mock.patch.object(infra_scanner, "_resolver", side_effect=OSError("no network")):
            profile = infra_scanner.analyze_infrastructure("example.com", {})
        self.assertEqual(profile["addresses"], [])
        self.assertEqual(profile["scan_target"], "unknown")


class StrengthTests(SimpleTestCase):
    def _pages(self, headers=CF_HEADERS):
        return [
            {
                "url": "https://ntubimdbirc.tw/",
                "final_url": "https://ntubimdbirc.tw/",
                "status_code": 200,
                "headers": headers,
                "load_time_ms": 1800,
                "layout_metrics": {"viewport_width": 375, "overflow_px": 0},
            },
            {
                "url": "https://ntubimdbirc.tw/about",
                "final_url": "https://ntubimdbirc.tw/about",
                "status_code": 200,
                "headers": headers,
                "load_time_ms": 2100,
                "layout_metrics": {"viewport_width": 375, "overflow_px": 0},
            },
        ]

    def _strengths(self, **kw):
        base = dict(
            pages=self._pages(),
            infrastructure={
                "edge": {
                    "provider": "Cloudflare",
                    "waf_capable": True,
                    "evidence": ["回應標頭：cf-ray"],
                }
            },
            dns={
                "spf": "v=spf1 a:ntubimdbirc.tw -all",
                "dmarc": None,
                "dmarc_policy": None,
                "dnssec": True,
            },
            seo_report={
                "site_checks": [
                    {"key": "http_to_https", "level": "pass"},
                    {"key": "robots_txt", "level": "pass"},
                    {"key": "sitemap", "level": "pass"},
                    {"key": "not_found", "level": "pass"},
                ]
            },
            finding_rules=set(),
            finding_titles={"缺少 CSP"},
            categories={"seo", "aeo", "geo", "ux", "security"},
        )
        base.update(kw)
        return {s["key"]: s for s in collect_strengths(**base)}

    def test_good_practices_are_listed(self):
        strengths = self._strengths()
        self.assertEqual(
            set(strengths),
            {
                "edge",
                "https",
                "hsts",
                "nosniff",
                "dnssec",
                "spf",
                "robots_sitemap",
                "not_found",
                "mobile_layout",
                "speed",
            },
        )
        self.assertIn("WAF", strengths["edge"]["detail"])
        self.assertIn("180 天", strengths["hsts"]["detail"])
        # 每一項都附可核對的依據；單次實驗室量測的速度只算推論
        self.assertTrue(all(item["evidence"] for item in strengths.values()))
        self.assertEqual(strengths["speed"]["confidence"], "likely")
        self.assertEqual(strengths["hsts"]["confidence"], "confirmed")

    def test_cdn_does_not_imply_waf_is_blocking(self):
        """2026-10-06 審查：偵測到 Cloudflare 不等於「已部署有效的入侵防護」。"""
        detail = self._strengths()["edge"]["detail"]
        self.assertIn("無法從外部確認", detail)
        self.assertNotIn("阻擋", detail)
        blocked = self._strengths(finding_rules={"waf_block_detected"})["edge"]["detail"]
        self.assertIn("確認防護規則已生效", blocked)

    def test_strengths_never_contradict_findings_or_unchecked_categories(self):
        headers = {**CF_HEADERS, "content-security-policy": "default-src 'self' 'unsafe-inline'"}
        strengths = self._strengths(
            pages=self._pages(headers),
            finding_rules={"header-csp-unsafe"},
            finding_titles=set(),
            categories={"seo"},
        )
        self.assertNotIn("csp", strengths)
        self.assertNotIn("https", strengths)  # 沒勾資安就不評資安優點
        self.assertIn("robots_sitemap", strengths)

    def test_build_site_profile_survives_network_failure(self):
        with (
            mock.patch(
                "apps.scans.site_profile.analyze_infrastructure", return_value={"edge": None}
            ),
            mock.patch("apps.scans.site_profile.email_dns_posture", return_value={}),
        ):
            profile = build_site_profile(
                hostname="ntubimdbirc.tw",
                pages=self._pages(),
                seo_report={},
                findings=[],
                categories={"security"},
            )
        self.assertEqual(profile["version"], 2)
        self.assertIn("https", {s["key"] for s in profile["strengths"]})


class ReportSiteProfileTests(TestCase):
    """報告第一章要呈現網站架構（CDN 提醒）與做得好的地方，並符合 schema。"""

    def setUp(self):
        user = get_user_model().objects.create_user(
            username="profile", password="safe-test-password"
        )
        self.scan = ScanJob.objects.create(
            user=user,
            original_url="https://ntubimdbirc.tw/",
            normalized_url="https://ntubimdbirc.tw/",
            origin="https://ntubimdbirc.tw",
            status=ScanJob.Status.COMPLETED,
            overall_score=62,
            category_scores={"security": 67},
            completed_at=timezone.now(),
            site_profile={
                "version": 1,
                "infrastructure": {
                    "hostname": "ntubimdbirc.tw",
                    "addresses": [
                        {"ip": "104.21.4.142", "version": 4, "rdns": "", "network": "Cloudflare"}
                    ],
                    "cname": [],
                    "nameservers": ["rob.ns.cloudflare.com"],
                    "edge": {
                        "provider": "Cloudflare",
                        "waf_capable": True,
                        "evidence": ["回應標頭：cf-ray"],
                    },
                    "scan_target": "edge",
                    "notice": infra_scanner.edge_notice({"provider": "Cloudflare"}),
                },
                "strengths": [
                    {
                        "key": "hsts",
                        "category": "security",
                        "title": "已啟用 HSTS",
                        "detail": "瀏覽器會在 180 天內強制使用 HTTPS。",
                    }
                ],
            },
        )

    def test_payload_and_document_show_edge_and_strengths(self):
        payload = build_report_payload(self.scan)
        schema = json.loads(
            (Path(report_render.__file__).parent / "schema.json").read_text("utf-8")
        )
        self.assertEqual(list(Draft7Validator(schema).iter_errors(payload)), [])
        facts = {f["label"]: f["value"] for f in payload["site_profile"]["facts"]}
        self.assertEqual(facts["實際掃描到"], "Cloudflare 邊緣節點（CDN／反向代理）")
        self.assertIn("104.21.4.142（Cloudflare 網段・無反解）", facts["IP 與反解"])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.docx"
            render_report_docx(self.scan, path)
            document = Document(str(path))
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("網站優勢", text)
        self.assertIn("已啟用 HSTS", text)
        self.assertIn("目前掃描目標位於 Cloudflare Edge，而非直接掃描 Origin Server", text)

    def test_old_scan_without_profile_has_no_section(self):
        self.scan.site_profile = {}
        self.scan.save(update_fields=["site_profile"])
        self.assertNotIn("site_profile", build_report_payload(self.scan))


class TechStackTests(SimpleTestCase):
    """網站使用的技術：只用已取得的 HTML 與標頭被動辨識，每項附依據。"""

    def test_next_js_site_behind_cloudflare(self):
        from apps.scans.tech_stack import detect_technologies

        html = (
            '<html><head><script src="/_next/static/chunks/main.js"></script>'
            '<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>'
            '<link href="https://fonts.googleapis.com/css2?family=Noto"></head></html>'
        )
        techs = {t["name"]: t for t in detect_technologies(html, {"Server": "cloudflare"})}
        self.assertEqual(
            set(techs), {"Next.js", "Google Analytics", "Google Fonts", "Cloudflare"}
        )
        self.assertEqual(techs["Next.js"]["category"], "網站框架")
        self.assertTrue(all(t["evidence"] for t in techs.values()))

    def test_plain_words_are_not_fingerprints(self):
        from apps.scans.tech_stack import detect_technologies

        html = "<p>我們使用 WordPress 與 jQuery 的經驗分享</p>"
        self.assertEqual(detect_technologies(html, {}), [])
