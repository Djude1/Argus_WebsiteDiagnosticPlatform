"""示範專案：新帳號自動建立、資料完整、唯讀限制、後台統計與評論資格不計入；新增專案的預設掃描設定。"""

from __future__ import annotations

import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.rebuild.models import SiteRebuild
from apps.scans.demo.seed import create_demo_project, load_dataset
from apps.scans.models import Finding, FixOutput, Page, ScanJob, SiteProject

User = get_user_model()


def make_user(name: str, **extra):
    return User.objects.create_user(
        username=f"{name}@example.com", email=f"{name}@example.com", password="x", **extra
    )


class DemoDatasetTests(APITestCase):
    def setUp(self):
        self.user = make_user("demo-owner")
        self.project = create_demo_project(self.user)

    def test_creates_three_completed_scans_with_full_data(self):
        dataset = load_dataset()
        self.assertTrue(self.project.is_demo)
        self.assertTrue(self.project.favicon.startswith("data:image/"))
        scans = list(ScanJob.objects.filter(project=self.project).order_by("completed_at"))
        self.assertEqual(len(scans), len(dataset["scans"]))
        self.assertEqual(len(scans), 3)
        for scan, entry in zip(scans, dataset["scans"], strict=True):
            self.assertEqual(scan.status, ScanJob.Status.COMPLETED)
            self.assertEqual(scan.user, self.user)
            self.assertEqual(scan.pages.count(), len(entry["pages"]))
            self.assertEqual(scan.findings.count(), len(entry["findings"]))
            self.assertEqual(scan.aeo_report.get("status"), "evaluated")
            self.assertEqual(set(scan.category_scores), {"seo", "aeo", "geo", "ux", "security"})
        latest = scans[-1]
        # 五個維度、各種嚴重度都有，示範才看得出 Argus 能分析什麼
        self.assertEqual(
            set(latest.findings.values_list("category", flat=True)),
            {"seo", "aeo", "geo", "ux", "security"},
        )
        self.assertTrue(scans[0].findings.filter(severity="critical").exists())
        self.assertEqual(FixOutput.objects.get(scan_job=latest).status, FixOutput.Status.READY)

    def test_timestamps_are_spread_up_to_yesterday(self):
        scans = list(ScanJob.objects.filter(project=self.project).order_by("completed_at"))
        now = timezone.now()
        self.assertLess(now - scans[-1].completed_at, timedelta(days=2))
        self.assertGreater(now - scans[0].completed_at, timedelta(days=20))
        self.assertTrue(all(s.created_at <= s.started_at <= s.completed_at for s in scans))
        log_time = scans[-1].scan_log[0]["t"]
        self.assertTrue(log_time.startswith(scans[-1].started_at.date().isoformat()[:7]))

    def test_screenshots_ship_with_the_code_and_are_served(self):
        page = (
            Page.objects.filter(scan_job__project=self.project).exclude(screenshot_path="").first()
        )
        self.assertTrue(page.screenshot_path.startswith("apps/scans/demo/screenshots/"))
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/scans/{page.scan_job_id}/pages/{page.id}/screenshot/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_overview_issues_and_pages_work(self):
        self.client.force_authenticate(self.user)
        overview = self.client.get(f"/api/projects/{self.project.id}/overview/").json()
        self.assertEqual(len(overview["trend"]), 3)
        self.assertTrue(overview["site_description"])
        issues = self.client.get(f"/api/projects/{self.project.id}/issues/").json()
        statuses = {issue["status"] for issue in issues["issues"]}
        self.assertTrue({"new", "persisting"} <= statuses)
        self.assertTrue(issues["missing"])
        pages = self.client.get(f"/api/projects/{self.project.id}/pages/").json()
        self.assertGreaterEqual(len(pages["pages"]), 15)

    def test_seo_analysis_has_link_checks_with_evidence(self):
        """示範資料要能展示 SEO 分析頁：每次掃描都有連結檢查，v1 的連結問題到 v3 有改善。"""
        self.client.force_authenticate(self.user)
        scans = list(ScanJob.objects.filter(project=self.project).order_by("completed_at"))
        self.assertTrue(all(scan.seo_report.get("checked_at") for scan in scans))

        def seo(scan):
            url = f"/api/projects/{self.project.id}/seo/?scan={scan.id}"
            return self.client.get(url).json()

        first, latest = seo(scans[0]), seo(scans[-1])
        titles = {issue["title"]: issue for issue in first["issues"]}
        broken = titles["站內失效連結"]
        self.assertTrue(broken["pages"][0]["url"].startswith("http://www.morninglight-coffee.example"))
        self.assertTrue(broken["pages"][0]["detected_at"])
        self.assertIn("連結沒有可讀文字", titles)
        self.assertEqual(
            {row["type"] for row in first["links"]["rows"]}, {"internal", "subdomain", "external"}
        )
        self.assertTrue(any(check["key"] == "www" for check in first["site_checks"]))
        self.assertLess(latest["overview"]["broken_links"], first["overview"]["broken_links"])

    def test_idempotent_and_not_recreated_after_archive(self):
        self.assertIsNone(create_demo_project(self.user))
        self.project.archived_at = timezone.now()
        self.project.save()
        self.assertIsNone(create_demo_project(self.user))
        self.assertEqual(SiteProject.objects.filter(user=self.user, is_demo=True).count(), 1)


class DemoReadOnlyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("demo-guard")
        self.project = create_demo_project(self.user)
        self.latest = ScanJob.objects.filter(project=self.project).order_by("-completed_at").first()
        self.client.force_authenticate(self.user)

    def test_cannot_create_scan_in_demo_project(self):
        response = self.client.post(
            "/api/scans/",
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 1,
                "max_depth": 1,
                "categories": ["seo"],
                "project": self.project.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("project", response.json())

    def test_cannot_edit_demo_project_but_can_archive(self):
        response = self.client.patch(
            f"/api/projects/{self.project.id}/", {"name": "改名"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete(f"/api/projects/{self.project.id}/").status_code, 204)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_fix_output_and_rebuild_are_blocked(self):
        response = self.client.post(f"/api/scans/{self.latest.id}/fix-output/trigger/")
        self.assertEqual(response.status_code, 400)
        page = self.latest.pages.first()
        response = self.client.post("/api/rebuilds/", {"page": page.id})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SiteRebuild.objects.exists())

    def test_scan_serializer_marks_demo(self):
        data = self.client.get(f"/api/scans/{self.latest.id}/").json()
        self.assertTrue(data["is_demo"])
        project = self.client.get(f"/api/projects/{self.project.id}/").json()
        self.assertTrue(project["is_demo"])

    def test_demo_scans_do_not_count_for_reviews(self):
        response = self.client.get(reverse("reviews-mine"))
        self.assertFalse(response.data["eligibility"]["eligible"])

    def test_admin_overview_excludes_demo_scans(self):
        admin = make_user("admin-demo", is_staff=True)
        self.client.force_authenticate(admin)
        totals = self.client.get(reverse("admin-overview")).data["totals"]
        self.assertEqual(totals["scans"], 0)
        listing = self.client.get(reverse("admin-scans")).data
        self.assertEqual(listing["scans"], [])


class DemoOnRegistrationTests(APITestCase):
    def setUp(self):
        cache.clear()

    def register(self, email):
        return self.client.post(
            "/api/auth/register/", {"email": email, "password": "StrongPass123!"}, format="json"
        )

    def test_register_creates_demo_project(self):
        self.assertEqual(self.register("fresh@example.com").status_code, 201)
        project = SiteProject.objects.get(user__email="fresh@example.com")
        self.assertTrue(project.is_demo)
        self.assertEqual(ScanJob.objects.filter(project=project).count(), 3)

    @override_settings(ARGUS_DEMO_PROJECT_ENABLED=False)
    def test_can_be_disabled(self):
        self.assertEqual(self.register("nodemo@example.com").status_code, 201)
        self.assertFalse(SiteProject.objects.filter(user__email="nodemo@example.com").exists())

    def test_seed_failure_does_not_break_registration(self):
        with patch("apps.scans.demo.seed.create_demo_project", side_effect=RuntimeError("boom")):
            self.assertEqual(self.register("robust@example.com").status_code, 201)
        self.assertTrue(User.objects.filter(email="robust@example.com").exists())
        self.assertFalse(Finding.objects.exists())

    def test_command_seeds_users_without_projects(self):
        empty = make_user("empty")
        busy = make_user("busy")
        SiteProject.objects.create(
            user=busy, name="x", origin="https://x.example.com", start_url="https://x.example.com/"
        )
        out = io.StringIO()
        call_command("seed_demo_project", "--without-projects", stdout=out)
        self.assertTrue(SiteProject.objects.filter(user=empty, is_demo=True).exists())
        self.assertFalse(SiteProject.objects.filter(user=busy, is_demo=True).exists())
        call_command("seed_demo_project", "--without-projects", stdout=out)
        self.assertEqual(SiteProject.objects.filter(user=empty).count(), 1)


@patch("apps.scans.views.refresh_project_favicon_from_url")
class ProjectCreateDefaultsTests(APITestCase):
    def setUp(self):
        self.user = make_user("creator")
        self.client.force_authenticate(self.user)

    def test_create_with_description_and_scan_defaults(self, _favicon):
        response = self.client.post(
            "/api/projects/",
            {
                "start_url": "https://example.com/",
                "name": "官網",
                "description": "  公司官網  ",
                "default_scope": "single",
                "default_categories": ["ux", "seo"],
                "default_scan_mode": "passive",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        data = response.json()
        self.assertEqual(data["description"], "公司官網")
        self.assertEqual(data["default_scope"], "single")
        self.assertEqual(data["default_categories"], ["seo", "ux"])
        self.assertFalse(data["is_demo"])

    def test_active_mode_requires_security_category(self, _favicon):
        response = self.client.post(
            "/api/projects/",
            {
                "start_url": "https://example.com/",
                "default_categories": ["seo"],
                "default_scan_mode": "active",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("default_scan_mode", response.json())

    def test_update_defaults_and_description(self, _favicon):
        project = SiteProject.objects.create(
            user=self.user, name="a", origin="https://example.com", start_url="https://example.com/"
        )
        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {"description": "新說明", "default_scan_mode": "active"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        self.assertEqual((project.description, project.default_scan_mode), ("新說明", "active"))
