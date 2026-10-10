"""Trust Stack 五層信任分（trust_stack.py）：既有訊號聚合，不重新偵測。"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.trust_stack import evaluate, summary_line


class TrustStackTests(SimpleTestCase):
    def _layer(self, result, key):
        return next(x for x in result["layers"] if x["key"] == key)

    def test_no_categories_returns_empty(self):
        self.assertEqual(evaluate(findings_rules=set(), observatory={}, categories=set()), {})

    def test_clean_geo_site_full_scores(self):
        # 沒有任何負面規則 → 各 GEO 層滿分
        r = evaluate(findings_rules=set(), observatory={}, categories={"geo"})
        for key in ("identity", "social", "academic", "consistency"):
            self.assertEqual(self._layer(r, key)["score"], 100)
        # 沒掃資安 → 技術層未評估
        self.assertFalse(self._layer(r, "technical")["evaluated"])
        self.assertEqual(r["overall_score"], 100)

    def test_technical_uses_observatory_score(self):
        r = evaluate(findings_rules=set(), observatory={"score": 55},
                     categories={"security", "geo"})
        tech = self._layer(r, "technical")
        self.assertTrue(tech["evaluated"])
        self.assertEqual(tech["score"], 55)

    def test_academic_penalised_by_citability_rules(self):
        r = evaluate(
            findings_rules={"geo-citability-no-sources", "geo-citability-no-statistics"},
            observatory={}, categories={"geo"},
        )
        # 100 − 45 − 25 = 30
        self.assertEqual(self._layer(r, "academic")["score"], 30)
        self.assertIn("geo-citability-no-sources", self._layer(r, "academic")["reasons"])

    def test_consistency_penalised(self):
        r = evaluate(
            findings_rules={"geo-content-decay", "seo-duplicate-titles"},
            observatory={}, categories={"geo", "seo"},
        )
        self.assertEqual(self._layer(r, "consistency")["score"], 60)  # 100-20-20

    def test_not_tested_layer_excluded_from_overall(self):
        # 只掃資安：GEO 四層未評估，總分只看技術層
        r = evaluate(findings_rules=set(), observatory={"score": 80},
                     categories={"security"})
        self.assertEqual(r["overall_score"], 80)
        self.assertFalse(self._layer(r, "academic")["evaluated"])

    def test_summary_line_mentions_not_scored(self):
        r = evaluate(findings_rules=set(), observatory={"score": 90},
                     categories={"security", "geo"})
        line = summary_line(r)
        self.assertIn("信任輪廓總分", line)
        self.assertIn("不計入 Argus 分數", line)
