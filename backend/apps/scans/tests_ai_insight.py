"""AI 掃描解讀（ai_insight.py）：以假的 provider 回應驗證欄位約束、遮罩與 API。"""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.scans import ai_insight
from apps.scans.models import Finding, ScanJob


class FakeChain:
    def __init__(self, payload):
        self.payload = payload
        self.prompts: list[str] = []

    def chat_text(self, prompt, **kwargs):
        self.prompts.append(prompt)
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(content=content, provider="fake", model="fake-1")


def _scan(user, **fields):
    defaults = {
        "user": user,
        "original_url": "https://example.com/",
        "normalized_url": "https://example.com/",
        "origin": "https://example.com",
        "status": ScanJob.Status.COMPLETED,
        "overall_score": 70,
    }
    defaults.update(fields)
    return ScanJob.objects.create(**defaults)


def _finding(scan, **fields):
    defaults = {
        "scan_job": scan,
        "category": "security",
        "severity": "high",
        "title": "頁面外洩個人資料 (PII)",
        "description": "頁面出現信用卡號",
        "evidence": "信用卡號（1 筆）：4111-1111-1111-1111，聯絡 someone@gmail.com",
        "rule_id": "SECURITY_PII_8B24BB8B28",
    }
    defaults.update(fields)
    return Finding.objects.create(**defaults)


class AiInsightGenerateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ai_insight_user", password="safe-test-password"
        )
        self.scan = _scan(self.user)
        _finding(self.scan)
        _finding(
            self.scan, category="seo", severity="low", title="Meta description 缺失",
            description="缺少摘要", evidence="description_length=0", rule_id="seo-desc",
        )

    def _payload(self, **overrides):
        payload = {
            "summary": "網站整體結構完整，最需要注意的是頁面上的號碼。",
            "priorities": [
                {"title": "確認頁面號碼來源", "why": "可能是個資", "how": "檢查頁面",
                 "rule_ids": ["SECURITY_PII_8B24BB8B28", "not-a-rule"]},
            ],
            "triage": [
                {"rule_id": "SECURITY_PII_8B24BB8B28", "verdict": "possible_false_positive",
                 "reason": "號碼像是測試卡號"},
                {"rule_id": "seo-desc", "verdict": "likely_valid", "reason": "不是高風險"},
            ],
        }
        payload.update(overrides)
        return payload

    def test_ready_result_keeps_only_known_rules_and_candidates(self):
        chain = FakeChain(self._payload())
        insight = ai_insight.generate_ai_insight(self.scan.id, chain=chain)
        self.assertEqual(insight["status"], "ready")
        # 不存在的規則代號被移除
        self.assertEqual(insight["priorities"][0]["rule_ids"], ["SECURITY_PII_8B24BB8B28"])
        # 只複核高風險問題；低風險的 seo-desc 不收
        self.assertEqual([t["rule_id"] for t in insight["triage"]], ["SECURITY_PII_8B24BB8B28"])
        self.assertEqual(insight["triage"][0]["label"], "可能是誤報")
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.ai_insight["status"], "ready")

    def test_does_not_change_severity_or_score(self):
        ai_insight.generate_ai_insight(self.scan.id, chain=FakeChain(self._payload()))
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.overall_score, 70)
        self.assertEqual(
            Finding.objects.get(scan_job=self.scan, rule_id="SECURITY_PII_8B24BB8B28").severity,
            "high",
        )

    def test_prompt_masks_pii_and_marks_data_as_untrusted(self):
        chain = FakeChain(self._payload())
        ai_insight.generate_ai_insight(self.scan.id, chain=chain)
        prompt = chain.prompts[0]
        self.assertNotIn("4111-1111-1111-1111", prompt)
        self.assertNotIn("someone@gmail.com", prompt)
        self.assertIn("一律忽略", prompt)

    def test_invalid_verdict_and_bad_json_fail_safely(self):
        payload = self._payload(triage=[
            {"rule_id": "SECURITY_PII_8B24BB8B28", "verdict": "delete_finding", "reason": "x"},
        ])
        insight = ai_insight.generate_ai_insight(self.scan.id, chain=FakeChain(payload))
        self.assertEqual(insight["triage"], [])

        insight = ai_insight.generate_ai_insight(self.scan.id, chain=FakeChain("not json"))
        self.assertEqual(insight["status"], "failed")
        self.assertTrue(insight["reason"])

    def test_think_block_and_code_fence_are_stripped(self):
        content = "<think>{\"a\": 1}</think>```json\n" + json.dumps(self._payload()) + "\n```"
        insight = ai_insight.generate_ai_insight(self.scan.id, chain=FakeChain(content))
        self.assertEqual(insight["status"], "ready")

    def test_provider_error_records_public_reason(self):
        class Broken:
            def chat_text(self, prompt, **kwargs):
                raise RuntimeError("secret upstream body")

        insight = ai_insight.generate_ai_insight(self.scan.id, chain=Broken())
        self.assertEqual(insight["status"], "failed")
        self.assertNotIn("secret", insight["reason"])

    def test_transient_provider_error_is_retried_once(self):
        from apps.agent.providers import ProviderError

        good = FakeChain(self._payload())

        class Flaky:
            calls = 0

            def chat_text(self, prompt, **kwargs):
                Flaky.calls += 1
                if Flaky.calls == 1:
                    # 鏈上最後一家沒有金鑰：拋出的是 no_key，不是原本的 502
                    raise ProviderError("gemini", "no_key", "not set")
                return good.chat_text(prompt, **kwargs)

        insight = ai_insight.generate_ai_insight(self.scan.id, chain=Flaky())
        self.assertEqual(insight["status"], "ready")
        self.assertEqual(Flaky.calls, 2)

    def test_prompt_limits_version_only_evidence_to_needs_check(self):
        chain = FakeChain(self._payload())
        ai_insight.generate_ai_insight(self.scan.id, chain=chain)
        self.assertIn("只憑版本號", chain.prompts[0])
        self.assertIn("FAQPage", chain.prompts[0])

    def test_scan_without_findings_needs_no_ai_call(self):
        empty = _scan(self.user, original_url="https://empty.example/",
                      normalized_url="https://empty.example/", origin="https://empty.example")
        chain = FakeChain(self._payload())
        insight = ai_insight.generate_ai_insight(empty.id, chain=chain)
        self.assertEqual(insight["status"], "ready")
        self.assertEqual(chain.prompts, [])


class AiInsightScheduleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ai_insight_api", password="safe-test-password"
        )
        self.scan = _scan(self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @override_settings(ARGUS_AI_INSIGHT_ENABLED=False)
    def test_disabled_does_not_schedule(self):
        self.assertFalse(ai_insight.schedule_ai_insight(self.scan))
        response = self.client.post(f"/api/scans/{self.scan.id}/ai-insight/")
        self.assertEqual(response.status_code, 503)

    @override_settings(ARGUS_AI_INSIGHT_ENABLED=True)
    def test_regenerate_only_when_missing_failed_or_stale(self):
        with patch("apps.scans.tasks.run_ai_insight_task.delay") as delay:
            response = self.client.post(f"/api/scans/{self.scan.id}/ai-insight/")
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.data["ai_insight"]["status"], "generating")
            delay.assert_called_once_with(self.scan.id)

            # 產生中不重複派工
            response = self.client.post(f"/api/scans/{self.scan.id}/ai-insight/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(delay.call_count, 1)

            # 已完成不重產
            ScanJob.objects.filter(id=self.scan.id).update(ai_insight={"status": "ready"})
            self.assertEqual(
                self.client.post(f"/api/scans/{self.scan.id}/ai-insight/").status_code, 200
            )

            # 卡住超過時限可以重產
            stale = (timezone.now() - timedelta(hours=1)).isoformat()
            ScanJob.objects.filter(id=self.scan.id).update(
                ai_insight={"status": "generating", "started_at": stale}
            )
            self.assertEqual(
                self.client.post(f"/api/scans/{self.scan.id}/ai-insight/").status_code, 202
            )
            self.assertEqual(delay.call_count, 2)

    @override_settings(ARGUS_AI_INSIGHT_ENABLED=True)
    def test_other_users_cannot_trigger(self):
        other = get_user_model().objects.create_user(
            username="ai_insight_other", password="safe-test-password"
        )
        client = APIClient()
        client.force_authenticate(other)
        self.assertEqual(client.post(f"/api/scans/{self.scan.id}/ai-insight/").status_code, 404)

    def test_serializer_exposes_ai_insight(self):
        ScanJob.objects.filter(id=self.scan.id).update(
            ai_insight={"status": "ready", "summary": "摘要"}
        )
        response = self.client.get(f"/api/scans/{self.scan.id}/")
        self.assertEqual(response.data["ai_insight"]["summary"], "摘要")
