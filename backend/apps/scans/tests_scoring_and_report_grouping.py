"""分數計算、finding 排序與報告分組的回歸測試。

背景（見 docs/scan-report-quality-audit-2026-08-30.md）：
scan 25 的報告出現「SECURITY：0 分」「低風險項目排在高風險前面」「同一個問題
在報告裡列 4 次」等問題，根因都在這三個函式：

- scanners.py::calculate_scores() —— 同問題跨頁重複扣分、info 也扣分、
  未評估分類仍回傳 100、top_actions 沒去重。
- scanners.py::make_finding() —— 未指定 priority_score 時留 None，
  PostgreSQL 的 DESC NULLS FIRST 把這些 finding 頂到最前面。
- reports.py::_group_findings_for_report() —— 用 (rule_id, evidence) 當合併鍵，
  evidence 含頁面專屬內容，導致同問題跨頁合併失敗。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scans.models import Finding, Page, ScanJob
from apps.scans.reports import _group_findings_for_report
from apps.scans.scanners import calculate_scores, make_finding

User = get_user_model()


def _finding(category: str, severity: str, rule_id: str, title: str = "") -> dict:
    return {
        "category": category,
        "severity": severity,
        "rule_id": rule_id,
        "title": title or rule_id,
        "priority_score": 50.0,
    }


class CalculateScoresTests(TestCase):
    def test_same_rule_across_pages_is_penalised_once(self):
        """同一個問題出現在 3 頁只該扣一次分。

        scan 25 的 PII finding 出現在 3 個頁面，被扣 25×3=75 分，
        單這一項就吃掉 SECURITY 的大半分數，但報告只顯示一項。
        """
        once = calculate_scores(
            [_finding("security", "high", "PII")],
            tested_categories={"security"},
        )[1]["security"]
        thrice = calculate_scores(
            [_finding("security", "high", "PII")] * 3,
            tested_categories={"security"},
        )[1]["security"]

        self.assertEqual(once, thrice)

    def test_different_rules_still_accumulate(self):
        """去重只針對同一個 rule_id；不同問題仍必須各自扣分。"""
        one = calculate_scores(
            [_finding("security", "high", "A")],
            tested_categories={"security"},
        )[1]["security"]
        two = calculate_scores(
            [_finding("security", "high", "A"), _finding("security", "high", "B")],
            tested_categories={"security"},
        )[1]["security"]

        self.assertLess(two, one)

    def test_info_severity_does_not_deduct(self):
        """info 常是正向或純資訊（例如「偵測到 WAF 保護」），不該倒扣。"""
        _, category_scores, _ = calculate_scores(
            [_finding("security", "info", "WAF_DETECTED")],
            tested_categories={"security"},
        )

        self.assertEqual(category_scores["security"], 100)

    def test_untested_category_is_absent_not_full_marks(self):
        """未評估的分類不寫進 category_scores。

        缺鍵代表「未評估」。舊行為回傳 ux=100，報告直接印「UX：100」，
        使用者會解讀成「UX 完美」，實際上 Agent 預設停用、根本沒測。
        """
        _, category_scores, _ = calculate_scores([], tested_categories={"security", "seo"})

        self.assertEqual(set(category_scores), {"security", "seo"})
        self.assertNotIn("ux", category_scores)

    def test_overall_is_average_of_exactly_the_reported_categories(self):
        """摘要列出的分數必須能算出整體分數。

        舊行為顯示 5 個分類但只平均 4 個，使用者怎麼算都對不上 39。
        """
        overall, category_scores, _ = calculate_scores(
            [_finding("security", "high", "A"), _finding("seo", "low", "B")],
            tested_categories={"security", "seo", "geo"},
        )

        expected = round(sum(category_scores.values()) / len(category_scores))
        self.assertEqual(overall, expected)

    def test_many_problems_do_not_collapse_to_zero(self):
        """分數必須保有解析度：問題再多也要能分出「很糟」與「更糟」。

        舊的 max(0, 100-penalty) 在累積 100 分懲罰後就永遠是 0，
        4 個高風險和 40 個高風險看起來一樣。
        """
        ten = calculate_scores(
            [_finding("security", "high", f"R{i}") for i in range(10)],
            tested_categories={"security"},
        )[1]["security"]
        thirty = calculate_scores(
            [_finding("security", "high", f"R{i}") for i in range(30)],
            tested_categories={"security"},
        )[1]["security"]

        self.assertGreater(ten, 0)
        self.assertLess(thirty, ten)

    def test_top_actions_are_deduplicated(self):
        """優先改善建議 5 個名額不該被同一個問題佔滿。

        scan 25 的 top_actions 是「PII×3 + JS渲染×2」，5 個名額只講了 2 件事。
        """
        findings = [_finding("security", "high", "PII")] * 3 + [
            _finding("geo", "medium", "JS_RENDER")
        ] * 2
        _, _, top_actions = calculate_scores(findings, tested_categories={"security", "geo"})

        titles = [a["title"] for a in top_actions]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(set(titles), {"PII", "JS_RENDER"})


class MakeFindingPriorityScoreTests(TestCase):
    def test_priority_score_defaults_from_severity(self):
        """未指定 priority_score 時依 severity 給預設，不留 None。

        security/ 子套件的 7 個 scanner 都沒傳 priority_score，留 None 會讓
        PostgreSQL 的 DESC NULLS FIRST 把它們排到報告最前面（見 FindingOrderingTests）。
        """
        for severity in ("critical", "high", "medium", "low", "info"):
            with self.subTest(severity=severity):
                finding = make_finding(
                    category="security",
                    severity=severity,
                    title="t",
                    description="d",
                    remediation="r",
                )
                self.assertIsNotNone(finding["priority_score"])

    def test_default_priority_is_ordered_by_severity(self):
        def score(severity: str) -> float:
            return make_finding(
                category="security", severity=severity,
                title="t", description="d", remediation="r",
            )["priority_score"]

        self.assertGreater(score("critical"), score("high"))
        self.assertGreater(score("high"), score("medium"))
        self.assertGreater(score("medium"), score("low"))
        self.assertGreater(score("low"), score("info"))

    def test_explicit_priority_score_is_not_overridden(self):
        finding = make_finding(
            category="seo", severity="low", title="t", description="d",
            remediation="r", priority_score=15,
        )

        self.assertEqual(finding["priority_score"], 15)


class FindingOrderingTests(TestCase):
    """鎖定 Finding.Meta.ordering。

    這組測試在 SQLite 下即使沒修也會通過（SQLite 的 DESC 天然 NULLS LAST），
    真正的驗證必須跑在 PostgreSQL 上。保留在這裡是為了鎖住「明確指定
    nulls_last / 嚴重度排序」這個契約，避免日後被改回隱含行為。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="ordering", password="safe-test-password")
        self.scan_job = ScanJob.objects.create(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
        )

    def _make(self, title: str, severity: str, priority: float | None) -> Finding:
        return Finding.objects.create(
            scan_job=self.scan_job, page=None, severity=severity,
            category=Finding.Category.SECURITY, title=title,
            description="d", remediation="r", ai_handoff_prompt="p",
            priority_score=priority,
        )

    def test_null_priority_sorts_last(self):
        self._make("null", "high", None)
        self._make("scored", "low", 25.0)

        titles = list(
            Finding.objects.filter(scan_job=self.scan_job).values_list("title", flat=True)
        )
        self.assertEqual(titles, ["scored", "null"])

    def test_severity_tiebreak_follows_risk_not_alphabet(self):
        """同 priority_score 時，info 不該排在 low / medium 前面。

        severity 是 CharField，字母序是 critical < high < info < low < medium。
        """
        self._make("info", "info", 50.0)
        self._make("medium", "medium", 50.0)
        self._make("critical", "critical", 50.0)

        titles = list(
            Finding.objects.filter(scan_job=self.scan_job).values_list("title", flat=True)
        )
        self.assertEqual(titles, ["critical", "medium", "info"])


class GroupFindingsForReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="grouping", password="safe-test-password")
        self.scan_job = ScanJob.objects.create(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
        )

    def _page(self, path: str) -> Page:
        return Page.objects.create(
            scan_job=self.scan_job, url=f"https://example.com{path}",
            final_url=f"https://example.com{path}", origin="https://example.com",
        )

    def _finding(self, page, rule_id: str, evidence: str) -> Finding:
        return Finding.objects.create(
            scan_job=self.scan_job, page=page, severity="medium",
            category=Finding.Category.SEO, title="Meta title 長度不理想",
            description="d", remediation="r", ai_handoff_prompt="p",
            rule_id=rule_id, evidence=evidence, priority_score=50.0,
        )

    def test_same_rule_merges_even_when_evidence_differs_per_page(self):
        """evidence 含頁面專屬內容，不能當合併鍵。

        scan 25 的報告因此把「Meta title 長度不理想」列了 4 次。
        """
        findings = [
            self._finding(self._page(f"/p{i}"), "SEO_META_TITLE_AAA", f"該頁 title：第 {i} 頁")
            for i in range(3)
        ]

        groups = _group_findings_for_report(findings)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["pages"]), 3)

    def test_different_rules_stay_separate(self):
        findings = [
            self._finding(self._page("/a"), "SEO_META_TITLE_AAA", "e1"),
            self._finding(self._page("/b"), "SEO_META_DESC_BBB", "e2"),
        ]

        self.assertEqual(len(_group_findings_for_report(findings)), 2)

    def test_findings_without_rule_id_are_not_merged_together(self):
        """rule_id 為空的 finding 是不同問題，不能因為同樣「沒有 rule_id」就合併。"""
        findings = [
            self._finding(self._page("/a"), "", "e1"),
            self._finding(self._page("/b"), "", "e2"),
        ]

        self.assertEqual(len(_group_findings_for_report(findings)), 2)
