# axe 無障礙問題的嚴重度上限改為「中」

**日期**：2026-10-09
**操作者**：Claude

## 背景
使用者掃描 ntubimdbirc.tw，唯一一個「高」是「按鈕沒有可辨識的名稱」（axe `button-name`，impact critical）。被標記的是輪播的上一張／下一張箭頭：`<button class="slick-arrow slick-prev/next"><img alt="prevArrow/nextArrow">`。一般訪客看箭頭就知道用途，使用者認為不該是高。

## 變更內容
- **`scanners.py`**：
  - `_AXE_SEVERITY` 的 critical 從高改成中。serious 維持中，moderate 與 minor 維持低。
  - 「高」保留給整站層級風險，例如已知 CVE、資料外洩。axe 的 critical 是指輔助科技使用者完全無法使用，影響的是特定族群，所以上限是中。
- **新增 `_AXE_NOTES`**，說明誰會受影響，接在 `_ux_axe` 的描述後面：
  - `button-name`：一般訪客看圖示知道用途，但螢幕閱讀器使用者只會聽到「按鈕」。
  - `link-name`：同上。
- **`button-name` 修法補充**：
  - 輪播箭頭的例子（aria-label 寫「下一張」）。
  - 按鈕裡只有圖片時，也可以用圖片的 alt 說明。
- **`versions.RULESET_VERSION`** 改成 `2026.10.09`。新舊掃描不比較分數變化。
- **文件**：`apps/scans/CLAUDE.md` 的 axe 對應說明。需求書第 263 行「確認沒有 critical 等級問題」是驗收條件，指 axe 本身的 impact，不需要改。

## 驗證方式
- `tests_accessibility_axe`：
  - 原本斷言 critical 是高，改成中。
  - 新增 `AxeSeverityCapTests`，確認三件事：嚴重度是中、描述含「螢幕閱讀器」、修法含「輪播箭頭」。
- 全套後端測試、`ruff check backend`。

## 尚未做／觀察
- 只對新的掃描生效，既有掃描要重新掃描才會看到。
- 同一則回覆另外說明了正式機 PageSpeed 金鑰沒有生效的原因：Secret 改了，但 Pod 沒有重啟。沒有改程式。
