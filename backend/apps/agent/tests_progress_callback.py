"""即時進度回呼（2026-10-18）：agent 跑十餘分鐘，過去進度一路停在 0／20 像卡住。

`HermesAgent` 每個 round 開始時呼叫 `step_callback(round_no)`，由 `tasks.stage_agent`
回寫累計步數，讓進度條會動、看得出活著。本檔鎖定「回呼每步會觸發」與「回呼失敗不中斷迴圈」。
"""

from __future__ import annotations

from unittest import mock

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.agent.loop import HermesAgent
from apps.agent.providers import ChatResponse
from apps.agent.runner import max_total_steps_estimate
from apps.scans.models import ScanJob

User = get_user_model()


class _FinishChain:
    """假 provider chain：第一輪就回無工具呼叫的文字收尾，讓 run() 只跑一個 round。"""

    providers: list = []

    def chat_with_tools(self, **kwargs) -> ChatResponse:
        return ChatResponse(provider="fake", model="fake", content="done")


class AgentStepCallbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="agent-cb", password="safe-test-password"
        )
        self.scan = ScanJob.objects.create(
            user=self.user, original_url="https://site.example.test/"
        )

    def _run(self, step_callback):
        agent = HermesAgent(
            scan_job=self.scan,
            executor=mock.Mock(),
            chain=_FinishChain(),
            step_callback=step_callback,
        )
        return async_to_sync(agent.run)("task")

    def test_callback_fires_on_each_round(self):
        seen: list[int] = []
        result = self._run(lambda rnd: seen.append(rnd))
        self.assertEqual(seen[0], 1)  # 第一步就回報，不會整段 0 不動
        self.assertTrue(result.session_id)

    def test_callback_failure_does_not_break_loop(self):
        def _boom(_rnd):
            raise RuntimeError("progress sink down")

        # 回呼爆炸也要照常跑完、拿到結果（fail-safe）
        result = self._run(_boom)
        self.assertTrue(result.session_id)

    def test_no_callback_is_fine(self):
        result = self._run(None)
        self.assertTrue(result.session_id)


class MaxTotalStepsEstimateTests(TestCase):
    def test_estimate_is_positive(self):
        self.assertGreater(max_total_steps_estimate(), 0)

    @override_settings(
        ARGUS_AGENT_MAX_STEPS=20,
        ARGUS_AGENT_MAX_SPECIALIST_DISPATCH=6,
        ARGUS_AGENT_SPECIALIST_MAX_STEPS=30,
    )
    def test_specialist_step_cap_is_env_tunable(self):
        from apps.agent.runner import ux_steps_estimate

        # 每位專家 30 步：20×2 ＋ 6×30 ＝ 220；UX 單一 session 上限同專家步數＝30
        self.assertEqual(max_total_steps_estimate(), 220)
        self.assertEqual(ux_steps_estimate(), 30)

    @override_settings(ARGUS_AGENT_SPECIALIST_MAX_STEPS=60, ARGUS_AGENT_MAX_SPECIALIST_DISPATCH=6)
    def test_larger_cap_raises_estimate(self):
        self.assertEqual(max_total_steps_estimate(), 40 + 6 * 60)


class _RecordingChain:
    """記下送進模型的 messages，驗證 task_prompt 確實傳達給模型。"""

    providers: list = []

    def __init__(self):
        self.seen_messages = None

    def chat_with_tools(self, **kwargs) -> ChatResponse:
        self.seen_messages = kwargs.get("messages")
        return ChatResponse(provider="fake", model="fake", content="done")


class AgentLanguageRuleTests(TestCase):
    """一律繁中回報（2026-10-18）：_LANGUAGE_RULE 會接在每個 session 的 task_prompt 尾端。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="agent-lang", password="safe-test-password"
        )
        self.scan = ScanJob.objects.create(
            user=self.user, original_url="https://site.example.test/"
        )

    def test_language_rule_mandates_traditional_chinese(self):
        from apps.agent.runner import _LANGUAGE_RULE

        self.assertIn("繁體中文", _LANGUAGE_RULE)
        self.assertIn("report_security_issue", _LANGUAGE_RULE)

    def test_task_prompt_reaches_model_messages(self):
        # HermesAgent.run 把 task_prompt（_run_session 會在尾端接上 _LANGUAGE_RULE）放進第一個
        # user message → 模型一定看得到這條語言鐵律
        from apps.agent.runner import _LANGUAGE_RULE

        chain = _RecordingChain()
        agent = HermesAgent(scan_job=self.scan, executor=mock.Mock(), chain=chain)
        async_to_sync(agent.run)("role prompt" + _LANGUAGE_RULE)
        joined = " ".join(m.get("content", "") for m in (chain.seen_messages or []))
        self.assertIn("繁體中文", joined)
