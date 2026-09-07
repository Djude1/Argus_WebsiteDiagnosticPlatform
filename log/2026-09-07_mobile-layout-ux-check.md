# UX 分類的第一個確定性檢查：行動版破版

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

- `crawler.py`：`collect_mobile_layout()`——切到 375×812 量水平溢出並定位超寬元素，
  接在 `collect_element_boxes` 之後（所有其他擷取完成之後）
- `models.py`：`Page.layout_metrics` JSONField（migration `scans/0013`）
- `scanners.py`：`analyze_ux()` 產生 UX finding，並接進 `analyze_page()`
- `tasks.py`：把 `layout_metrics` 寫入 Page 與傳進 `analyze_page`；
  `tested_categories` 的 UX 判斷改為「量測成功 或 agent 跑完」
- `README.md`：修正 Hermes-Agent 的描述（見下）

## 原因

使用者反映「優化版看不出任何區別，UI/UX 都沒變化」。查證後確認那是預期行為：
掃描的 findings 全是 metadata 層級（title / description / canonical / alt /
JSON-LD），改了本來就不會有視覺差異。

要讓「優化」看得出來，得先有**視覺層級的 finding**。這是第一項。

刻意只做水平溢出一項：判準客觀（`scrollWidth > clientWidth`）、不需要
computed style、修好在手機上一眼可見。先用最小的一項驗證「在 crawler 加量測」
這條路的成本與風險——crawler 是所有掃描的必經路徑，改壞了不是這個功能不能用，
是整個產品不能用。

## 順帶修正 README 的誤導

README 把 Hermes-Agent 列在「系統功能」，讀起來像預設就有。實際上程式完整、
正式站 `ARGUS_AGENT_ENABLED` 也是 true，但 `scan_plan.py` 的 `run_agent` 要求
**同時**滿足：`scan_mode=active` ＋ 主動測試授權 ＋ 非單頁掃描。一般（被動）
掃描永遠不會觸發，所以使用者從來沒看過 UX finding。已在 README 標明前提。

## 影響範圍

- 每頁多一次 viewport 切換與量測（等待 300ms + evaluate）。掃描時間會增加，
  實際增幅需在正式站觀察
- `Page.layout_metrics` 每頁最多存 5 個超寬元素（`_MAX_OVERFLOW_OFFENDERS`）
- UX 分類從「永遠未評估」變成「有量到就評估」，報告會多出 UX 分數
- 舊掃描的 `layout_metrics` 是空的 → 視為未量測，不產生 finding、不列入計分

## 驗證方式

- `apps.scans` **632 tests OK**（新增 `tests_mobile_layout.py` 7 項）
- ruff / check / makemigrations 通過
- **用真實 Chromium 驗過量測本身**（純邏輯測試證明不了這段）：
  ```
  overflow.html  viewport=375 scroll=900 overflow=524
                 offenders=[{'selector': 'div.banner', 'overflow_px': 525}]
  ok.html        viewport=375 scroll=375 overflow=0  offenders=[]
  ```
  本機 Playwright 瀏覽器版本不符（套件要 1223、已裝 1228），依專案規範以
  `PLAYWRIGHT_BROWSERS_PATH=.ms-playwright` 安裝於專案內，未污染全域

## 待辦（評估過、暫不做）

第二批視覺檢查：色彩對比（WCAG AA 4.5:1）、內文字級 < 12px、觸控目標 < 44×44px。
三項共用同一次量測與同一種修復方式（注入覆寫 `<style>`），等這一項在正式站
確認成本可接受再做。

**修復可行性的已知限制**：對比／字級／觸控大小的樣式多半在外部 CSS，Argus 沒有
存、agent 也看不到，現行的 `{find, replace}` 修不了。要修得新增一種「注入覆寫
樣式」的 edit 型別——那是覆寫補丁，不是改正源頭，使用者不能直接貼回自己的網站。
