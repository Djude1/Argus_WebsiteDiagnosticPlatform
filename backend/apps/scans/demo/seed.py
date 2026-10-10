"""示範專案：新帳號一進來就有一個看得到完整分析結果的網站專案。

資料來源是虛構網站「晨光咖啡烘焙所」（scripts/demo_site/server.py）的三次**真實**掃描，
由 `manage.py export_demo_dataset` 匯出成 dataset.json.gz 與 screenshots/（重產步驟見 README.md）。
建立時複製成使用者自己的 SiteProject（is_demo=True）、ScanJob、Page、Finding 與 FixOutput，
並把三次掃描的時間平移到「約一個月前、兩週前、昨天」，讓趨勢與「新增／持續／未出現」看起來自然。

示範專案唯讀：不能建立掃描、不能修改設定、不能產生修正產出或網頁複刻（views／serializers 檢查
`is_demo`），但可以封存。截圖是 repo 內的共用檔案（相對 BASE_DIR 的路徑），不會複製到 media。
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.scans.models import Finding, FixOutput, Page, ScanJob, SiteProject
from apps.scans.versions import RULESET_VERSION, SCORING_VERSION

logger = logging.getLogger(__name__)

DEMO_DIR = Path(__file__).resolve().parent
DATASET_PATH = DEMO_DIR / "dataset.json.gz"
SCREENSHOT_DIR = DEMO_DIR / "screenshots"

SCAN_FIELDS = (
    "original_url",
    "normalized_url",
    "origin",
    "scan_mode",
    "categories",
    "max_depth",
    "max_pages",
    "respect_robots",
    "active_testing_authorized",
    "overall_score",
    "category_scores",
    "top_actions",
    "warning_summary",
    "aeo_report",
    "seo_report",
    "progress",
    "scan_log",
)
PAGE_FIELDS = (
    "url",
    "final_url",
    "origin",
    "status_code",
    "title",
    "html",
    "rendered_dom",
    "html_only_text",
    "screenshot_path",
    "load_time_ms",
    "depth",
    "fetch_mode",
    "blocked_reason",
    "outgoing_links",
    "headers",
    "element_boxes",
    "layout_metrics",
)
FINDING_FIELDS = (
    "severity",
    "category",
    "priority_score",
    "impact_area",
    "confidence",
    "title",
    "description",
    "remediation",
    "evidence",
    "rule_id",
    "evidence_type",
    "evidence_json",
    "evidence_source",
    "bounding_box",
    "selector",
    "owasp_category",
    "cwe_id",
    "ai_handoff_prompt",
)
# 三次掃描各自「完成於幾天前」（依序對應匯出的掃描；多於三次時從最後往前對齊）
COMPLETED_DAYS_AGO = (29, 15, 1)

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


@lru_cache(maxsize=1)
def load_dataset() -> dict:
    return json.loads(gzip.decompress(DATASET_PATH.read_bytes()).decode("utf-8"))


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _shift_times(value, delta: timedelta):
    """把 JSON 裡的 ISO 時間字串（掃描紀錄、進度、AEO 評估時間）一起平移。"""
    if isinstance(value, dict):
        return {key: _shift_times(item, delta) for key, item in value.items()}
    if isinstance(value, list):
        return [_shift_times(item, delta) for item in value]
    if isinstance(value, str) and _ISO_RE.match(value):
        try:
            return (_parse(value) + delta).isoformat()
        except ValueError:
            return value
    return value


def demo_enabled() -> bool:
    return getattr(settings, "ARGUS_DEMO_PROJECT_ENABLED", True) and DATASET_PATH.exists()


@transaction.atomic
def create_demo_project(user) -> SiteProject | None:
    """為使用者建立示範專案；已有示範專案（含已封存）或同網站專案時不重複建立。"""
    data = load_dataset()
    meta = data["project"]
    if SiteProject.objects.filter(user=user).filter(is_demo=True).exists():
        return None
    if SiteProject.objects.filter(user=user, origin=meta["origin"]).exists():
        return None

    project = SiteProject.objects.create(
        user=user,
        is_demo=True,
        name=meta["name"],
        origin=meta["origin"],
        start_url=meta["start_url"],
        default_scope=meta["default_scope"],
        default_categories=meta["default_categories"],
        favicon=meta.get("favicon") or "",
        favicon_checked_at=timezone.now(),
        description="Argus 示範專案：虛構網站的三次真實掃描結果，讓你先看看 Argus 能分析什麼。",
    )

    now = timezone.now()
    scans = data["scans"]
    offsets = COMPLETED_DAYS_AGO[-len(scans) :] if len(scans) <= len(COMPLETED_DAYS_AGO) else None
    for number, entry in enumerate(scans):
        days_ago = offsets[number] if offsets else max(1, (len(scans) - number) * 7)
        row = entry["scan"]
        completed = _parse(row["completed_at"])
        target = now - timedelta(days=days_ago, hours=2)
        delta = target - completed

        scan = ScanJob(
            user=user,
            project=project,
            status=ScanJob.Status.COMPLETED,
            **{field: _shift_times(row[field], delta) for field in SCAN_FIELDS},
        )
        scan.started_at = _parse(row["started_at"]) + delta
        scan.completed_at = target
        # 三次示範掃描視為同一套規則，總覽才會顯示 57 → 60 → 61 的分數變化；
        # 匯出資料沒有版本欄位，空字串會被當成版本不明而寫「評分規則已更新，無法直接比較」
        scan.scoring_version = SCORING_VERSION
        scan.ruleset_version = RULESET_VERSION
        scan.save()
        # created_at 是 auto_now_add，只能建立後再改
        ScanJob.objects.filter(id=scan.id).update(created_at=_parse(row["created_at"]) + delta)

        pages = Page.objects.bulk_create(
            [
                Page(scan_job=scan, **{field: page[field] for field in PAGE_FIELDS})
                for page in entry["pages"]
            ]
        )
        Finding.objects.bulk_create(
            [
                Finding(
                    scan_job=scan,
                    page=pages[finding["page_index"]]
                    if finding.get("page_index") is not None
                    else None,
                    **{field: finding[field] for field in FINDING_FIELDS},
                )
                for finding in entry["findings"]
            ]
        )
        # 匯出資料的分數是當時公式算的；用目前公式重算，與分數說明、評分版本一致
        rescore_with_current_formula(scan)
        fix = row.get("fix_output")
        if fix:
            FixOutput.objects.create(
                scan_job=scan,
                status=FixOutput.Status.READY,
                artifacts=fix["artifacts"],
                provider=fix.get("provider") or "",
                model_id=fix.get("model_id") or "",
                generated_at=target + timedelta(minutes=10),
            )
    return project


def rescore_with_current_formula(scan) -> None:
    from apps.scans.finding_normalization import _rescore

    _rescore(scan)


def create_demo_project_safely(user) -> None:
    """註冊流程用：示範資料建立失敗只記錄，絕不影響註冊與登入。"""
    if not demo_enabled():
        return
    try:
        create_demo_project(user)
    except Exception:
        logger.exception("建立示範專案失敗（user_id=%s）", user.pk)
