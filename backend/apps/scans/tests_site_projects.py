"""網站專案（docs/adr/0003-site-project-workspace.md）：歸入規則、API、總覽與跨掃描問題比較。"""

from __future__ import annotations

import importlib
import io
from contextlib import redirect_stdout
from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import CoinWallet
from apps.scans.models import Finding, ScanJob, SiteProject

backfill = importlib.import_module(
    "apps.scans.migrations.0019_site_projects"
).backfill_site_projects


def _user(name: str):
    user = get_user_model().objects.create_user(
        username=name, email=f"{name}@example.com", password="safe-test-password"
    )
    CoinWallet.objects.filter(user=user).update(balance=10000)
    return user


def _scan(user, origin="https://example.com", *, completed_minutes_ago=None, **extra):
    fields = {
        "user": user,
        "original_url": f"{origin}/",
        "normalized_url": f"{origin}/",
        "origin": origin,
        **extra,
    }
    if completed_minutes_ago is not None:
        fields.setdefault("status", ScanJob.Status.COMPLETED)
        fields.setdefault("overall_score", 70)
    scan = ScanJob.objects.create(**fields)
    if completed_minutes_ago is not None:
        done = timezone.now() - timedelta(minutes=completed_minutes_ago)
        ScanJob.objects.filter(id=scan.id).update(created_at=done, completed_at=done)
        scan.refresh_from_db()
    return scan


def _finding(scan, rule_id, *, severity="medium", category="seo", title=None):
    return Finding.objects.create(
        scan_job=scan,
        category=category,
        severity=severity,
        title=title or rule_id,
        description="d",
        remediation="r",
        rule_id=rule_id,
    )


class ProjectAssignmentTests(TestCase):
    def setUp(self):
        self.user = _user("assign")

    def test_scan_without_project_joins_project_of_same_origin(self):
        first = _scan(self.user)
        second = _scan(self.user)
        other_site = _scan(self.user, "https://shop.example.com")
        self.assertIsNotNone(first.project_id)
        self.assertEqual(first.project_id, second.project_id)
        self.assertNotEqual(first.project_id, other_site.project_id)
        project = first.project
        self.assertEqual(project.name, "example.com")
        self.assertEqual(project.start_url, "https://example.com/")

    def test_same_origin_of_different_users_are_separate_projects(self):
        mine = _scan(self.user)
        theirs = _scan(_user("other"))
        self.assertNotEqual(mine.project_id, theirs.project_id)

    def test_new_scan_restores_archived_project(self):
        scan = _scan(self.user)
        SiteProject.objects.filter(id=scan.project_id).update(archived_at=timezone.now())
        again = _scan(self.user)
        again.project.refresh_from_db()
        self.assertEqual(again.project_id, scan.project_id)
        self.assertIsNone(again.project.archived_at)

    def test_backfill_groups_existing_scans_by_user_and_origin(self):
        a1 = _scan(self.user)
        a2 = _scan(self.user)
        b = _scan(self.user, "https://shop.example.com")
        ScanJob.objects.update(project=None)
        SiteProject.objects.all().delete()
        backfill(django_apps, None)
        a1.refresh_from_db()
        a2.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(SiteProject.objects.count(), 2)
        self.assertEqual(a1.project_id, a2.project_id)
        self.assertNotEqual(a1.project_id, b.project_id)
        self.assertEqual(ScanJob.objects.filter(project__isnull=True).count(), 0)


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class ProjectApiTests(APITestCase):
    def setUp(self):
        self.user = _user("api")
        self.client.force_authenticate(self.user)

    def _create(self, url, **extra):
        return self.client.post(
            reverse("site-project-list"), {"start_url": url, **extra}, format="json"
        )

    def test_create_list_and_duplicate_conflict(self):
        response = self._create("example.com/about", name="官網")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["origin"], "https://example.com")
        self.assertEqual(response.data["start_url"], "https://example.com/about")
        self.assertEqual(response.data["name"], "官網")
        self.assertEqual(response.data["summary"]["scans_count"], 0)

        duplicate = self._create("https://example.com/")
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(duplicate.data["project"]["id"], response.data["id"])

        listed = self.client.get(reverse("site-project-list"))
        self.assertEqual([p["id"] for p in listed.data], [response.data["id"]])

    def test_archive_hides_project_and_recreate_restores_history(self):
        scan = _scan(self.user, completed_minutes_ago=5)
        project_id = scan.project_id
        detail = reverse("site-project-detail", args=[project_id])
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(reverse("site-project-list")).data, [])
        # 掃描不受影響、單筆仍可讀（舊掃描詳情要能顯示所屬專案）
        self.assertTrue(ScanJob.objects.filter(id=scan.id, project_id=project_id).exists())
        self.assertIsNotNone(self.client.get(detail).data["archived_at"])

        restored = self._create("https://example.com/")
        self.assertEqual(restored.status_code, status.HTTP_201_CREATED)
        self.assertEqual(restored.data["id"], project_id)
        self.assertEqual(restored.data["summary"]["scans_count"], 1)

    def test_update_keeps_start_url_within_same_site(self):
        project_id = self._create("https://example.com/").data["id"]
        detail = reverse("site-project-detail", args=[project_id])
        ok = self.client.patch(detail, {"name": "新名稱", "start_url": "https://example.com/zh"})
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data["start_url"], "https://example.com/zh")
        moved = self.client.patch(detail, {"start_url": "https://example.org/"})
        self.assertEqual(moved.status_code, status.HTTP_400_BAD_REQUEST)
        blank = self.client.patch(detail, {"name": "  "})
        self.assertEqual(blank.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_users_project_is_not_found(self):
        theirs = _scan(_user("stranger")).project
        self.assertEqual(
            self.client.get(reverse("site-project-detail", args=[theirs.id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(reverse("site-project-overview", args=[theirs.id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_scan_in_project_checks_site_and_owner(self):
        project_id = self._create("https://example.com/").data["id"]
        payload = {"authorization_confirmed": True, "project": project_id}
        created = self.client.post(
            reverse("scan-list"), {**payload, "url": "https://example.com/pricing"}, format="json"
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["project"], project_id)

        other_site = self.client.post(
            reverse("scan-list"), {**payload, "url": "https://example.org/"}, format="json"
        )
        self.assertEqual(other_site.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("url", other_site.data)

        theirs = _scan(_user("stranger2")).project_id
        foreign = self.client.post(
            reverse("scan-list"),
            {**payload, "project": theirs, "url": "https://example.com/"},
            format="json",
        )
        self.assertEqual(foreign.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", foreign.data)

    def test_scan_list_filtered_by_project_returns_every_scan(self):
        first = _scan(self.user, completed_minutes_ago=30)
        second = _scan(self.user, completed_minutes_ago=5)
        _scan(self.user, "https://shop.example.com")
        response = self.client.get(reverse("scan-list"), {"project": first.project_id})
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(sorted(ids), sorted([first.id, second.id]))
        # 未帶 project 時維持舊行為：每個 origin 只回最新一筆
        default = self.client.get(reverse("scan-list"))
        self.assertEqual(len(default.data["results"]), 2)


class ProjectOverviewAndIssuesTests(APITestCase):
    def setUp(self):
        self.user = _user("overview")
        self.client.force_authenticate(self.user)
        self.old = _scan(self.user, completed_minutes_ago=60, overall_score=60)
        self.new = _scan(self.user, completed_minutes_ago=10, overall_score=75)
        self.project_id = self.new.project_id
        # 舊：a、b（seo）、g（geo）；新：b（兩頁）、c，且新掃描沒勾 geo
        _finding(self.old, "a")
        _finding(self.old, "b", severity="low")
        _finding(self.old, "g", category="geo")
        _finding(self.new, "b", severity="low")
        _finding(self.new, "b", severity="high")
        _finding(self.new, "c", severity="critical")
        ScanJob.objects.filter(id=self.new.id).update(categories=["seo"])

    def test_issues_compare_with_previous_scan(self):
        data = self.client.get(reverse("site-project-issues", args=[self.project_id])).data
        self.assertEqual(data["scan"]["id"], self.new.id)
        self.assertEqual(data["compared_with"]["id"], self.old.id)
        by_key = {issue["key"]: issue for issue in data["issues"]}
        self.assertEqual(by_key["c"]["status"], "new")
        self.assertEqual(by_key["b"]["status"], "persisting")
        # 同規則多筆合併，嚴重度取最嚴重的一筆
        self.assertEqual(by_key["b"]["severity"], "high")
        self.assertEqual(by_key["b"]["occurrences"], 2)
        self.assertEqual([issue["key"] for issue in data["issues"]], ["c", "b"])
        # 本次沒勾 geo：g 不能算「未出現」；a 是 seo 且本次沒出現
        self.assertEqual([m["key"] for m in data["missing"]], ["a"])

    def test_issues_for_older_scan_and_unknown_scan(self):
        url = reverse("site-project-issues", args=[self.project_id])
        older = self.client.get(url, {"scan": self.old.id}).data
        self.assertIsNone(older["compared_with"])
        self.assertTrue(all(issue["status"] is None for issue in older["issues"]))
        other_project_scan = _scan(self.user, "https://shop.example.com", completed_minutes_ago=1)
        self.assertEqual(
            self.client.get(url, {"scan": other_project_scan.id}).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_overview_summarises_latest_scan_changes_and_trend(self):
        running = _scan(self.user, status=ScanJob.Status.CRAWLING)
        data = self.client.get(reverse("site-project-overview", args=[self.project_id])).data
        self.assertEqual(data["latest_scan"]["id"], self.new.id)
        self.assertEqual(data["previous_scan"]["overall_score"], 60)
        self.assertEqual(data["active_scan"]["id"], running.id)
        self.assertEqual(data["severity_counts"]["critical"], 1)
        self.assertEqual(data["severity_counts"]["high"], 1)
        self.assertEqual(data["changes"], {"new": 1, "persisting": 1, "missing": 1})
        self.assertEqual([p["id"] for p in data["trend"]], [self.old.id, self.new.id])
        self.assertEqual(data["scans_count"], 3)
        self.assertEqual(data["project"]["summary"]["latest_score"], 75)
        self.assertEqual(data["project"]["summary"]["previous_score"], 60)

    def test_overview_without_completed_scan(self):
        empty = SiteProject.objects.create(
            user=self.user,
            origin="https://empty.example.com",
            name="empty",
            start_url="https://empty.example.com/",
        )
        data = self.client.get(reverse("site-project-overview", args=[empty.id])).data
        self.assertIsNone(data["latest_scan"])
        self.assertIsNone(data["changes"])
        self.assertEqual(data["trend"], [])


class ProjectImprovementTests(APITestCase):
    """預設掃描設定、已封存清單、問題持續次數。"""

    def setUp(self):
        self.user = _user("improve")
        self.client.force_authenticate(self.user)

    def test_default_scan_settings_are_saved_and_validated(self):
        project = _scan(self.user).project
        detail = reverse("site-project-detail", args=[project.id])
        self.assertEqual(self.client.get(detail).data["default_scope"], "site")
        ok = self.client.patch(
            detail,
            {"default_scope": "single", "default_categories": ["security", "seo", "seo"]},
            format="json",
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data["default_scope"], "single")
        self.assertEqual(ok.data["default_categories"], ["seo", "security"])
        bad_payloads = (
            {"default_categories": []},
            {"default_categories": ["xss"]},
            {"default_scope": "all"},
        )
        for bad in bad_payloads:
            self.assertEqual(
                self.client.patch(detail, bad, format="json").status_code,
                status.HTTP_400_BAD_REQUEST,
            )

    def test_archived_projects_are_listed_separately(self):
        kept = _scan(self.user).project
        archived = _scan(self.user, "https://old.example.com").project
        SiteProject.objects.filter(id=archived.id).update(archived_at=timezone.now())
        url = reverse("site-project-list")
        self.assertEqual([p["id"] for p in self.client.get(url).data], [kept.id])
        self.assertEqual(
            [p["id"] for p in self.client.get(url, {"archived": "true"}).data], [archived.id]
        )
        restored = self.client.post(reverse("site-project-restore", args=[archived.id]))
        self.assertIsNone(restored.data["archived_at"])

    def test_issue_streak_counts_consecutive_scans(self):
        s1 = _scan(self.user, completed_minutes_ago=90)
        s2 = _scan(self.user, completed_minutes_ago=60)
        s3 = _scan(self.user, completed_minutes_ago=30)
        s4 = _scan(self.user, completed_minutes_ago=10)
        for scan in (s1, s2, s3, s4):
            _finding(scan, "always")
        _finding(s1, "gap")
        _finding(s3, "gap")
        _finding(s4, "gap")
        _finding(s4, "fresh")
        # s2 沒勾 geo：geo 問題的連續次數到 s2 就無從判斷
        ScanJob.objects.filter(id=s2.id).update(categories=["seo"])
        for scan in (s1, s3, s4):
            _finding(scan, "geo-rule", category="geo")
        data = self.client.get(reverse("site-project-issues", args=[s4.project_id])).data
        by_key = {issue["key"]: issue for issue in data["issues"]}
        self.assertEqual(by_key["always"]["streak"], 4)
        self.assertEqual(by_key["gap"]["streak"], 2)
        self.assertEqual(by_key["fresh"]["streak"], 1)
        self.assertEqual(by_key["geo-rule"]["streak"], 2)
        s1.refresh_from_db()
        self.assertEqual(by_key["always"]["since"], s1.completed_at)


class ProjectIssueScopeTests(APITestCase):
    def test_issues_only_include_checked_categories(self):
        user = _user("scope")
        self.client.force_authenticate(user)
        scan = _scan(user, completed_minutes_ago=5, categories=["seo"])
        _finding(scan, "seo-rule")
        _finding(scan, "dns-spf-missing", category="security")
        ScanJob.objects.filter(id=scan.id).update(
            top_actions=[
                {"title": "缺少 SPF", "category": "security", "severity": "medium"},
                {"title": "seo-rule", "category": "seo", "severity": "medium"},
            ]
        )
        data = self.client.get(reverse("site-project-issues", args=[scan.project_id])).data
        self.assertEqual([issue["key"] for issue in data["issues"]], ["seo-rule"])
        overview = self.client.get(reverse("site-project-overview", args=[scan.project_id])).data
        self.assertEqual(overview["latest_scan"]["issues_count"], 1)
        self.assertEqual([a["category"] for a in overview["latest_scan"]["top_actions"]], ["seo"])


class SiteProjectMigrationRecoveryTests(TransactionTestCase):
    """0019 遇到先前被回退版本留下的表與欄位時仍要能套用（2026-10-02 Docker migrate 失敗）。"""

    BEFORE = [("scans", "0018_scanjob_aeo_report")]
    AFTER = [("scans", "0019_site_projects")]

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def test_migration_recovers_from_leftover_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.BEFORE)
        old_apps = executor.loader.project_state(self.BEFORE).apps
        user = old_apps.get_model("accounts", "User").objects.create(
            username="leftover", email="leftover@example.com"
        )
        old_apps.get_model("scans", "ScanJob").objects.create(
            user_id=user.id,
            original_url="https://a.example/",
            normalized_url="https://a.example/",
            origin="https://a.example",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE scans_siteproject (id integer PRIMARY KEY, name varchar(80))"
            )
            cursor.execute("ALTER TABLE scans_scanjob ADD COLUMN project_id bigint NULL")
            cursor.execute(
                "CREATE INDEX scans_scanjob_project_id_left ON scans_scanjob (project_id)"
            )

        executor = MigrationExecutor(connection)
        with redirect_stdout(io.StringIO()):
            executor.migrate(self.AFTER)
        new_apps = executor.loader.project_state(self.AFTER).apps
        project = new_apps.get_model("scans", "SiteProject").objects.get()
        self.assertEqual(project.origin, "https://a.example")
        self.assertEqual(project.default_scope, "site")
        self.assertFalse(
            new_apps.get_model("scans", "ScanJob").objects.filter(project=None).exists()
        )


class ProjectDashboardDataTests(APITestCase):
    """總覽儀表板、頁面清單與問題詳情的資料。"""

    def setUp(self):
        self.user = _user("dashboard")
        self.client.force_authenticate(self.user)
        self.scan = _scan(self.user, completed_minutes_ago=5, categories=["seo", "security"])
        Page = django_apps.get_model("scans", "Page")
        self.home = Page.objects.create(
            scan_job=self.scan,
            url="https://example.com/",
            final_url="https://example.com/",
            origin="https://example.com",
            status_code=200,
            load_time_ms=420,
            depth=0,
        )
        self.blocked = Page.objects.create(
            scan_job=self.scan,
            url="https://example.com/x",
            final_url="https://example.com/x",
            origin="https://example.com",
            status_code=403,
            depth=1,
            blocked_reason="HTTP 403",
        )
        for severity in ("low", "high"):
            finding = _finding(self.scan, "seo-a", severity=severity)
            finding.page = self.home
            finding.remediation = f"修補 {severity}"
            finding.save()
        _finding(self.scan, "dns-spf-missing", category="security")
        geo = _finding(self.scan, "geo-x", category="geo")
        geo.page = self.home
        geo.save()

    def test_overview_includes_stats_category_counts_and_recent_scans(self):
        data = self.client.get(reverse("site-project-overview", args=[self.scan.project_id])).data
        latest = data["latest_scan"]
        self.assertEqual(latest["stats"]["pages"], 2)
        self.assertEqual(latest["stats"]["pages_blocked"], 1)
        self.assertEqual(latest["stats"]["findings"], 3)  # geo 沒勾，不計
        self.assertEqual(latest["category_counts"], {"seo": 1, "security": 1})
        self.assertEqual([s["id"] for s in data["recent_scans"]], [self.scan.id])

    def test_pages_list_counts_issues_per_page(self):
        data = self.client.get(reverse("site-project-pages", args=[self.scan.project_id])).data
        by_url = {page["url"]: page for page in data["pages"]}
        home = by_url["https://example.com/"]
        self.assertEqual(home["findings"], 2)
        self.assertEqual(home["max_severity"], "high")
        self.assertEqual(home["by_category"], {"seo": 2})
        self.assertEqual(by_url["https://example.com/x"]["blocked_reason"], "HTTP 403")
        self.assertEqual(data["site_level_findings"], 1)

    def test_issue_carries_remediation_and_page_list(self):
        data = self.client.get(reverse("site-project-issues", args=[self.scan.project_id])).data
        issue = next(item for item in data["issues"] if item["key"] == "seo-a")
        self.assertEqual(issue["remediation"], "修補 high")
        self.assertEqual(issue["urls"], ["https://example.com/"])


class ProjectSummaryListTests(APITestCase):
    """所有專案頁的摘要：分數走勢與最新完成掃描的問題數。"""

    def test_score_history_and_issue_counts(self):
        user = _user("summary")
        self.client.force_authenticate(user)
        old = _scan(user, completed_minutes_ago=60, overall_score=50)
        latest = _scan(user, completed_minutes_ago=5, overall_score=70, categories=["seo"])
        _scan(user)  # 進行中的掃描不影響走勢與問題數
        _finding(old, "seo-old", severity="critical")
        for severity in ("low", "high"):
            _finding(latest, "seo-a", severity=severity)
        _finding(latest, "seo-b", severity="info")
        _finding(latest, "dns-spf-missing", category="security", severity="high")
        rows = self.client.get(reverse("site-project-list")).data
        summary = next(row for row in rows if row["id"] == latest.project_id)["summary"]
        self.assertEqual(summary["score_history"], [50, 70])
        # 同規則算一個並取最高嚴重度；info 與未勾維度（security）不算
        self.assertEqual(summary["issue_counts"], {"high": 1})
