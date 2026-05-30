"""Hermes-Agent 主迴圈：observe → think → act。

流程：
1. 建立 AgentSession（status=queued → running），記錄 provider/model/max_steps。
2. 以 system_prompt + task_prompt 為起始 messages，進入迴圈。
3. 每步呼叫 ProviderChain.chat_with_tools 取得 tool_calls 或 content：
   - 有 tool_calls → 依序執行 ToolExecutor.run，把結果以 role=tool 回灌 messages，
     並寫一筆 AgentStep。
   - 無 tool_calls 但有 content → 視為「Agent 想自然語言收尾」，寫 AgentStep 後結束。
   - finish/超過 max_steps/超過 max_tokens → 結束。
4. report_ux_issue 收集到 self.issues，由 caller 決定落地時機（loop 不直接寫 Finding，
   方便測試與離線重放）。
5. AgentSession.status 流轉至 completed / failed。

安全閘：
- max_steps 上限（settings.ARGUS_AGENT_MAX_STEPS，預設 20）
- max_tokens 上限（settings.ARGUS_AGENT_MAX_TOKENS）
- ToolExecutor 自身有 timeout
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.scans.models import AgentSession, AgentStep, ScanJob

from .providers import ChatResponse, ProviderChain, ProviderError
from .tools import TOOL_SCHEMAS, ToolExecutor, ToolOutcome

DEFAULT_SYSTEM_PROMPT = """你是 Argus 平台的 Hermes 動態 UX 測試 Agent。
你會以呼叫 tool 的方式操作真實瀏覽器（Playwright），完成使用者指派的測試任務。

規則：
- 每一輪都必須呼叫一個 tool；自然語言回覆只在 finish 後給簡短總結。
- 過程中遇到任何 UX 問題（按鈕點不到、流程斷裂、UI 誤導、文案歧義等），
  必須呼叫 report_ux_issue，並提供修補方向（不要給程式碼）。
- 若已完成任務或無法繼續，呼叫 finish 並附短總結。
- 不要嘗試繞過任何驗證、不要操作他站資源、不要送出任何破壞性 payload。
"""


@dataclass
class AgentRunResult:
    session_id: int
    status: str
    steps: int
    total_tokens: int
    issues: list[dict[str, Any]] = field(default_factory=list)
    final_summary: str = ""
    error: str = ""


class HermesAgent:
    """observe-think-act 主迴圈。

    呼叫方式：
        agent = HermesAgent(scan_job=..., page=..., chain=...)
        result = await agent.run(task_prompt="加入購物車後完成結帳")
    """

    def __init__(
        self,
        scan_job: ScanJob,
        executor: ToolExecutor,
        chain: ProviderChain,
        max_steps: int | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ):
        self.scan_job = scan_job
        self.executor = executor
        self.chain = chain
        self.max_steps = max_steps or settings.ARGUS_AGENT_MAX_STEPS
        self.max_tokens = max_tokens or settings.ARGUS_AGENT_MAX_TOKENS
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._messages: list[dict[str, Any]] = []
        self._issues: list[dict[str, Any]] = []
        self._total_tokens = 0
        self._step_counter = 0  # AgentStep DB 流水號，與 LLM round 解耦

    async def run(self, task_prompt: str) -> AgentRunResult:
        from asgiref.sync import sync_to_async

        session = await sync_to_async(self._create_session)()

        self._messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_prompt},
        ]
        final_summary = ""
        error = ""
        finished = False

        try:
            for _round_no in range(1, self.max_steps + 1):
                if self._total_tokens > self.max_tokens:
                    error = f"token_budget_exceeded({self._total_tokens}>{self.max_tokens})"
                    break

                response = await sync_to_async(self._call_provider)()
                self._total_tokens += response.total_tokens

                if not response.tool_calls:
                    # Agent 自然語言收尾
                    final_summary = response.content
                    await sync_to_async(self._save_step)(
                        session, response, tool_outcome=None, tool_call=None, is_first_in_round=True
                    )
                    finished = True
                    break

                # 把 assistant 訊息（含 tool_calls）也存進 messages，符合 OpenAI 規範
                self._messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                                },
                            }
                            for tc in response.tool_calls
                        ],
                    }
                )

                for tc_idx, tc in enumerate(response.tool_calls):
                    outcome = await self.executor.run(tc.name, tc.arguments)
                    await sync_to_async(self._save_step)(
                        session,
                        response,
                        tool_outcome=outcome,
                        tool_call=tc,
                        is_first_in_round=(tc_idx == 0),
                    )
                    self._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": json.dumps(outcome.result, ensure_ascii=False)[:4000],
                        }
                    )
                    if outcome.issue:
                        self._issues.append(outcome.issue)
                    if outcome.finish:
                        final_summary = str(outcome.result.get("summary", ""))
                        finished = True
                        break

                if finished:
                    break
            else:
                error = f"max_steps_reached({self.max_steps})"
        except ProviderError as exc:
            error = f"provider_error:{exc.provider}:{exc.http_status}"
        except Exception as exc:  # noqa: BLE001 — 任何異常都要關閉 session
            error = f"agent_exception:{exc.__class__.__name__}"

        status = (
            AgentSession.Status.COMPLETED
            if finished and not error
            else AgentSession.Status.FAILED
        )
        await sync_to_async(self._finalize_session)(
            session, status=status, error=error, total_tokens=self._total_tokens
        )
        return AgentRunResult(
            session_id=session.id,
            status=status,
            steps=self._step_counter,
            total_tokens=self._total_tokens,
            issues=self._issues,
            final_summary=final_summary,
            error=error,
        )

    def _call_provider(self) -> ChatResponse:
        return self.chain.chat_with_tools(
            messages=self._messages,
            tools=TOOL_SCHEMAS,
            temperature=0.2,
            max_tokens=1024,
            tool_choice="auto",
        )

    def _create_session(self) -> AgentSession:
        first_provider = next(
            (
                p
                for p in self.chain.providers
                if getattr(p, "available", False) and p.supports_tools
            ),
            None,
        )
        session = AgentSession.objects.create(
            scan_job=self.scan_job,
            provider=first_provider.name if first_provider else "unknown",
            model=first_provider.default_model if first_provider else "unknown",
            status=AgentSession.Status.RUNNING,
            max_steps=self.max_steps,
            started_at=timezone.now(),
        )
        return session

    def _save_step(
        self,
        session: AgentSession,
        response: ChatResponse,
        tool_outcome: ToolOutcome | None,
        tool_call,
        is_first_in_round: bool,
    ) -> None:
        self._step_counter += 1
        AgentStep.objects.create(
            session=session,
            step_number=self._step_counter,
            observation=(response.content or "")[:5000],
            thought_summary="",
            tool_name=tool_call.name if tool_call else "",
            tool_arguments=tool_call.arguments if tool_call else {},
            tool_result=tool_outcome.result if tool_outcome else {},
            # 同 round 的多筆 tool 共用 1 次 LLM 呼叫的 token，只記在第一筆避免重複
            token_count=response.total_tokens if is_first_in_round else 0,
        )

    def _finalize_session(
        self,
        session: AgentSession,
        status: str,
        error: str,
        total_tokens: int,
    ) -> None:
        session.status = status
        session.total_tokens = total_tokens
        session.error_message = error[:500]
        session.completed_at = timezone.now()
        session.save(
            update_fields=["status", "total_tokens", "error_message", "completed_at"]
        )
