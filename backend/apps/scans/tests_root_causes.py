"""根本原因關聯（root_causes.py）：同一處修法的問題分在一起，只是呈現、不改計分。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.scans.models import Finding, ScanJob
from apps.scans.root_causes import annotate_root_causes, cause_for

User = get_user_model()


def _issue(key, rule_id, severity="low", pages=1):
    return {"key": key, "rule_id": rule_id, "severity": severity, "pages": pages}


class CauseForTests(SimpleTestCase):
    def test_rule_ids_from_real_scans(self):
        # 規則名稱取自示範專案的真實掃描（demo/dataset.json.gz）與站台層級檢查
        cases = {
            "SECURITY_CSP_BD010B5BE0": "server-headers",
            "SECURITY_HSTS_6A08D9EE20": "server-headers",
            "SECURITY_X_FRAME_OPTIONS_A7A326FEA9": "server-headers",
            "SECURITY_X_CONTENT_TYPE_OPTIONS_89053405E6": "server-headers",
            "header-x-powered-by": "server-headers",
            "header-hsts-missing": "server-headers",
            "cookie-no-httponly": "cookie-attributes",
            "ssl-weak-protocol": "tls",
            "dns-spf-missing": "email-domain-auth",
            "dns-dmarc-policy-weak": "email-domain-auth",
            "SEO_ALT_97B655BF66": "image-alt",
            "axe-image-alt": "image-alt",
            "geo-article-date-missing": "article-metadata",
        }
        for rule_id, expected in cases.items():
            with self.subTest(rule_id=rule_id):
                self.assertEqual(cause_for(rule_id).id, expected)

    def test_unrelated_rules_have_no_cause(self):
        # 頁面沒有 HTTPS、CSRF、DNSSEC、其他 axe 規則：修法不在同一處，不歸類
        for rule_id in ("SECURITY_HTTPS_4EDA524EB2", "SECURITY_CSRF_TOKEN_1BC47D8B6C",
                        "dns-dnssec-missing", "axe-color-contrast", "", "seo-title"):
            with self.subTest(rule_id=rule_id):
                self.assertIsNone(cause_for(rule_id))


class AnnotateTests(SimpleTestCase):
    def test_groups_two_or_more_and_orders_by_severity(self):
        issues = [
            _issue("a", "SECURITY_CSP_X", "low", pages=1),
            _issue("b", "header-hsts-missing", "medium", pages=1),
            _issue("c", "SEO_ALT_X", "low", pages=18),
            _issue("d", "axe-image-alt", "medium", pages=12),
            _issue("e", "dns-spf-missing", "medium"),  # 只有一個：不分組
            _issue("f", "SEO_H1_X", "low"),
        ]
        summaries = annotate_root_causes(issues)

        self.assertEqual([s["id"] for s in summaries], ["image-alt", "server-headers"])
        image_alt = summaries[0]
        self.assertEqual(
            (image_alt["count"], image_alt["severity"], image_alt["pages"], image_alt["issues"]),
            (2, "medium", 18, ["c", "d"]),
        )
        self.assertEqual(
            {i["key"]: i.get("root_cause") for i in issues},
            {"a": "server-headers", "b": "server-headers", "c": "image-alt",
             "d": "image-alt", "e": None, "f": None},
        )


class IssuesApiTests(TestCase):
    def test_issues_endpoint_returns_root_causes(self):
        user = User.objects.create_user(username="causes", password="safe-test-password")
        scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", status=ScanJob.Status.COMPLETED,
            completed_at=timezone.now(), category_scores={"security": 80},
        )
        for rule_id, title in (("SECURITY_CSP_X", "缺少 CSP"), ("header-hsts-missing", "缺少 HSTS"),
                               ("SECURITY_HTTPS_X", "頁面未使用 HTTPS")):
            Finding.objects.create(
                scan_job=scan, category="security", severity="medium", title=title,
                description="d", remediation="r", rule_id=rule_id, ai_handoff_prompt="p",
            )
        client = APIClient()
        client.force_authenticate(user=user)

        data = client.get(f"/api/projects/{scan.project_id}/issues/").json()

        self.assertEqual([c["id"] for c in data["root_causes"]], ["server-headers"])
        self.assertEqual(data["root_causes"][0]["count"], 2)
        by_rule = {i["rule_id"]: i.get("root_cause") for i in data["issues"]}
        self.assertEqual(by_rule["SECURITY_HTTPS_X"], None)
        self.assertEqual(by_rule["header-hsts-missing"], "server-headers")


class ReportRootCauseTests(TestCase):
    """PDF 報告摘要的「改一處就能一起解決」：項次對應第 4 章，資訊提示不列。"""

    def setUp(self):
        user = User.objects.create_user(username="report-causes", password="safe-test-password")
        self.scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", status=ScanJob.Status.COMPLETED,
            completed_at=timezone.now(), category_scores={"security": 80}, overall_score=80,
        )
        for rule_id, title, severity in (
            ("SECURITY_CSP_X", "缺少 CSP", "low"),
            ("header-hsts-missing", "缺少 HSTS", "medium"),
            ("header-x-powered-by", "回應標頭透露技術", "info"),
            ("dns-spf-missing", "網域缺少 SPF 記錄", "medium"),
        ):
            Finding.objects.create(
                scan_job=self.scan, category="security", severity=severity, title=title,
                description="d", remediation="r", rule_id=rule_id, ai_handoff_prompt="p",
            )

    def test_payload_lists_causes_with_chapter_refs(self):
        from apps.scans.reports import build_report_payload

        payload = build_report_payload(self.scan)
        causes = payload["summary"]["root_causes"]
        self.assertEqual([c["title"] for c in causes], ["網站伺服器的回應標頭設定"])
        refs = {f["title"]: f["id"] for f in payload["findings"]}
        self.assertEqual(sorted(causes[0]["refs"]), sorted([refs["缺少 CSP"], refs["缺少 HSTS"]]))

    def test_rendered_summary_has_section(self):
        from docx import Document

        from apps.scans.reports import render_report_docx

        text = "\n".join(p.text for p in Document(render_report_docx(self.scan)).paragraphs)
        self.assertIn("改一處就能一起解決", text)
        self.assertIn("在哪裡修：網站伺服器", text)
