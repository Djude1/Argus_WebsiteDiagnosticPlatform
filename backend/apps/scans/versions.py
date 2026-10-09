"""評分與規則版本（docs/scan-upgrade-roadmap.md P1：comparable history）。

每次完成的掃描都記下當時的計分公式版本與判定規則集版本。兩次掃描只有在兩個版本都相同時，
分數變化才能解讀成「網站變好／變差」；版本不同時，分數差可能只是規則或權重改了。

- **SCORING_VERSION**：`scanners.calculate_scores` 的公式（扣分權重、衰減常數、去重、基準分、
  哪些維度不評分）。改了公式就 +1。
- **RULESET_VERSION**：判定規則集（新增／移除規則、改嚴重度、AEO 判定規則、覆蓋契約）。
  改了會影響「哪些問題被找出來、算多嚴重」的規則，就改成當天日期。

舊掃描兩個欄位是空字串（版本不明），與任何掃描都不可直接比較。
"""

from __future__ import annotations

SCORING_VERSION = "2"
RULESET_VERSION = "2026.10.09"


def comparable(scan, other) -> bool:
    """兩次掃描的分數可否直接比較（兩者版本都已知且相同）。"""
    if scan is None or other is None:
        return False
    return bool(
        scan.scoring_version
        and scan.ruleset_version
        and scan.scoring_version == other.scoring_version
        and scan.ruleset_version == other.ruleset_version
    )


def label(scan) -> str:
    """給人看的版本字串；舊掃描回「版本不明」。"""
    if not (scan.scoring_version and scan.ruleset_version):
        return "版本不明（舊掃描）"
    return f"計分 v{scan.scoring_version}／規則 {scan.ruleset_version}"
