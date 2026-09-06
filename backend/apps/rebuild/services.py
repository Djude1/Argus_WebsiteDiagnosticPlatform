"""複刻 + 優化的流程編排。

分兩段是刻意的：複刻不花錢且幾乎不會失敗，優化要呼叫外部 agent 且隨時可能
掛掉。先把複刻落地再去碰 agent，優化失敗時使用者至少還拿得到原樣快照。
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

import requests
from django.conf import settings

from apps.rebuild.client import OpenCodeClient, OpenCodeError
from apps.rebuild.models import SiteRebuild
from apps.rebuild.prompts import OPTIMIZED_FILENAME, build_optimization_prompt
from apps.rebuild.snapshot import build_snapshot_html

logger = logging.getLogger(__name__)

# agent 沒照指示寫檔時的退路：從回覆裡撈 ```html 圍欄。
_HTML_FENCE = re.compile(r"```(?:html)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


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


def output_relpath(rebuild: SiteRebuild) -> str:
    """agent 要寫的檔案位置，相對於 agent_workspace()。

    帶上 scan/page 編號，兩個 rebuild 同時跑也不會互相覆蓋 optimized.html。
    """
    return (
        f"argus/scan-{rebuild.scan_job_id}-page-{rebuild.page_id}/{OPTIMIZED_FILENAME}"
    )


def _write_media(relative_path: str, content: str) -> str:
    target = settings.MEDIA_ROOT / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative_path


def _set_status(rebuild: SiteRebuild, status: str, **fields) -> None:
    rebuild.status = status
    for key, value in fields.items():
        setattr(rebuild, key, value)
    rebuild.save(update_fields=["status", "updated_at", *fields.keys()])


def _extract_optimized_html(
    client: OpenCodeClient, workspace: str, relpath: str, reply: str
):
    """優先讀 agent 寫的檔案，讀不到才退回從回覆文字撈圍欄。"""
    content = client.read_file(workspace, relpath)
    if content:
        return content
    match = _HTML_FENCE.search(reply or "")
    if match and match.group(1).strip():
        logger.warning("OpenCode 未寫出 %s，改用回覆中的 HTML 圍欄", relpath)
        return match.group(1).strip()
    return None


def run_rebuild(rebuild: SiteRebuild) -> SiteRebuild:
    media_dir = rebuild_media_dir(rebuild)

    # --- 第一段：複刻（不花 token） ---
    _set_status(rebuild, SiteRebuild.Status.SNAPSHOTTING)
    try:
        snapshot = build_snapshot_html(rebuild.page)
    except ValueError as exc:
        _set_status(rebuild, SiteRebuild.Status.FAILED, error=str(exc)[:255])
        return rebuild
    snapshot_path = _write_media(f"{media_dir}/original.html", snapshot)
    rebuild.snapshot_path = snapshot_path
    rebuild.save(update_fields=["snapshot_path", "updated_at"])

    if not settings.ARGUS_OPENCODE_ENABLED:
        # 複刻已經落地，仍可下載；只有優化這一段沒做。
        _set_status(
            rebuild,
            SiteRebuild.Status.FAILED,
            error="網頁優化未啟用（ARGUS_OPENCODE_ENABLED=false），僅產出原樣複刻",
        )
        return rebuild

    client = OpenCodeClient()
    if not client.is_configured:
        _set_status(
            rebuild,
            SiteRebuild.Status.FAILED,
            error="未設定 ARGUS_OPENCODE_BASE_URL，僅產出原樣複刻",
        )
        return rebuild

    # --- 第二段：優化（呼叫外部 agent，會花錢） ---
    _set_status(rebuild, SiteRebuild.Status.OPTIMIZING)
    workspace = agent_workspace()
    relpath = output_relpath(rebuild)
    findings = list(rebuild.page.findings.all())
    prompt = build_optimization_prompt(rebuild.page, findings, snapshot, relpath)

    session_id = ""
    try:
        session_id = client.create_session(workspace)
        rebuild.opencode_session_id = session_id
        rebuild.save(update_fields=["opencode_session_id", "updated_at"])

        result = client.prompt(
            session_id,
            prompt,
            agent=settings.ARGUS_OPENCODE_AGENT,
            model=settings.ARGUS_OPENCODE_MODEL,
        )
        optimized = _extract_optimized_html(
            client, workspace, relpath, result["text"]
        )
        if not optimized:
            raise OpenCodeError("agent 未產出優化後的 HTML")
    except OpenCodeError as exc:
        if session_id:
            client.abort(session_id)
        _set_status(rebuild, SiteRebuild.Status.FAILED, error=str(exc)[:255])
        return rebuild
    except requests.RequestException:
        if session_id:
            client.abort(session_id)
        # 不把 exception 內容落地：requests 的訊息會帶完整 URL，而 URL 裡有
        # 內網位址。對使用者也沒有意義。
        logger.exception("OpenCode 連線失敗 rebuild=%s", rebuild.pk)
        _set_status(
            rebuild, SiteRebuild.Status.FAILED, error="無法連線到 OpenCode agent 服務"
        )
        return rebuild

    optimized_path = _write_media(f"{media_dir}/{OPTIMIZED_FILENAME}", optimized)
    _set_status(
        rebuild,
        SiteRebuild.Status.SUCCEEDED,
        optimized_path=optimized_path,
        model_id=result["model_id"][:128],
        cost_usd=Decimal(str(result["cost"] or 0)),
    )
    return rebuild
