"""axe-core 無障礙檢查（docs/scan-upgrade-roadmap.md P1：UX 接業界標準規則）。

axe-core（Deque Systems，MPL-2.0）是 WCAG 自動化檢查的業界標準。檔案放在
`vendor/axe/axe.min.js`（固定版本、隨 backend image 一起部署，不在掃描時下載）。

- 注入方式用 `page.evaluate(原始碼)`：走 DevTools 協定執行，不受目標網站的 CSP 限制
  （`add_script_tag` 會被 `script-src` 擋掉）。
- 只跑 WCAG 2.0／2.1／2.2 A 與 AA 的規則，只回傳違規（不回 passes，結果小）。
- 與自建檢查重疊的規則關掉，避免同一件事報兩次：`target-size`（自建觸控目標用 40px
  易用性門檻）、`label`／`select-name`（自建「表單欄位缺少可及標籤」）。
- 每項違規最多保留 `MAX_NODES` 個元素的選擇器、HTML 片段與文件座標（桌面版截圖用）。

只在爬蟲裡呼叫；失敗回 `{"error": 例外類別}`，不影響其他擷取。
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

AXE_PATH = Path(__file__).parent / "vendor" / "axe" / "axe.min.js"
MAX_NODES = 5
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]
# 與自建 UX 檢查重疊：交給自建規則（scanners._ux_tap_targets／_ux_unlabeled_fields）
DISABLED_RULES = ("target-size", "label", "select-name")

_RUN_SCRIPT = """
async ({tags, disabled, maxNodes}) => {
  const rules = {};
  for (const id of disabled) rules[id] = {enabled: false};
  const result = await window.axe.run(document, {
    runOnly: {type: "tag", values: tags},
    rules,
    resultTypes: ["violations"],
  });
  const box = (target) => {
    if (!Array.isArray(target) || typeof target[0] !== "string" || target.length !== 1) return null;
    let el = null;
    try { el = document.querySelector(target[0]); } catch (e) { return null; }
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    const x = r.left + window.scrollX;
    const y = r.top + window.scrollY;
    return {x, y, width: r.width, height: r.height};
  };
  return {
    version: window.axe.version,
    violations: result.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      description: v.description,
      help_url: v.helpUrl,
      tags: v.tags.filter((t) => t.startsWith("wcag")),
      count: v.nodes.length,
      nodes: v.nodes.slice(0, maxNodes).map((n) => ({
        target: (n.target || []).map(String).join(" >>> "),
        html: (n.html || "").slice(0, 200),
        summary: (n.failureSummary || "").slice(0, 300),
        box: box(n.target),
      })),
    })),
  };
}
"""


@lru_cache(maxsize=1)
def _axe_source() -> str:
    return AXE_PATH.read_text(encoding="utf-8")


async def run_axe(page, *, timeout_seconds: float) -> dict:
    """在目前頁面跑 axe-core；成功回 {"version", "violations"}，失敗回 {"error"}。"""
    async def _run() -> dict:
        await page.evaluate(_axe_source())
        return await page.evaluate(
            _RUN_SCRIPT,
            {"tags": WCAG_TAGS, "disabled": list(DISABLED_RULES), "maxNodes": MAX_NODES},
        )

    try:
        return await asyncio.wait_for(_run(), timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - 無障礙檢查失敗不影響這一頁的其他擷取
        return {"error": exc.__class__.__name__}
