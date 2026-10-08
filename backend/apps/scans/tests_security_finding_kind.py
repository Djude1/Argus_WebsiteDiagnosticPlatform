"""資安發現的類型標示（roadmap §5 第 1 項、§12 第 6 項第一階段：只標示，不影響分數）。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.scans.models import Finding, ScanJob
from apps.scans.projects import issue_groups
from apps.scans.reports import build_report_payload
from apps.scans.security.finding_kind import (
    CONFIG,
    EXPOSURE,
    SUSPECTED,
    VERIFIED,
    kind_payload,
    security_kind,
)
from apps.scans.serializers import FindingSerializer


def _kind(**kw):
    return security_kind(category="security", **kw)


class SecurityKindMappingTests(SimpleTestCase):
    def test_config_settings(self):
        for rule_id in ("header-csp-unsafe-inline", "cookie-missing-secure", "dns-spf-missing",
                        "ssl-weak-cipher", "sri-missing", "zap-10038", "exposure-securitytxt"):
            self.assertEqual(_kind(rule_id=rule_id), CONFIG, rule_id)
        # 沒有明確 rule_id 的內建檢查依標題判斷
        self.assertEqual(_kind(rule_id="SECURITY_X_1234", title="缺少 HSTS"), CONFIG)

    def test_exposure(self):
        for rule_id in ("service-version-exposed", "header-x-powered-by", "exposure-admin-panel",
                        "security-pii-public-contact"):
            self.assertEqual(_kind(rule_id=rule_id), EXPOSURE, rule_id)
        # 探測到的一般檔案（低風險）是曝露面
        self.assertEqual(_kind(rule_id="exposure-readme", severity="low"), EXPOSURE)

    def test_suspected(self):
        for rule_id in ("service-known-cve", "js-lib-known-vuln", "exposure-hardcoded-secret",
                        "agent-observed-security", "header-cors-credentials"):
            self.assertEqual(_kind(rule_id=rule_id), SUSPECTED, rule_id)
        self.assertEqual(_kind(title="表單可能缺少 CSRF token"), SUSPECTED)
        # Nuclei 樣板命中只代表符合樣板特徵
        self.assertEqual(_kind(rule_id="SECURITY_N_1", evidence="Template：tech-detect"), SUSPECTED)

    def test_verified(self):
        self.assertEqual(_kind(rule_id="kali-sqlmap-sqli", severity="critical"), VERIFIED)
        # 真的下載到高風險檔案（.env、.git）
        self.assertEqual(_kind(rule_id="exposure-env-file", severity="critical"), VERIFIED)
        self.assertEqual(_kind(rule_id="exposure-git-config", severity="high"), VERIFIED)

    def test_scan_notes_and_other_categories_have_no_kind(self):
        # 掃描本身的說明（被防護機制擋下）不屬於任何類型
        self.assertIsNone(_kind(
            rule_id="SECURITY_W_1", title="主動弱點掃描 0 項發現，但目標位於 Cloudflare 之後",
            evidence="Nuclei 掃描 3 個 URL，回傳 0 項發現",
        ))
        self.assertIsNone(security_kind(category="seo", rule_id="header-x"))
        self.assertEqual(
            kind_payload(category="seo", rule_id="seo-title"),
            {"security_kind": None, "security_kind_label": ""},
        )


class SecurityKindSurfacesTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="kind", password="safe-test-password")
        self.scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", status=ScanJob.Status.COMPLETED, overall_score=70,
            category_scores={"security": 60, "seo": 80}, max_pages=1, max_depth=1,
            completed_at=timezone.now(),
        )

    def _finding(self, **kw):
        base = dict(
            scan_job=self.scan, page=None, severity="medium", category=Finding.Category.SECURITY,
            title="t", description="d", remediation="r", evidence="e", rule_id="r",
            ai_handoff_prompt="p", priority_score=10.0,
        )
        base.update(kw)
        return Finding.objects.create(**base)

    def test_serializer_issue_groups_and_report_show_kind(self):
        cve = self._finding(
            rule_id="service-known-cve", title="nginx 1.18 有已知漏洞", severity="high",
        )
        self._finding(
            rule_id="seo-title-missing", title="缺少 title", category=Finding.Category.SEO,
        )

        data = FindingSerializer(cve).data
        self.assertEqual(
            (data["security_kind"], data["security_kind_label"]), (SUSPECTED, "疑似弱點"),
        )

        groups = issue_groups(self.scan)
        kinds = {g["title"]: g["security_kind_label"] for g in groups.values()}
        self.assertEqual(kinds, {"nginx 1.18 有已知漏洞": "疑似弱點", "缺少 title": ""})

        payload = build_report_payload(self.scan)
        traces = {f["title"]: f["trace"] for f in payload["findings"]}
        self.assertIn("類型：疑似弱點", traces["nginx 1.18 有已知漏洞"])
        self.assertNotIn("類型：", traces["缺少 title"])
