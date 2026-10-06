"""優化前後指標（metrics.compare）：只列有變化的項目，方向要正確。"""

from django.test import SimpleTestCase

from apps.rebuild.metrics import compare

BEFORE = """<html><head><title>首頁</title></head><body>
<div><img src="a.png"><img src="b.png"></div>
<input type="text" id="q"><input type="email">
</body></html>"""

AFTER = """<html lang="zh-Hant"><head><title>首頁｜國立臺北商業大學商業智慧研究中心</title>
<meta name="description" content="研究中心簡介"><meta name="viewport" content="width=device-width">
<style>.hero{display:grid}.hero h1{font-size:2.5rem}</style></head><body>
<header></header><main><h1>商業智慧研究中心</h1>
<img src="a.png" alt="研究中心外觀" loading="lazy"><img src="b.png" alt="" loading="lazy">
<label for="q">搜尋</label><input type="text" id="q"><input type="email" aria-label="Email">
</main></body></html>"""


class MetricsTests(SimpleTestCase):
    def test_only_changed_metrics_with_direction(self):
        rows = {r["key"]: r for r in compare(BEFORE, AFTER)}
        self.assertEqual(rows["images_missing_alt"]["before"], 2)
        self.assertEqual(rows["images_missing_alt"]["after"], 0)
        self.assertTrue(rows["images_missing_alt"]["improved"])
        self.assertTrue(rows["unlabeled_fields"]["improved"])
        self.assertTrue(rows["lang"]["improved"])
        self.assertTrue(rows["h1"]["improved"])
        self.assertTrue(rows["title_length"]["improved"])
        self.assertIsNone(rows["css_rules"]["improved"])
        self.assertNotIn("canonical", rows)  # 沒變化不列

    def test_identical_pages_have_no_rows(self):
        self.assertEqual(compare(BEFORE, BEFORE), [])
