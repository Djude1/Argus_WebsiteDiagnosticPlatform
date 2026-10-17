"""外部 JS bundle 秘鑰偵測測試（ADR-0005 §1 第一刀）。

crawler 讀到的 JS body 除了抽端點，另跑秘鑰偵測累積到 state.js_secrets；
tasks._js_secret_findings 按來源檔分組成 finding。
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.scans import tasks
from apps.scans.crawler import _collect_js_secrets

_AWS = "AKIAIOSFODNN7EXAMPLE"  # AWS Access Key ID（canonical 範例）→ critical
_GOOGLE = "AIzaSyA1234567890123456789012345678901"  # Google API Key → 瀏覽器用金鑰、低
_JS = f'var k="{_AWS}"; const g="{_GOOGLE}";'


def _state():
    return SimpleNamespace(js_secrets=[], js_secret_keys=set())


class CollectJsSecretsTests(SimpleTestCase):
    def test_detects_and_tags_source(self):
        state = _state()
        _collect_js_secrets(_JS, "https://site.example.test/app.js", state)
        kinds = {s["kind"] for s in state.js_secrets}
        self.assertIn("aws_access_key", kinds)
        self.assertIn("google_api_key", kinds)
        self.assertTrue(all(s["source"].endswith("/app.js") for s in state.js_secrets))

    def test_dedupes_same_secret_across_files(self):
        state = _state()
        _collect_js_secrets(_JS, "https://site.example.test/a.js", state)
        before = len(state.js_secrets)
        _collect_js_secrets(_JS, "https://site.example.test/b.js", state)  # 同金鑰
        self.assertEqual(len(state.js_secrets), before)  # 不重複累加

    def test_clean_js_adds_nothing(self):
        state = _state()
        _collect_js_secrets("function add(a,b){return a+b;}", "https://x/u.js", state)
        self.assertEqual(state.js_secrets, [])


class JsSecretFindingsTests(SimpleTestCase):
    def _ctx(self, js_secrets):
        return SimpleNamespace(site_signals={"js_secrets": js_secrets})

    def test_builds_secret_and_browser_key_findings(self):
        ctx = self._ctx([
            {"kind": "aws_access_key", "label": "AWS Access Key ID", "severity": "critical",
             "masked": "AKIAIO…", "source": "https://site.example.test/app.js"},
            {"kind": "google_api_key", "label": "Google API Key", "severity": "low",
             "masked": "AIzaSy…", "source": "https://site.example.test/app.js"},
        ])
        findings = tasks._js_secret_findings(ctx)
        rule_ids = {f["rule_id"] for f in findings}
        self.assertIn("exposure-hardcoded-secret", rule_ids)
        self.assertIn("exposure-browser-api-key", rule_ids)
        secret = next(f for f in findings if f["rule_id"] == "exposure-hardcoded-secret")
        self.assertEqual(secret["severity"], "critical")  # AWS key，不含瀏覽器金鑰
        self.assertEqual(secret["evidence_source"], "js_bundle")

    def test_no_js_secrets_no_findings(self):
        self.assertEqual(tasks._js_secret_findings(self._ctx([])), [])
