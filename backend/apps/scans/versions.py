"""評分與規則版本（docs/scan-upgrade-roadmap.md P1：comparable history）。

每次完成的掃描都記下當時的計分公式版本與判定規則集版本。兩次掃描只有在兩個版本都相同時，
分數變化才能解讀成「網站變好／變差」；版本不同時，分數差可能只是規則或權重改了。

- **SCORING_VERSION**：`scanners.calculate_scores` 的公式（扣分權重、衰減常數、去重、基準分、
  哪些維度不評分）。改了公式就 +1。
- **RULESET_VERSION**：判定規則集（新增／移除規則、改嚴重度、AEO 判定規則、覆蓋契約）。
  改了會影響「哪些問題被找出來、算多嚴重」的規則，就改成當天日期。

舊掃描兩個欄位是空字串（版本不明），與任何掃描都不可直接比較。

另外 `tool_versions` 列出這次實際用到的外部工具版本（瀏覽器、axe-core、Lighthouse、Nuclei、
OWASP ZAP），重現或比較結果時對照；工具版本不同不影響 `comparable`，只是說明。
"""

from __future__ import annotations

SCORING_VERSION = "3"
RULESET_VERSION = "2026.10.10.4"


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


def tool_versions(scan) -> dict[str, str]:
    """這次掃描實際用到的外部工具與版本（沒跑的工具不列；舊掃描可能是空的）。

    來源：爬蟲與各階段寫進 ``warning_summary["tools"]`` 的版本、Nuclei 模板集紀錄、
    PageSpeed Insights 回傳的 Lighthouse 版本。
    """
    warnings = scan.warning_summary or {}
    tools = {
        str(name): str(version)
        for name, version in (warnings.get("tools") or {}).items()
        if version
    }
    lighthouse = ((scan.performance_report or {}).get("lab") or {}).get("version")
    if lighthouse:
        tools["Lighthouse"] = f"{lighthouse}（經 PageSpeed Insights）"
    nuclei = warnings.get("nuclei") or {}
    if nuclei:
        tools["Nuclei"] = (
            f"{nuclei.get('engine', 'unknown')}，模板 {nuclei.get('templates_version', 'unknown')}"
            f"（{nuclei.get('templates', 0)} 個，指紋 {str(nuclei.get('sha256', ''))[:12]}）"
        )
    return tools
