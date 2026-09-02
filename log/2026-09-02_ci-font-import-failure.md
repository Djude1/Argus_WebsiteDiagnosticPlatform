# CI 事故修正：字型解析在 import 時 raise，導致 Django 在無字型環境啟動失敗

**日期**：2026-09-02
**操作者**：Claude
**觸發**：`31aae2c` 推上後 Quality Gate 與 Build & Push Backend Image 雙雙失敗。

## 根因（我的 bug）

前置階段我在 `report_render/theme.py` 加了字型解析，並刻意讓它在找不到 CJK 字型時 `RuntimeError`——「大聲失敗」的方向是對的（退回預設字型的話圖表中文會變成一整排 □，報告照樣寄給客戶，沒有人會發現）。

**但位置錯了**：那段是在 **module import 時**執行的，而 `reports.py → report_render` 的 import 鏈是 Django 啟動時就會走的。結果沒有 CJK 字型的 GitHub runner 連 `manage.py check` 都跑不起來：

```
File "backend/apps/scans/report_render/theme.py", line 56, in <module>
    MPL_FONT_REGULAR, MPL_FONT_BOLD = _resolve_cjk_fonts()
RuntimeError: 報告圖表需要 CJK 字型，但找不到任何一組。
```

字型只有畫圖才需要，失敗就該發生在畫圖時。

## 變更內容

### 1. `theme.py`：解析不拋例外，要求時才拋
- `_resolve_cjk_fonts()` 找不到時回 `(None, None)`，不再 raise。
- 新增 `require_cjk_fonts()`：畫圖前呼叫，缺字型時才 `RuntimeError`，訊息保留可執行的修法。

### 2. `charts.py`：字型延後建立
原本 module 層就 `fm.FontProperties(fname=T.MPL_FONT_REGULAR)`，等同 import 時解析。改為 `_reg = _bold = None` + `_ensure_fonts()`，由唯一入口 `build_all()` 在真的要畫圖時呼叫。

### 3. 兩個 CI workflow 安裝 `fonts-noto-cjk`
`quality.yml` 與 `build-backend.yml` 都在 runner 上跑 `manage.py test apps`，而報告測試會**實際產生含 matplotlib 圖表的 .docx**——光是修好 import 還不夠，測試仍會在畫圖時失敗。與 Dockerfile 裝的是同一個套件。

### 4. 新增 `tests_report_fonts.py`（4 項）
- 沒有字型時解析必須安靜地回 `(None, None)`（**這就是能在 CI 掛掉前抓到本次事故的測試**）
- 環境變數覆寫優先
- 缺字型時 `require_cjk_fonts()` 要拋出含 `fonts-noto-cjk` 與環境變數名的可執行訊息
- `charts` 不得在 import 時建立 `FontProperties`

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 790 tests，OK（skipped=1）**
- **模擬無字型環境實測**（本機有字型，不模擬就證明不了）：把 `theme.MPL_FONT_*` 置為 `None` 後
  - `import reports` 成功 → Django 起得來
  - `charts.build_all()` 拋 `RuntimeError` 且訊息可執行 → 失敗發生在該發生的地方
- **workflow YAML 以 pyyaml 解析驗證**語法與步驟順序（字型安裝在跑測試之前）——不能讓 CI 因為我的 YAML 再掛一次。

## 教訓

「大聲失敗」是對的，但**失敗的時機必須對齊真正的需求點**。把環境檢查放在 import 時，等於讓一個只有單一功能需要的相依，變成整個應用程式的啟動條件。前置階段我在容器裡驗證過「有字型時能產圖」，卻沒有驗證「沒字型時會怎樣」——而 CI 正是那個沒字型的環境。

## 未處理／待決事項

- 仍未在容器內走完整 `build_scan_report` 路徑（前置階段驗的是直接呼叫 module）。
- 視覺與頁數仍需人工用 Word 確認。
- 本機磁碟仍在 98%。
