"""分數說明（roadmap §12 第 3 項：評分可解釋化）。

由資料庫保存的發現，依目前的計分公式（scanners.score_breakdown）還原每個維度的分數來源：
基準分、逐項扣分（只修好這一項時的分數）、不扣分的項目與覆蓋狀態。不重新掃描、不寫資料庫。

掃描若是舊版計分公式算的（scoring_version 不同）或發現事後被重新判定過，依目前公式重算的分數
可能和保存的分數不同，``matches`` 為 False，前端據此提示。
"""

from __future__ import annotations

from apps.scans.coverage import CHECK_CATEGORIES, incomplete_checks
from apps.scans.finding_normalization import stored_scoring_inputs
from apps.scans.models import ScanJob
from apps.scans.scanners import (
    SCORE_CATEGORIES,
    SCORE_DECAY_CONSTANT,
    SEVERITY_PENALTY,
    score_breakdown,
)
from apps.scans.versions import SCORING_VERSION


def score_explanation(scan_job: ScanJob) -> dict:
    stored = scan_job.category_scores or {}
    payload = {
        "available": bool(stored),
        "overall_score": scan_job.overall_score,
        "scoring_version": scan_job.scoring_version,
        "current_scoring_version": SCORING_VERSION,
        "decay_constant": SCORE_DECAY_CONSTANT,
        "weights": {str(severity): weight for severity, weight in SEVERITY_PENALTY.items()},
        "matches": True,
        "categories": [],
    }
    if not stored:
        return payload
    findings, tested, base_scores = stored_scoring_inputs(scan_job)
    breakdown = score_breakdown(findings, tested_categories=tested, base_scores=base_scores)
    coverage = scan_job.coverage or {}
    incomplete = incomplete_checks(coverage)
    for category in SCORE_CATEGORIES:
        entry = breakdown.get(category)
        if entry is None:
            continue
        stored_score = stored.get(category)
        if stored_score != entry["score"]:
            payload["matches"] = False
        payload["categories"].append({
            "category": category,
            **entry,
            "score": stored_score,
            "recomputed_score": entry["score"],
            "coverage": (coverage.get("categories") or {}).get(category, ""),
            "incomplete_checks": [
                item["label"] for item in incomplete
                if CHECK_CATEGORIES.get(item["check"]) == category
            ],
        })
    return payload
