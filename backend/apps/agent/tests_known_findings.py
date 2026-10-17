"""ADR-0005 §5：orchestrator 吃確定性發現、不重報（_summarize_known_findings）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.agent.runner import ORCHESTRATOR_PROMPT, _summarize_known_findings


class SummarizeKnownFindingsTests(SimpleTestCase):
    def test_security_only_with_endpoint_and_severity(self):
        known = [
            {"category": "security", "severity": "high", "title": "API 文件外洩",
             "rule_id": "exposure-file-apidoc", "evidence_json": {"endpoint": "/svc/v3/api-docs"}},
            {"category": "seo", "severity": "low", "title": "缺 canonical", "rule_id": "seo-x"},
        ]
        out = _summarize_known_findings(known)
        self.assertIn("API 文件外洩", out)
        self.assertIn("/svc/v3/api-docs", out)
        self.assertIn("[high]", out)
        self.assertNotIn("canonical", out)  # 非資安不列

    def test_dedupe_by_rule_id(self):
        known = [
            {"category": "security", "severity": "high", "title": "a", "rule_id": "r1"},
            {"category": "security", "severity": "medium", "title": "a 換句話說", "rule_id": "r1"},
        ]
        self.assertEqual(_summarize_known_findings(known).count("\n"), 0)  # 一行

    def test_empty(self):
        self.assertEqual(_summarize_known_findings([]), "（無）")
        self.assertEqual(_summarize_known_findings(None), "（無）")

    def test_no_evidence_leaked(self):
        # 只送標題/端點/嚴重度，不送 evidence 片段
        known = [{"category": "security", "severity": "critical", "title": "秘鑰外洩",
                  "rule_id": "exposure-hardcoded-secret", "evidence": "AKIA...SECRET...",
                  "evidence_json": {"excerpt": "super-secret-value"}}]
        out = _summarize_known_findings(known)
        self.assertNotIn("super-secret-value", out)
        self.assertNotIn("AKIA", out)


class OrchestratorPromptFormatTests(SimpleTestCase):
    def test_prompt_accepts_deterministic_findings_placeholder(self):
        # 回歸：ORCHESTRATOR_PROMPT 新增 {deterministic_findings}，format 不可缺鍵
        prompt = ORCHESTRATOR_PROMPT.format(
            origin="https://site.example.test",
            recon_summary="（無）",
            findings_list="（無）",
            deterministic_findings="- [high] API 文件外洩（/svc/v3/api-docs）",
            endpoints="（無）",
            roles_desc="- auth_idor: ...",
        )
        self.assertIn("不要重報", prompt)
        self.assertIn("API 文件外洩", prompt)
