"""AEO 判定回歸資料集的門檻（aeo/benchmark.py，docs/scan-upgrade-roadmap.md P0-C）。

規則調整後跑這裡；任一指標低於門檻就失敗。要放寬門檻必須有理由並寫進 roadmap，
不可為了讓新規則通過而改標註。
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.scans.aeo.answers import VERDICT_LABELS
from apps.scans.aeo.benchmark import THRESHOLDS, run_benchmark
from apps.scans.aeo.gold_dataset import (
    ALL_CASES,
    HOLDOUT,
    HOLDOUT_CASES,
    NEAR_MISS,
    labelled_count,
)


class GoldDatasetShapeTests(SimpleTestCase):
    def test_dataset_size_and_coverage(self):
        """roadmap P0-C：50–100 組標註，涵蓋四種判定與「語意相近但不是答案」。"""
        self.assertGreaterEqual(labelled_count(), 50)
        expected = {v for case in ALL_CASES for v in case.expected.values()}
        self.assertEqual(expected, set(VERDICT_LABELS))
        self.assertGreaterEqual(
            sum(len(c.expected) for c in ALL_CASES if NEAR_MISS in c.tags), 10
        )
        self.assertTrue(all(HOLDOUT in c.tags for c in HOLDOUT_CASES))

    def test_case_names_are_unique(self):
        names = [case.name for case in ALL_CASES]
        self.assertEqual(len(names), len(set(names)))


class BenchmarkThresholdTests(SimpleTestCase):
    def test_metrics_meet_thresholds(self):
        result = run_benchmark()
        failed = result.failed_thresholds()
        detail = "\n".join(
            f"{j.case}｜{j.key}｜標註 {j.expected}，規則 {j.actual}" for j in result.mismatches
        )
        self.assertFalse(failed, f"{failed}\n不一致：\n{detail}")

    def test_no_false_answer_on_near_miss_cases(self):
        """「語意相近但不是答案」最傷：把非答案當答案，網站主會以為這題沒問題。"""
        near = [j for j in run_benchmark().judgements if NEAR_MISS in j.tags]
        wrong = [j for j in near if j.actual == "answered" and j.expected != "answered"]
        self.assertEqual(wrong, [])

    def test_thresholds_are_the_documented_ones(self):
        self.assertEqual(
            THRESHOLDS,
            {"accuracy": 0.95, "precision": 0.95, "recall": 0.95, "false_positive_rate": 0.05},
        )


class BenchmarkCommandTests(SimpleTestCase):
    def test_command_prints_metrics(self):
        out = StringIO()
        call_command("aeo_benchmark", stdout=out)
        text = out.getvalue()
        self.assertIn("precision", text)
        self.assertIn("false_positive_rate", text)
