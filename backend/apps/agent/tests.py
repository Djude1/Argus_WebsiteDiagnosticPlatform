"""Hermes-Agent 單元測試。

覆蓋面：
- providers：ProviderError、ProviderChain fallback、不可重試錯誤直接拋出。
- tools：TOOL_SCHEMAS 結構、ToolExecutor 對 mock page 的行為。
- loop：迴圈 finish、max_steps、max_tokens、多 tool_calls 分攤 token。
- findings：persist_agent_issues 寫入、去重、URL → Page 對應。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings

from apps.agent.findings import persist_agent_issues, persist_agent_security_findings
from apps.agent.loop import HermesAgent
from apps.agent.providers import (
    ChatProvider,
    ChatResponse,
    ProviderChain,
    ProviderError,
    ToolCall,
)
from apps.agent.runner import (
    _enforce_agent_request,
    _enforce_agent_websocket,
    _make_agent_context,
)
from apps.agent.tools import (
    TOOL_SCHEMAS,
    ToolExecutor,
    ToolOutcome,
    build_tool_schemas,
    redact_tool_arguments,
    redact_tool_result,
)
from apps.scans.models import AgentSession, AgentStep, Finding, Page, ScanJob
from apps.scans.services import PublicScanTargetError

User = get_user_model()


# ---------------- helpers ----------------


def _make_scan_job(user) -> ScanJob:
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
    )


class AgentBrowserBoundaryTests(TestCase):
    def test_context_blocks_service_workers_and_registers_both_routes(self):
        context = MagicMock()
        context.route = AsyncMock()
        context.route_web_socket = AsyncMock()
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)

        created = asyncio.run(_make_agent_context(browser, "https://example.com"))

        self.assertIs(created, context)
        browser.new_context.assert_awaited_once()
        self.assertEqual(
            browser.new_context.await_args.kwargs["service_workers"],
            "block",
        )
        context.route.assert_awaited_once()
        context.route_web_socket.assert_awaited_once()

    def test_request_policy_blocks_private_and_cross_origin_document(self):
        private_route = MagicMock()
        private_route.abort = AsyncMock()
        private_route.continue_ = AsyncMock()
        private_request = MagicMock(url="http://127.0.0.1/", resource_type="image")
        with patch(
            "apps.agent.runner.assert_public_http_url",
            side_effect=PublicScanTargetError("blocked"),
        ):
            asyncio.run(
                _enforce_agent_request(private_route, private_request, "https://example.com")
            )
        private_route.abort.assert_awaited_once_with("blockedbyclient")
        private_route.continue_.assert_not_awaited()

        cross_route = MagicMock()
        cross_route.abort = AsyncMock()
        cross_route.continue_ = AsyncMock()
        cross_request = MagicMock(
            url="https://other.example/page", resource_type="document"
        )
        with patch(
            "apps.agent.runner.assert_public_http_url",
            return_value="https://other.example/page",
        ):
            asyncio.run(
                _enforce_agent_request(cross_route, cross_request, "https://example.com")
            )
        cross_route.abort.assert_awaited_once_with("blockedbyclient")
        cross_route.continue_.assert_not_awaited()

    def test_request_policy_allows_public_subresource_and_same_origin_document(self):
        for url, resource_type in (
            ("https://cdn.example.net/app.js", "script"),
            ("https://example.com/next", "document"),
        ):
            route = MagicMock()
            route.abort = AsyncMock()
            route.continue_ = AsyncMock()
            request = MagicMock(url=url, resource_type=resource_type)
            with patch("apps.agent.runner.assert_public_http_url", return_value=url):
                asyncio.run(
                    _enforce_agent_request(route, request, "https://example.com")
                )
            route.continue_.assert_awaited_once()
            route.abort.assert_not_awaited()

    def test_websocket_policy_blocks_cross_origin(self):
        websocket_route = MagicMock(url="wss://other.example/socket")
        websocket_route.close = AsyncMock()
        with patch(
            "apps.agent.runner.assert_public_websocket_url",
            return_value="wss://other.example/socket",
        ):
            asyncio.run(
                _enforce_agent_websocket(websocket_route, "https://example.com")
            )
        websocket_route.close.assert_awaited_once()
        websocket_route.connect_to_server.assert_not_called()


class FakeProvider(ChatProvider):
    name = "fake"
    default_model = "fake-model"
    supports_tools = True

    def __init__(self, responses, available: bool = True):
        self._responses = list(responses)
        self._available = available
        self.calls = 0

    @property
    def available(self) -> bool:
        return self._available

    def chat_with_tools(self, **kwargs) -> ChatResponse:  # type: ignore[override]
        self.calls += 1
        next_item = self._responses.pop(0)
        if isinstance(next_item, ProviderError):
            raise next_item
        return next_item


def _chat_response_finish(content: str = "done") -> ChatResponse:
    return ChatResponse(
        provider="fake",
        model="fake-model",
        content=content,
        tool_calls=[],
        total_tokens=10,
        finish_reason="stop",
    )


def _chat_response_tool(
    tool_name: str, args: dict[str, Any], total_tokens: int = 5
) -> ChatResponse:
    return ChatResponse(
        provider="fake",
        model="fake-model",
        content="",
        tool_calls=[ToolCall(id=f"call_{tool_name}", name=tool_name, arguments=args)],
        total_tokens=total_tokens,
        finish_reason="tool_calls",
    )


class FakeExecutor:
    """模擬 ToolExecutor，不真的開瀏覽器。"""

    def __init__(self, outcomes: dict[str, ToolOutcome] | None = None):
        self._outcomes = outcomes or {}
        self.calls: list[tuple[str, dict]] = []

    async def run(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        self.calls.append((name, args))
        if name in self._outcomes:
            return self._outcomes[name]
        if name == "finish":
            return ToolOutcome(ok=True, result={"summary": args.get("summary", "")}, finish=True)
        return ToolOutcome(ok=True, result={"ran": name})


# ---------------- providers ----------------


class ProviderChainTests(TestCase):
    def test_fallback_on_429(self):
        p1 = FakeProvider([ProviderError("fake", 429, "rate")])
        p2 = FakeProvider([_chat_response_finish("ok")])
        chain = ProviderChain(providers=[p1, p2])
        resp = chain.chat_with_tools(messages=[{"role": "user", "content": "hi"}], tools=[{}])
        self.assertEqual(p1.calls, 1)
        self.assertEqual(p2.calls, 1)
        self.assertEqual(resp.content, "ok")

    def test_non_retryable_raises_immediately(self):
        p1 = FakeProvider([ProviderError("fake", 400, "bad_prompt")])
        p2 = FakeProvider([_chat_response_finish("never")])
        chain = ProviderChain(providers=[p1, p2])
        with self.assertRaises(ProviderError) as cm:
            chain.chat_with_tools(messages=[], tools=[{}])
        self.assertEqual(cm.exception.http_status, 400)
        self.assertEqual(p2.calls, 0)

    def test_skip_provider_without_tool_support(self):
        no_tool = FakeProvider([_chat_response_finish("nope")])
        no_tool.supports_tools = False
        with_tool = FakeProvider([_chat_response_finish("ok")])
        chain = ProviderChain(providers=[no_tool, with_tool])
        resp = chain.chat_with_tools(messages=[], tools=[{"x": 1}])
        self.assertEqual(no_tool.calls, 0)
        self.assertEqual(with_tool.calls, 1)
        self.assertEqual(resp.content, "ok")

    def test_empty_chain_raises(self):
        chain = ProviderChain(providers=[])
        with self.assertRaises(ProviderError):
            chain.chat_with_tools(messages=[], tools=None)


# ---------------- tools ----------------


class ToolSchemaTests(TestCase):
    def test_schema_has_all_required_tools(self):
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        expected = {
            "click",
            "type_text",
            "scroll",
            "get_visible_text",
            "get_dom_summary",
            "take_screenshot",
            "report_ux_issue",
            "probe_sql_injection",
            "finish",
        }
        self.assertEqual(names, expected)

    def test_report_ux_issue_required_fields(self):
        report = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "report_ux_issue")
        required = report["function"]["parameters"]["required"]
        for field in ("severity", "title", "description"):
            self.assertIn(field, required)

    def test_passive_schema_omits_sqlmap_tool(self):
        names = {item["function"]["name"] for item in build_tool_schemas(False)}
        self.assertNotIn("probe_sql_injection", names)

    def test_authorized_active_schema_includes_sqlmap_tool(self):
        names = {item["function"]["name"] for item in build_tool_schemas(True)}
        self.assertIn("probe_sql_injection", names)

    def test_build_tool_schemas_returns_deep_copy(self):
        """build_tool_schemas 必須回傳獨立深拷貝，避免共用 mutable schema 被意外修改。"""
        schemas = build_tool_schemas(True)
        original = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "click")
        copy_item = next(s for s in schemas if s["function"]["name"] == "click")
        copy_item["function"]["name"] = "mutated"
        self.assertNotEqual(original["function"]["name"], "mutated")


class ToolExecutorTests(TestCase):
    def _make_executor(self):
        page = MagicMock()
        page.url = "https://example.com/test"
        page.locator = MagicMock()
        page.evaluate = AsyncMock(return_value="hello")
        page.screenshot = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        return ToolExecutor(page=page, screenshot_dir="/tmp/agent", action_timeout_ms=1000), page

    def test_unknown_tool_returns_error(self):
        executor, _ = self._make_executor()
        outcome = asyncio.run(executor.run("nope", {}))
        self.assertFalse(outcome.ok)
        self.assertIn("unknown_tool", outcome.result["error"])

    def test_report_ux_issue_returns_issue_payload(self):
        executor, page = self._make_executor()
        outcome = asyncio.run(
            executor.run(
                "report_ux_issue",
                {
                    "severity": "high",
                    "title": "結帳按鈕點不到",
                    "description": "點擊結帳沒有任何反應，console 無錯誤。",
                    "remediation": "確認 onClick handler 是否綁定。",
                    "selector": ".checkout-btn",
                },
            )
        )
        self.assertTrue(outcome.ok)
        self.assertIsNotNone(outcome.issue)
        self.assertEqual(outcome.issue["severity"], "high")
        self.assertEqual(outcome.issue["selector"], ".checkout-btn")
        self.assertEqual(outcome.issue["url"], "https://example.com/test")

    def test_report_ux_issue_rejects_missing_title(self):
        executor, _ = self._make_executor()
        outcome = asyncio.run(
            executor.run(
                "report_ux_issue",
                {"severity": "low", "title": "", "description": "x"},
            )
        )
        self.assertFalse(outcome.ok)

    def test_finish_marks_finish_flag(self):
        executor, _ = self._make_executor()
        outcome = asyncio.run(executor.run("finish", {"summary": "ok"}))
        self.assertTrue(outcome.finish)


class RedactToolDataTests(TestCase):
    """Step 5：probe_sql_injection 的 arguments 與 result 必須遮罩後才持久化。"""

    def test_probe_arguments_redact_query_values(self):
        clean = redact_tool_arguments(
            "probe_sql_injection",
            {"url": "https://example.com/search?q=secret&id=42"},
        )
        encoded = json.dumps(clean)
        self.assertIn("%5BREDACTED%5D", encoded)
        self.assertNotIn("secret", encoded)

    def test_other_tool_arguments_pass_through(self):
        """非 probe_sql_injection 的 tool 參數不應被遮罩。"""
        original = {"selector": ".btn", "text": "hello"}
        clean = redact_tool_arguments("click", dict(original))
        self.assertEqual(clean, original)

    def test_probe_result_removes_url_keeps_correlation(self):
        """probe_sql_injection 的持久化 result 只保留 confirmed/blocked/error/correlation_id。"""
        raw = {
            "confirmed": True,
            "correlation_id": "kali-sqlmap-sqli",
            "url": "https://example.com/s?q=secret",
            "note": "leaked note",
        }
        clean = redact_tool_result("probe_sql_injection", raw)
        dumped = json.dumps(clean)
        self.assertNotIn("secret", dumped)
        self.assertNotIn("example.com", dumped)
        self.assertNotIn("leaked note", dumped)
        self.assertTrue(clean.get("confirmed"))
        self.assertEqual(clean.get("correlation_id"), "kali-sqlmap-sqli")

    def test_probe_result_keeps_blocked_and_error(self):
        raw = {"confirmed": False, "blocked": "kali_disabled", "error": "", "url": "leak"}
        clean = redact_tool_result("probe_sql_injection", raw)
        self.assertFalse(clean.get("confirmed"))
        self.assertEqual(clean.get("blocked"), "kali_disabled")
        self.assertNotIn("leak", json.dumps(clean))

    def test_other_tool_result_passes_through(self):
        original = {"clicked": ".btn", "url_after": "https://example.com/page"}
        clean = redact_tool_result("click", dict(original))
        self.assertEqual(clean, original)


class ProbeSqlInjectionTests(TestCase):
    """agent 的 probe_sql_injection tool：同源約束 + 授權鎖委派 + 確認才產 finding。"""

    def setUp(self):
        self.user = User.objects.create_user(username="probeuser", password="x")
        self.scan_job = _make_scan_job(self.user)  # origin=https://example.com

    def _executor(self):
        page = MagicMock()
        page.url = "https://example.com/"
        return ToolExecutor(
            page=page, screenshot_dir="/tmp/agent", scan_job=self.scan_job
        )

    def test_cross_origin_is_forbidden(self):
        executor = self._executor()
        with patch("apps.scans.security.kali_tools.run_sqlmap") as m:
            outcome = asyncio.run(
                executor.run("probe_sql_injection", {"url": "https://evil.com/?id=1"})
            )
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.result["error"], "cross_origin_forbidden")
        m.assert_not_called()  # 跨站直接擋，不呼叫 sqlmap

    def test_requires_query_parameter(self):
        executor = self._executor()
        with patch("apps.scans.security.kali_tools.run_sqlmap") as m:
            outcome = asyncio.run(
                executor.run("probe_sql_injection", {"url": "https://example.com/products"})
            )
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.result["error"], "no_query_parameter")
        m.assert_not_called()

    def test_blocked_when_run_sqlmap_reports_blocked(self):
        executor = self._executor()
        blocked = {"ok": False, "blocked_reason": "active_testing_unauthorized", "stdout": ""}
        with patch("apps.scans.security.kali_tools.run_sqlmap", return_value=blocked):
            outcome = asyncio.run(
                executor.run("probe_sql_injection", {"url": "https://example.com/s?q=1"})
            )
        self.assertFalse(outcome.result["confirmed"])
        self.assertEqual(outcome.result["blocked"], "active_testing_unauthorized")
        self.assertIsNone(outcome.security_finding)

    def test_not_vulnerable_produces_no_finding(self):
        """Step 6：信任 confirmed=False，不再解析 stdout。"""
        executor = self._executor()
        res = {
            "ok": True,
            "blocked_reason": "",
            "confirmed": False,
            "stdout": "",
            "evidence_summary": {},
        }
        with patch("apps.scans.security.kali_tools.run_sqlmap", return_value=res):
            outcome = asyncio.run(
                executor.run("probe_sql_injection", {"url": "https://example.com/s?q=1"})
            )
        self.assertTrue(outcome.ok)
        self.assertFalse(outcome.result["confirmed"])
        self.assertIsNone(outcome.security_finding)

    def test_confirmed_produces_critical_security_finding(self):
        """Step 6：信任 confirmed=True，不再解析 stdout；evidence 是 evidence_summary 的 JSON。"""
        executor = self._executor()
        res = {
            "ok": True,
            "blocked_reason": "",
            "confirmed": True,
            "stdout": "",
            "evidence_summary": {
                "parameter": "q",
                "techniques": ["boolean-based blind"],
                "dbms": "MySQL",
            },
        }
        with patch("apps.scans.security.kali_tools.run_sqlmap", return_value=res):
            outcome = asyncio.run(
                executor.run("probe_sql_injection", {"url": "https://example.com/s?q=secret"})
            )
        self.assertTrue(outcome.result["confirmed"])
        self.assertIsNotNone(outcome.security_finding)
        f = outcome.security_finding
        self.assertEqual(f["category"], "security")
        self.assertEqual(f["severity"], "critical")
        self.assertEqual(f["rule_id"], "kali-sqlmap-sqli")

    def test_confirmed_finding_description_uses_redacted_url(self):
        """Finding description 必須使用遮罩後的 URL，query value 不可外洩。"""
        executor = self._executor()
        res = {
            "ok": True,
            "blocked_reason": "",
            "confirmed": True,
            "stdout": "",
            "evidence_summary": {"parameter": "q"},
        }
        with patch("apps.scans.security.kali_tools.run_sqlmap", return_value=res):
            outcome = asyncio.run(
                executor.run(
                    "probe_sql_injection",
                    {"url": "https://example.com/s?q=secret-value"},
                )
            )
        description = outcome.security_finding["description"]
        self.assertNotIn("secret-value", description)
        self.assertIn("q", description)  # query key 保留

    def test_confirmed_finding_evidence_is_json_dumps_of_summary(self):
        """evidence 必須是 json.dumps(evidence_summary, sort_keys=True)，不放 raw stdout。"""
        executor = self._executor()
        evidence_summary = {"dbms": "MySQL", "parameter": "q", "techniques": ["error-based"]}
        res = {
            "ok": True,
            "blocked_reason": "",
            "confirmed": True,
            "stdout": "raw should not leak",
            "evidence_summary": evidence_summary,
        }
        with patch("apps.scans.security.kali_tools.run_sqlmap", return_value=res):
            outcome = asyncio.run(
                executor.run("probe_sql_injection", {"url": "https://example.com/s?q=1"})
            )
        evidence = outcome.security_finding.get("evidence", "")
        # evidence 是 sorted JSON string
        self.assertEqual(evidence, json.dumps(evidence_summary, sort_keys=True))
        self.assertNotIn("raw should not leak", evidence)

    def test_confirmed_result_excludes_target_url(self):
        """Step 5/6：ToolOutcome.result 不可帶 target URL。"""
        executor = self._executor()
        res = {
            "ok": True,
            "blocked_reason": "",
            "confirmed": True,
            "stdout": "",
            "evidence_summary": {"parameter": "q"},
        }
        with patch("apps.scans.security.kali_tools.run_sqlmap", return_value=res):
            outcome = asyncio.run(
                executor.run(
                    "probe_sql_injection",
                    {"url": "https://example.com/s?q=secret"},
                )
            )
        dumped = json.dumps(outcome.result)
        self.assertNotIn("secret", dumped)
        self.assertNotIn("https://example.com/s", dumped)


class PersistAgentSecurityFindingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="secuser", password="x")
        self.scan_job = _make_scan_job(self.user)

    def test_persists_security_finding_with_owasp_tag(self):
        from apps.scans.models import Finding
        from apps.scans.scanners import make_finding

        f = make_finding(
            category="security", severity="critical", rule_id="kali-sqlmap-sqli",
            title="SQLi via agent", description="確認 https://example.com/s?q=1 可注入",
            remediation="用參數化查詢", evidence="sqlmap: is vulnerable",
            impact_area="vulnerability", confidence=1.0,
        )
        created = persist_agent_security_findings(self.scan_job, [f, f])  # 同 desc → 去重
        self.assertEqual(len(created), 1)
        obj = Finding.objects.get(scan_job=self.scan_job, rule_id="kali-sqlmap-sqli")
        self.assertEqual(obj.category, "security")
        self.assertEqual(obj.owasp_category, "A03")  # owasp_mapper 對 kali-sqlmap-sqli 的對映


# ---------------- loop ----------------


@override_settings(ARGUS_AGENT_MAX_STEPS=4, ARGUS_AGENT_MAX_TOKENS=10_000)
class HermesAgentLoopTests(TransactionTestCase):
    # 用 TransactionTestCase 避免 async + SQLite 跨 thread 寫入時的 "database table is locked"
    # （TestCase 把每個 test 包在 transaction 中，sync_to_async 跨 thread 拿不到 lock）。
    def setUp(self):
        self.user = User.objects.create_user(username="agent_user", password="x123!Long")
        self.scan_job = _make_scan_job(self.user)

    def _run(self, agent: HermesAgent, prompt: str = "do it"):
        return asyncio.run(agent.run(task_prompt=prompt))

    def test_finish_via_natural_language(self):
        chain = ProviderChain(providers=[FakeProvider([_chat_response_finish("all done")])])
        agent = HermesAgent(self.scan_job, executor=FakeExecutor(), chain=chain)
        result = self._run(agent)
        self.assertEqual(result.status, AgentSession.Status.COMPLETED)
        self.assertEqual(result.final_summary, "all done")
        session = AgentSession.objects.get(id=result.session_id)
        self.assertEqual(session.status, AgentSession.Status.COMPLETED)
        self.assertEqual(AgentStep.objects.filter(session=session).count(), 1)

    def test_finish_via_tool(self):
        chain = ProviderChain(
            providers=[
                FakeProvider(
                    [
                        _chat_response_tool("get_visible_text", {}, total_tokens=20),
                        _chat_response_tool("finish", {"summary": "done"}, total_tokens=30),
                    ]
                )
            ]
        )
        agent = HermesAgent(self.scan_job, executor=FakeExecutor(), chain=chain)
        result = self._run(agent)
        self.assertEqual(result.status, AgentSession.Status.COMPLETED)
        self.assertEqual(result.final_summary, "done")
        self.assertEqual(result.total_tokens, 50)
        # 2 個 step：get_visible_text + finish
        self.assertEqual(AgentStep.objects.filter(session_id=result.session_id).count(), 2)

    def test_max_steps_triggers_failure(self):
        responses = [_chat_response_tool("get_visible_text", {}) for _ in range(10)]
        chain = ProviderChain(providers=[FakeProvider(responses)])
        agent = HermesAgent(self.scan_job, executor=FakeExecutor(), chain=chain)
        result = self._run(agent)
        self.assertEqual(result.status, AgentSession.Status.FAILED)
        self.assertIn("max_steps_reached", result.error)

    def test_max_tokens_triggers_failure(self):
        responses = [
            _chat_response_tool("get_visible_text", {}, total_tokens=8000) for _ in range(4)
        ]
        chain = ProviderChain(providers=[FakeProvider(responses)])
        agent = HermesAgent(
            self.scan_job,
            executor=FakeExecutor(),
            chain=chain,
            max_tokens=10_000,
        )
        result = self._run(agent)
        self.assertEqual(result.status, AgentSession.Status.FAILED)
        self.assertIn("token_budget_exceeded", result.error)

    def test_issue_collected_via_tool(self):
        # 一個 round 內 LLM 一次回兩個 tool_calls：report_ux_issue + finish
        multi = ChatResponse(
            provider="fake",
            model="fake-model",
            content="",
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="report_ux_issue",
                    arguments={
                        "severity": "high",
                        "title": "送出按鈕無反應",
                        "description": "點了沒任何 feedback。",
                    },
                ),
                ToolCall(id="c2", name="finish", arguments={"summary": "stop"}),
            ],
            total_tokens=40,
        )
        chain = ProviderChain(providers=[FakeProvider([multi])])
        executor = FakeExecutor(
            outcomes={
                "report_ux_issue": ToolOutcome(
                    ok=True,
                    result={"reported": True, "title": "送出按鈕無反應"},
                    issue={
                        "severity": "high",
                        "title": "送出按鈕無反應",
                        "description": "點了沒任何 feedback。",
                        "remediation": "",
                        "selector": "button.submit",
                        "url": "https://example.com/checkout",
                    },
                ),
            }
        )
        agent = HermesAgent(self.scan_job, executor=executor, chain=chain)
        result = self._run(agent)
        self.assertEqual(result.status, AgentSession.Status.COMPLETED)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0]["title"], "送出按鈕無反應")
        # 同 round 兩個 tool_calls 共用一次 LLM call 的 token，只記第一筆
        steps = list(AgentStep.objects.filter(session_id=result.session_id).order_by("step_number"))
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].token_count, 40)
        self.assertEqual(steps[1].token_count, 0)

    def test_probe_sql_injection_step_persists_redacted_data(self):
        """Step 5：AgentStep 的 tool_arguments 與 tool_result 必須遮罩 query value、移除 URL。"""
        probe_response = ChatResponse(
            provider="fake",
            model="fake-model",
            content="",
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="probe_sql_injection",
                    arguments={"url": "https://example.com/search?q=secret&id=42"},
                )
            ],
            total_tokens=20,
            finish_reason="tool_calls",
        )
        chain = ProviderChain(
            providers=[FakeProvider([probe_response, _chat_response_finish("done")])]
        )
        executor = FakeExecutor(
            outcomes={
                "probe_sql_injection": ToolOutcome(
                    ok=True,
                    result={
                        "confirmed": True,
                        "correlation_id": "kali-sqlmap-sqli",
                        "url": "https://example.com/search?q=secret&id=42",
                        "note": "leaked note",
                    },
                ),
            }
        )
        agent = HermesAgent(self.scan_job, executor=executor, chain=chain)
        result = self._run(agent)

        step = AgentStep.objects.get(
            session_id=result.session_id, tool_name="probe_sql_injection"
        )
        # tool_arguments：query value 必須被遮罩
        args_json = json.dumps(step.tool_arguments)
        self.assertNotIn("secret", args_json)
        self.assertIn("%5BREDACTED%5D", args_json)
        # tool_result：URL 與 note 必須被移除，confirmed / correlation_id 保留
        result_json = json.dumps(step.tool_result)
        self.assertNotIn("secret", result_json)
        self.assertNotIn("example.com", result_json)
        self.assertNotIn("leaked note", result_json)
        self.assertTrue(step.tool_result.get("confirmed"))
        self.assertEqual(
            step.tool_result.get("correlation_id"), "kali-sqlmap-sqli"
        )


# ---------------- findings ----------------


class PersistAgentIssuesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="persist_user", password="x123!Long")
        self.scan_job = _make_scan_job(self.user)
        self.page = Page.objects.create(
            scan_job=self.scan_job,
            url="https://example.com/checkout",
            final_url="https://example.com/checkout",
            origin="https://example.com",
            status_code=200,
        )

    def test_persists_with_matched_page(self):
        issues = [
            {
                "severity": "high",
                "title": "結帳流程斷裂",
                "description": "點下一步沒反應。",
                "remediation": "檢查 onClick handler。",
                "selector": ".next",
                "url": "https://example.com/checkout",
            }
        ]
        created = persist_agent_issues(self.scan_job, issues)
        self.assertEqual(len(created), 1)
        finding = created[0]
        self.assertEqual(finding.category, Finding.Category.UX)
        self.assertEqual(finding.page, self.page)
        self.assertIn("不要輸出完整修復程式碼", finding.ai_handoff_prompt)

    def test_dedup_by_title(self):
        issues = [
            {
                "severity": "low",
                "title": "重複問題",
                "description": "desc",
                "url": "https://example.com/checkout",
            },
            {
                "severity": "high",
                "title": "重複問題",
                "description": "desc2",
                "url": "https://example.com/checkout",
            },
        ]
        created = persist_agent_issues(self.scan_job, issues)
        self.assertEqual(len(created), 1)

    def test_no_url_falls_back_to_site_level(self):
        issues = [
            {
                "severity": "medium",
                "title": "站台層級問題",
                "description": "整站找不到搜尋。",
            }
        ]
        created = persist_agent_issues(self.scan_job, issues)
        self.assertEqual(len(created), 1)
        self.assertIsNone(created[0].page)

    def test_invalid_severity_normalized(self):
        issues = [
            {
                "severity": "bogus",
                "title": "嚴重度錯",
                "description": "x",
            }
        ]
        created = persist_agent_issues(self.scan_job, issues)
        self.assertEqual(created[0].severity, "low")

    def test_skips_empty_title_or_description(self):
        issues = [
            {"severity": "low", "title": "", "description": "x"},
            {"severity": "low", "title": "x", "description": ""},
        ]
        created = persist_agent_issues(self.scan_job, issues)
        self.assertEqual(created, [])
