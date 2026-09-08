"""複刻 + 優化的流程編排。

分兩段是刻意的：複刻不花錢且幾乎不會失敗，優化要呼叫外部 agent 且隨時可能
掛掉。先把複刻落地再去碰 agent，優化失敗時使用者至少還拿得到原樣快照。
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal

import requests
from django.conf import settings
from django.db.models import Q, Sum

from apps.billing.models import CoinTransaction
from apps.billing.services import (
    charge_rebuild_usage,
    refund_rebuild,
    settle_rebuild_actual,
)
from apps.rebuild.client import OpenCodeClient, OpenCodeError
from apps.rebuild.models import SiteRebuild
from apps.rebuild.prompts import build_optimization_prompt
from apps.rebuild.snapshot import build_snapshot_html
from apps.scans.models import Finding

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
# 模型忘記加圍欄時的退路
_BARE_EDITS = re.compile(r"\{\s*\"edits\"\s*:.*\}", re.DOTALL)

def rebuild_media_dir(rebuild: SiteRebuild) -> str:
    return f"rebuilds/scan-{rebuild.scan_job_id}/page-{rebuild.page_id}"


def agent_workspace() -> str:
    """agent session 的 cwd。

    **這個目錄必須在 agent 主機上事先存在**：opencode 允許用不存在的目錄
    建 session，但之後送 prompt 會回 500（實測 1.18.29）。所以 cwd 固定指向
    一個既有目錄，每個 rebuild 的隔離靠下面的 output_relpath 走子路徑，
    不靠 cwd。
    """
    return settings.ARGUS_OPENCODE_WORKSPACE.rstrip("/")


def _write_media(relative_path: str, content: str) -> str:
    target = settings.MEDIA_ROOT / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative_path


def _sum_rebuild_charge(rebuild: SiteRebuild) -> int:
    """這次複刻實際被扣掉的淨點數。

    從 CoinTransaction 回推而不是自己再算一次：帳目的唯一事實來源是交易紀錄，
    兩邊各算各的遲早會對不起來。
    """
    total = CoinTransaction.objects.filter(site_rebuild=rebuild).aggregate(
        s=Sum("amount")
    )["s"]
    return max(0, -(total or 0))


def _set_status(rebuild: SiteRebuild, status: str, **fields) -> None:
    rebuild.status = status
    for key, value in fields.items():
        setattr(rebuild, key, value)
    rebuild.save(update_fields=["status", "updated_at", *fields.keys()])


# 思考流的上限。前端每 5 秒 polling 一次這筆資料，不設限的話單列會膨脹到
# 讓列表端點變慢。
_TRACE_MAX_ENTRIES = 120
_TRACE_MAX_CHARS = 1500
# 每累積這麼多事件才寫一次 DB。逐則寫等於一次任務打上千次 UPDATE。
_TRACE_FLUSH_EVERY = 8
# 回覆的長度上限。prompt 要求只回一行摘要，正常遠低於此；設限是防模型失控。
_REPLY_MAX_CHARS = 8000


def _append_trace(entries: list, event: dict) -> None:
    """把串流事件併進 trace，同型別的連續片段合併成一則。

    模型的推理是逐字吐出來的，不合併的話 trace 會變成幾百則單字，
    前端渲染起來既慢又不可讀。

    **agent 的回覆不走這裡**——結論存進 SiteRebuild.reply 獨立呈現。
    混在推理片段之間的話使用者找不到重點。
    """
    kind = event.get("type")
    text = (event.get("text") or "").strip()
    if kind == "tool":
        detail = event.get("detail") or ""
        entries.append(
            {"kind": "tool", "text": f"{event.get('name', '')} {detail}".strip()[:_TRACE_MAX_CHARS]}
        )
    elif kind in ("thinking", "text") and text:
        chunk = event.get("text", "")
        last = entries[-1] if entries else None
        # 只在「同型別且尚未寫滿」時併進上一則。少了長度判斷的話，一旦某則
        # 達到上限，後續所有 delta 都會被重新截回同樣長度、內容再也不增加，
        # 畫面看起來就像 agent 停住了——使用者實際回報過「卡住」。
        if last and last["kind"] == kind and len(last["text"]) < _TRACE_MAX_CHARS:
            room = _TRACE_MAX_CHARS - len(last["text"])
            last["text"] += chunk[:room]
            chunk = chunk[room:]
        while chunk:
            entries.append({"kind": kind, "text": chunk[:_TRACE_MAX_CHARS]})
            chunk = chunk[_TRACE_MAX_CHARS:]
    del entries[:-_TRACE_MAX_ENTRIES]


def _run_streaming(
    client: OpenCodeClient, rebuild: SiteRebuild, session_id: str, prompt: str, workspace: str
) -> dict:
    """跑一次 agent，過程中把思考流寫進 DB 讓前端能即時看到。

    串流只用來呈現進度；最終的回覆文字與花費一律從訊息物件取回——delta 只
    保證片段，而計費是照 cost 算的，不能用累加的片段去湊。
    """
    entries: list = list(rebuild.trace or [])
    reply_parts: list[str] = []
    pending = 0
    for event in client.stream(
        session_id,
        prompt,
        agent=settings.ARGUS_OPENCODE_AGENT,
        model=settings.ARGUS_OPENCODE_MODEL,
        directory=workspace,
    ):
        if event["type"] == "error":
            raise OpenCodeError(event.get("text") or "agent 串流失敗")
        if event["type"] == "done":
            break
        if event["type"] == "text":
            # 回覆逐字累積到 reply，讓前端邊跑邊顯示結論，而不是等跑完才出現
            reply_parts.append(event.get("text", ""))
        else:
            _append_trace(entries, event)
        pending += 1
        if pending >= _TRACE_FLUSH_EVERY:
            rebuild.trace = entries
            rebuild.reply = "".join(reply_parts)[:_REPLY_MAX_CHARS]
            rebuild.save(update_fields=["trace", "reply", "updated_at"])
            pending = 0

    rebuild.trace = entries
    rebuild.reply = "".join(reply_parts)[:_REPLY_MAX_CHARS]
    rebuild.save(update_fields=["trace", "reply", "updated_at"])
    return client.session_result(session_id)


def _fail(rebuild: SiteRebuild, error: str) -> SiteRebuild:
    """標記失敗並退點。

    退款一律走這裡，不散在各個 return 前面——漏掉任何一條失敗路徑，使用者
    就會為一個沒拿到的產出付錢，而且不會有人發現。refund_rebuild 本身冪等。
    """
    _set_status(rebuild, SiteRebuild.Status.FAILED, error=error[:255])
    refund_rebuild(rebuild.scan_job.user, rebuild, reason="失敗")
    return rebuild


_CONVERSATION_MAX_TURNS = 20
_QUESTION_MAX_CHARS = 2000


def ask_followup(rebuild: SiteRebuild, question: str) -> SiteRebuild:
    """在**同一個 opencode session** 裡追問。

    沿用原 session 才有意義：session 裡已經有整份 HTML 與診斷清單的上下文，
    重開一個等於要使用者再付一次把 85KB 塞進 prompt 的錢，而且 agent 會失憶。

    這裡不預扣點數——追問的回合很短，實際用量由 settle 依 cost 結算。
    餘額檢查在 view 層做，避免餘額為 0 的人先把 agent 的錢花掉。
    """
    question = (question or "").strip()[:_QUESTION_MAX_CHARS]
    if not question:
        raise OpenCodeError("問題不能是空的")
    if not rebuild.opencode_session_id:
        raise OpenCodeError("這次複刻沒有可延續的對話（可能是在啟用優化前產生的）")

    client = OpenCodeClient()
    if not client.is_configured:
        raise OpenCodeError("未設定 ARGUS_OPENCODE_BASE_URL")

    conversation = list(rebuild.conversation or [])
    conversation.append({"role": "user", "text": question})
    # 清掉上一輪的思考流：那是「產生優化版」的推理，跟這個問題無關，
    # 留著只會讓使用者以為新的回應沒有進來。對話本身保存在 conversation。
    _set_status(
        rebuild,
        SiteRebuild.Status.ASKING,
        conversation=conversation[-_CONVERSATION_MAX_TURNS:],
        reply="",
        trace=[],
    )

    try:
        result = _run_streaming(
            client, rebuild, rebuild.opencode_session_id, question, agent_workspace()
        )
    except (OpenCodeError, requests.RequestException) as exc:
        message = (
            str(exc)
            if isinstance(exc, OpenCodeError)
            else "無法連線到 OpenCode agent 服務"
        )
        if not isinstance(exc, OpenCodeError):
            logger.exception("追問連線失敗 rebuild=%s", rebuild.pk)
        # 失敗不改回 failed：那會讓已經產出的優化版看起來像沒做成。
        # 只把錯誤放進對話，讓使用者知道這一輪沒成功。
        conversation.append({"role": "agent", "text": f"（失敗）{message}"})
        _set_status(
            rebuild,
            SiteRebuild.Status.SUCCEEDED,
            conversation=conversation[-_CONVERSATION_MAX_TURNS:],
        )
        return rebuild

    conversation.append({"role": "agent", "text": rebuild.reply[:_REPLY_MAX_CHARS]})
    # session_result 回的是整個 session 的累計花費（含最初的優化那輪）。
    # 追問只該收「這一輪多花的」，所以扣掉先前已記錄的部分。
    previous = Decimal(str(rebuild.cost_usd or 0))
    total = Decimal(str(result["cost"] or 0))
    rebuild.cost_usd = total
    rebuild.save(update_fields=["cost_usd", "updated_at"])
    charge_rebuild_usage(rebuild.scan_job.user, rebuild, max(Decimal("0"), total - previous))
    _set_status(
        rebuild,
        SiteRebuild.Status.SUCCEEDED,
        conversation=conversation[-_CONVERSATION_MAX_TURNS:],
        coins_charged=_sum_rebuild_charge(rebuild),
    )
    return rebuild


def _extract_edits(reply: str) -> list[dict]:
    """從 agent 的回覆裡取出修改清單。

    優先找 ```json 圍欄；模型偶爾會忘記加圍欄，所以退而求其次掃第一個看起來
    像 {"edits": ...} 的物件。兩者都失敗就回空清單，由呼叫端判定失敗。
    """
    candidates = [m.group(1) for m in _JSON_FENCE.finditer(reply or "")]
    match = _BARE_EDITS.search(reply or "")
    if match:
        candidates.append(match.group(0))
    for blob in candidates:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        edits = data.get("edits") if isinstance(data, dict) else data
        if isinstance(edits, list):
            normalized = [_normalize_edit(e) for e in edits if isinstance(e, dict)]
            found = [e for e in normalized if e]
            if found:
                return found
    return []


# 模型不一定照 prompt 的欄位名走。實測看過它自己改用 old/new——那種整批
# 會被丟掉，使用者付了錢卻拿到「沒有提出任何修改」。認別名成本很低。
_FIND_KEYS = ("find", "old", "search", "from")
_REPLACE_KEYS = ("replace", "new", "to")
_WHY_KEYS = ("why", "issue", "reason")


def _pick(item: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _normalize_edit(item: dict) -> dict | None:
    find = _pick(item, _FIND_KEYS)
    if not find:
        return None
    return {
        "find": find,
        "replace": _pick(item, _REPLACE_KEYS),
        "why": _pick(item, _WHY_KEYS),
    }


def apply_edits(html: str, edits: list[dict]) -> tuple[str, list[dict]]:
    """把修改清單套用到原始 HTML，回傳 (結果, 每筆的套用狀況)。

    對不上的那筆**略過而不是整批失敗**：模型常常有幾筆憑印象重打、字元對不上，
    但其餘是好的。全有全無會讓一兩個字的偏差毀掉整次產出（而且使用者已經
    付過錢了）。哪幾筆沒套上會回報給使用者。
    """
    report = []
    for item in edits:
        find = item.get("find") or ""
        replacement = item.get("replace") or ""
        count = html.count(find)
        if count:
            html = html.replace(find, replacement)
        report.append(
            {
                "why": str(item.get("why") or "")[:200],
                "applied": count,
                "find": find[:120],
            }
        )
    return html, report


def run_rebuild(rebuild: SiteRebuild) -> SiteRebuild:
    media_dir = rebuild_media_dir(rebuild)

    # --- 第一段：複刻（不花 token） ---
    _set_status(rebuild, SiteRebuild.Status.SNAPSHOTTING)
    try:
        snapshot = build_snapshot_html(rebuild.page)
    except ValueError as exc:
        return _fail(rebuild, str(exc))
    snapshot_path = _write_media(f"{media_dir}/original.html", snapshot)
    rebuild.snapshot_path = snapshot_path
    rebuild.save(update_fields=["snapshot_path", "updated_at"])

    if not settings.ARGUS_OPENCODE_ENABLED:
        # 複刻已經落地，仍可下載；只有優化這一段沒做。
        return _fail(
            rebuild, "網頁優化未啟用（ARGUS_OPENCODE_ENABLED=false），僅產出原樣複刻"
        )

    client = OpenCodeClient()
    if not client.is_configured:
        return _fail(rebuild, "未設定 ARGUS_OPENCODE_BASE_URL，僅產出原樣複刻")

    # --- 第二段：優化（呼叫外部 agent，會花錢） ---
    _set_status(rebuild, SiteRebuild.Status.OPTIMIZING)
    workspace = agent_workspace()
    # 站台層級的 finding（page=NULL）也要送進去。前端的頁籤過濾就是
    # 「這一頁的 + 全站的」，只取 page.findings 會讓 UI 顯示有問題、但送給
    # agent 的清單是空的——agent 收到「沒有偵測到問題，請原樣輸出」就照做，
    # 使用者拿到與原稿一模一樣的「優化版」。使用者實際踩過。
    findings = list(
        Finding.objects.filter(scan_job_id=rebuild.scan_job_id)
        .filter(Q(page_id=rebuild.page_id) | Q(page__isnull=True))
    )
    prompt = build_optimization_prompt(rebuild.page, findings, snapshot)

    session_id = ""
    try:
        session_id = client.create_session(workspace)
        rebuild.opencode_session_id = session_id
        rebuild.save(update_fields=["opencode_session_id", "updated_at"])

        result = _run_streaming(client, rebuild, session_id, prompt, workspace)
        edits = _extract_edits(result["text"])
        if not edits:
            raise OpenCodeError("agent 沒有提出任何修改")
        optimized, report = apply_edits(snapshot, edits)
        applied = sum(1 for r in report if r["applied"])
        if not applied:
            raise OpenCodeError(
                f"agent 提出的 {len(report)} 筆修改都對不上原始 HTML"
            )
        rebuild.edit_report = report
        if applied < len(report):
            logger.warning(
                "rebuild=%s：%d/%d 筆修改對不上原文",
                rebuild.pk, len(report) - applied, len(report),
            )
    except OpenCodeError as exc:
        if session_id:
            client.abort(session_id)
        return _fail(rebuild, str(exc))
    except requests.RequestException:
        if session_id:
            client.abort(session_id)
        # 不把 exception 內容落地：requests 的訊息會帶完整 URL，而 URL 裡有
        # 內網位址。對使用者也沒有意義。
        logger.exception("OpenCode 連線失敗 rebuild=%s", rebuild.pk)
        return _fail(rebuild, "無法連線到 OpenCode agent 服務")

    optimized_path = _write_media(f"{media_dir}/optimized.html", optimized)
    _set_status(
        rebuild,
        SiteRebuild.Status.SUCCEEDED,
        optimized_path=optimized_path,
        model_id=result["model_id"][:128],
        cost_usd=Decimal(str(result["cost"] or 0)),
        edit_report=rebuild.edit_report,
    )
    # 依實際用量結算：cost_usd 要先落地，settle 才讀得到
    settle_rebuild_actual(rebuild.scan_job.user, rebuild)
    rebuild.coins_charged = _sum_rebuild_charge(rebuild)
    rebuild.save(update_fields=["coins_charged", "updated_at"])
    return rebuild
