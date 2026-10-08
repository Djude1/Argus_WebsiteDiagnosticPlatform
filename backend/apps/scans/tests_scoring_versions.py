"""評分與規則版本（versions.py，docs/scan-upgrade-roadmap.md P1 comparable history）。

版本不同的兩次掃描，分數差不能被說成「網站進步／退步」。
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.scans import versions
from apps.scans.models import ScanJob
from apps.scans.projects import project_overview, project_summaries
from apps.scans.reports import _headline

CURRENT = {"scoring_version": versions.SCORING_VERSION, "ruleset_version": versions.RULESET_VERSION}
OLD_RULES = {"scoring_version": versions.SCORING_VERSION, "ruleset_version": "2026.01.01"}


class ComparableTests(SimpleTestCase):
    def test_same_versions_are_comparable(self):
        self.assertTrue(versions.comparable(ScanJob(**CURRENT), ScanJob(**CURRENT)))

    def test_different_ruleset_is_not_comparable(self):
        self.assertFalse(versions.comparable(ScanJob(**CURRENT), ScanJob(**OLD_RULES)))

    def test_legacy_scan_without_versions_is_not_comparable(self):
        self.assertFalse(versions.comparable(ScanJob(), ScanJob()))
        self.assertEqual(versions.label(ScanJob()), "版本不明（舊掃描）")

    def test_label(self):
        self.assertEqual(
            versions.label(ScanJob(**CURRENT)),
            f"計分 v{versions.SCORING_VERSION}／規則 {versions.RULESET_VERSION}",
        )


def _completed(user, minutes_ago, score, **fields):
    scan = ScanJob.objects.create(
        user=user, original_url="https://example.com/", normalized_url="https://example.com/",
        origin="https://example.com", status=ScanJob.Status.COMPLETED, overall_score=score,
        **fields,
    )
    done = timezone.now() - timedelta(minutes=minutes_ago)
    ScanJob.objects.filter(id=scan.id).update(created_at=done, completed_at=done)
    scan.refresh_from_db()
    return scan


class ProjectComparisonTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="versions", password="safe-test-password"
        )

    def test_overview_flags_incomparable_scores_and_marks_trend(self):
        _completed(self.user, 60, 60, **OLD_RULES)
        latest = _completed(self.user, 10, 80, **CURRENT)

        data = project_overview(latest.project)

        self.assertFalse(data["score_comparable"])
        self.assertEqual([p["model_changed"] for p in data["trend"]], [False, True])

    def test_same_versions_are_comparable_in_overview_and_summaries(self):
        _completed(self.user, 60, 60, **CURRENT)
        latest = _completed(self.user, 10, 80, **CURRENT)

        self.assertTrue(project_overview(latest.project)["score_comparable"])
        summary = project_summaries([latest.project_id])[latest.project_id]
        self.assertTrue(summary["score_comparable"])
        self.assertEqual((summary["previous_score"], summary["latest_score"]), (60, 80))

    def test_summaries_flag_incomparable(self):
        _completed(self.user, 60, 60)
        latest = _completed(self.user, 10, 80, **CURRENT)
        summary = project_summaries([latest.project_id])[latest.project_id]
        self.assertFalse(summary["score_comparable"])


class ReportHeadlineTests(SimpleTestCase):
    def test_incomparable_scores_are_not_called_progress(self):
        text = _headline(
            ScanJob(overall_score=80, **CURRENT), ScanJob(overall_score=60, **OLD_RULES), {}
        )
        self.assertIn("評分規則與前次不同，分數不宜直接比較", text)
        self.assertNotIn("進步", text)

    def test_comparable_scores_report_delta(self):
        text = _headline(
            ScanJob(overall_score=80, **CURRENT), ScanJob(overall_score=60, **CURRENT), {}
        )
        self.assertIn("較前次進步 20 分", text)
