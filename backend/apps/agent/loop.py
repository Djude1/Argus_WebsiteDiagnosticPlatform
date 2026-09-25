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
from .tools import (
    TOOL_SCHEMAS,
    ToolExecutor,
    ToolOutcome,
    redact_tool_arguments,
    redact_tool_result,
)

DEFAULT_SYSTEM_PROMPT = """你是 Argus 平台的 Hermes 動態 UX 測試 Agent。
你會以呼叫 tool 的方式操作真實瀏覽器（Playwright），完成使用者指派的測試任務。

規則：
- 每一輪都必須呼叫一個 tool；自然語言回覆只在 finish 後給簡短總結。
- 過程中遇到任何 UX 問題（按鈕點不到、流程斷裂、UI 誤導、文案歧義等），
  必須呼叫 report_ux_issue，並提供修補方向（不要給程式碼）。
- 若已完成任務或無法繼續，呼叫 finish 並附短總結。
- 不要嘗試繞過任何驗證、不要操作他站資源、不要送出任何破壞性 payload。
- finish 的 summary 必須包含兩部分：(1) 已完成測試與發現摘要；
  (2) **未能完成的測試與原因**（缺少什麼工具／被目標拒絕／逾時／找不到入口），
  這些資訊會用於改善測試能力，請誠實具體描述。
- 效率紀律：文字回應用電報體（短句、無客套、不重述已知資訊）；
  探索走單一路徑優先，失敗才換替代法，不並行多猜測。
- 速率紀律：收到 429／連續 403（rate limit／WAF）時立即停打該端點，
  改測其他面相或收斂 finish——硬打只會被封鎖且浪費預算。
"""


@dataclass
class AgentRunResult:
    session_id: int
    status: str
    steps: int
    total_tokens: int
    issues: list[dict[str, Any]] = field(default_factory=list)
    security_findings: list[dict[str, Any]] = field(default_factory=list)
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
        tool_schemas: list[dict[str, Any]] | None = None,
        forced_first_tool: str | None = None,
    ):
        self.scan_job = scan_job
        self.executor = executor
        self.chain = chain
        self.max_steps = max_steps or settings.ARGUS_AGENT_MAX_STEPS
        self.max_tokens = max_tokens or settings.ARGUS_AGENT_MAX_TOKENS
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        # Task 6：依授權模式決定是否暴露 probe_sql_injection；預設全工具（向下相容）
        self.tool_schemas = tool_schemas if tool_schemas is not None else TOOL_SCHEMAS
        self.forced_first_tool = forced_first_tool
        self._messages: list[dict[str, Any]] = []
        self._issues: list[dict[str, Any]] = []
        self._security_findings: list[dict[str, Any]] = []
        self._total_tokens = 0
        self._step_counter = 0  # AgentStep DB 流水號，與 LLM round 解耦
        # 空轉偵測（PentAGI Reflector 概念的輕量版）：連續同名工具呼叫計數
        self._last_tool_name = ""
        self._consecutive_same_tool = 0
        self._stall_hint_given = False
        self._endgame_hint_given = False

    # 觀察型工具的回應很大（DOM 80 節點／整頁文字／請求清單／HTML），舊快照每輪
    # 重複計入 prompt tokens 是 context 爆炸的主因（實測 32 步累積 260k）。
    _BULKY_OBSERVATION_TOOLS = {
        "get_dom_summary",
        "get_visible_text",
        "get_network_requests",
        "get_page_html",
        "get_storage",
    }
    _STALL_HINT_THRESHOLD = 4

    def _compact_stale_tool_results(self) -> None:
        """每種觀察工具只保留最新一份全量快照，較舊的換成佔位字串。

        只改 content、不動 tool_call_id／結構，維持 OpenAI messages
        規範的配對完整性；舊快照本來就過時，對後續推理沒有保留價值。
        """
        keep: dict[str, str] = {}
        for msg in self._messages:
            if (
                msg.get("role") == "tool"
                and msg.get("name") in self._BULKY_OBSERVATION_TOOLS
                and "tool_call_id" in msg
            ):
                keep[msg["name"]] = msg["tool_call_id"]
        for msg in self._messages:
            if (
                msg.get("role") == "tool"
                and msg.get("name") in self._BULKY_OBSERVATION_TOOLS
                and msg.get("tool_call_id") != keep.get(msg.get("name"))
            ):
                msg["content"] = "[較舊的頁面快照已省略；需要最新狀態請再次呼叫工具]"

    def _record_tool_for_stall_detection(self, tool_name: str) -> None:
        if tool_name == self._last_tool_name:
            self._consecutive_same_tool += 1
        else:
            self._last_tool_name = tool_name
            self._consecutive_same_tool = 1

    def _inject_endgame_hint_if_needed(self, round_no: int) -> None:
        """剩餘步數收斂提示：接近 max_steps 時強制把未報發現落地。

        #30~#32 實測：specialist 常在步數/token 上限前仍持續深挖，
        未 report 的發現整批遺失——終局提示一次（不重複注入）。
        """
        remaining = self.max_steps - round_no
        if remaining == 10 and not self._endgame_hint_given:
            self._messages.append(
                {
                    "role": "user",
                    "content": (
                        f"系統提醒：你只剩約 {remaining} 步。立即停止新的探索——"
                        "把目前已確認但尚未回報的發現逐一 report_security_issue，"
                        "然後 finish。未回報的發現會全部遺失。"
                    ),
                }
            )
            self._endgame_hint_given = True

    def _inject_stall_hint_if_needed(self) -> None:
        """連續多次同一動作型工具（如反覆換 selector click 同一區塊）時導正。

        只在停滯事件首次發生插入一條提醒；計數隨即重置，再次空轉才會
        再觸發。觀察型工具（DOM／網路／截圖）不算停滯。
        """
        if (
            self._consecutive_same_tool >= self._STALL_HINT_THRESHOLD
            and self._last_tool_name in {"click", "type_text"}
            and not self._stall_hint_given
        ):
            self._messages.append(
                {
                    "role": "user",
                    "content": (
                        "系統提醒：你已連續多次執行相同的動作但似乎沒有明顯進展。"
                        "請先停下來用 get_dom_summary 確認目前頁面的實際狀態，"
                        "再決定：換一個完全不同的探索方向（例如其他選單功能或"
                        "表單），或直接 finish 回報目前為止的發現與觀察。"
                        "不要繼續對同一個元素嘗試不同的 selector。"
                    ),
                }
            )
            self._stall_hint_given = True
            self._consecutive_same_tool = 0

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
                self._compact_stale_tool_results()
                self._inject_stall_hint_if_needed()
                self._inject_endgame_hint_if_needed(_round_no)

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
                    self._record_tool_for_stall_detection(tc.name)
                    if outcome.issue:
                        self._issues.append(outcome.issue)
                    if outcome.security_finding:
                        self._security_findings.append(outcome.security_finding)
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
            security_findings=self._security_findings,
            final_summary=final_summary,
            error=error,
        )

    def _call_provider(self) -> ChatResponse:
        # 指揮官模式首輪強制派工：M3 讀完情報傾向直接文字收尾（#28/#32
        # 實測零 dispatch），首輪鎖定 dispatch_specialist 打斷該傾向
        tool_choice = "auto"
        if self.forced_first_tool and self._step_counter == 0:
            tool_choice = {
                "type": "function",
                "function": {"name": self.forced_first_tool},
            }
        return self.chain.chat_with_tools(
            messages=self._messages,
            tools=self.tool_schemas,
            temperature=0.2,
            max_tokens=1024,
            tool_choice=tool_choice,
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
        tool_name = tool_call.name if tool_call else ""
        # Task 5：持久化前遮罩 query value / 移除 target URL，避免機密外洩到 AgentStep
        safe_arguments = redact_tool_arguments(
            tool_name, tool_call.arguments if tool_call else {}
        )
        safe_result = redact_tool_result(
            tool_name, tool_outcome.result if tool_outcome else {}
        )
        AgentStep.objects.create(
            session=session,
            step_number=self._step_counter,
            observation=(response.content or "")[:5000],
            thought_summary="",
            tool_name=tool_name,
            tool_arguments=safe_arguments,
            tool_result=safe_result,
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
