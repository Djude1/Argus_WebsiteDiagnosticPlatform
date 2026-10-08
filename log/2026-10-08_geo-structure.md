# GEO 可被 AI 摘要性：長篇無小標題、列舉寫成整段（roadmap §3 GEO 第 3 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- 先盤點既有檢查：段落過長（>1000 字，低）、可引用文字區塊偏少（資訊）、缺 `<main>`（低）、核心內容依賴 JavaScript（中）已存在，不重做。
- 新增 `backend/apps/scans/geo_structure.py`，由 `scanners.analyze_page` 的 GEO 分支逐頁呼叫（函式內匯入，避免與 scanners 循環匯入）：
  - `geo-long-content-no-subheadings`（低）：
    - 成句段落（40 字以上）換算約中文 1500 字／英文 1000 詞以上，且原始 HTML 沒有任何 h2–h6。
    - 門檻刻意高於一般新聞稿長度（800–1500 字不分段是正常寫法）。
  - `geo-enumeration-not-list`（資訊，不扣分）：同一段出現 3 個以上編號（`1.`、`1)`、`(1)`、`（1）`、`第一、`、`一、`），建議改成清單。
- 刻意不做：
  - 「開頭有沒有摘要句」：屬寫作品質，規則無法可靠判定。
  - 不以「整頁有沒有 `<ul>`」決定是否列舉：導覽列幾乎都是 `<ul>`，會讓檢查永遠不觸發。改看「同一段」內的編號——清單項目本來就會被擷取成獨立段落。
- `reports.RULE_BASIS` 兩條規則的依據與限制。
- 文件：scans CLAUDE.md、roadmap、需求書 GEO 段落。

## 真實網站核對（各站首頁＋最多 14 個同網站連結）
- 正確列出：
  - ntubimdbirc.tw/about 三段「1.技術研究及成果擴散 2.辦理企業職業訓練 3.業務協調及基地統合」等列舉。
  - ntub.edu.tw 無障礙說明頁「1) 上方導覽連結區 2) 首頁右側功能區 3) 左側導覽連結區 4) 主要內容區」。
- 依實測修正的誤判：
  1. technews／gslin 的 RSS（`/feed/`）被當網頁分析 → 略過沒有 `<html>`／`<body>` 的文件。
  2. blog.gslin.org 首頁被判「沒有小標題」：文章標題在 `<header class="entry-header">` 裡，正文擷取會排除 `<header>` → 改為直接數原始 HTML 的 h2–h6。
  3. 中華郵政首頁被判「長篇內容」：實際是 140 個短連結文字（中位數 10 字）→ 只算 40 字以上的成句段落。
  4. css-tricks CSS 範例 `style(--index: 1)…` 被當成編號 → 略過 `<pre>`／`<code>`。
- 修正後 law.moj.gov.tw、中華電信、gov.tw、wordpress.org、css-tricks 等沒有誤報。
- 長篇無小標題在真實網站沒有出現：維基百科、Project Gutenberg、科技新報都有小標題。目前只有測試驗證。

## 影響範圍
- 長篇未分段的頁面多一項低風險 GEO 問題；列舉建議為資訊、不扣分。
- `RULESET_VERSION` 今天已是 2026.10.08；不需要 migration。

## 驗證方式
- 新測試 `tests_geo_structure.py`（7 項）：
  - 長篇無小標題。
  - `<header>` 內的小標題也算。
  - 短頁與入口網站連結頁不算。
  - RSS 略過。
  - 行內編號；三種編號寫法，含全形括號接在中文後面。
  - 真正的清單、版本號、程式碼與只有兩項的列舉不列。
- 全套 `uv run python backend/manage.py test apps`：1706 項 OK（3 skipped）。
- `ruff check backend` 通過；`makemigrations --check` 無變更。
