# 事故修復：截圖失敗導致整頁分析作廢

**日期**：2026-08-31
**操作者**：Claude
**觸發**：使用者回報「掃描後截圖沒有顯示」，補充「且 SEO 的分析也沒有了」，並指出是最近一次前端更新之後開始的。

## 使用者的假設（前端）已排除，證據如下

| 懷疑點 | 檢查方式 | 結果 |
|---|---|---|
| `styles.css` 的 132 行插入破壞樣式 | **建置前後兩版 CSS 逐規則比對**：1821 → 1847 條，**0 條內容改變**，「消失」的 2 條只是我把 `.verify-layout` 加進選擇器清單後字串變了 | 排除 |
| `ScanExperience.jsx` 被影響 | 建置產物比對：兩版皆 **36390 bytes**，唯一差異是它 import 的 `index` chunk 檔名雜湊 | 排除 |
| `App.jsx` 改動 | 逐行看 diff，3 處純新增 | 排除 |
| 其他人未部署的前端變更被一併帶上線 | `git log 18c8540..70a6747 -- frontend/` 只有我的 commit | 排除 |
| `Meta.ordering` 的 `Case/When` 汙染 `values().annotate()` 的 GROUP BY | 實際印 SQL：GROUP BY 只有 `1` | 排除 |
| K8s 覆寫 `ARGUS_MEDIA_ROOT` 致 `relative_to` 失敗 | grep `k8s/*.yaml` 無此設定 | 排除 |

## 真正的根因

決定性線索是使用者補的那句「**SEO 的分析也沒有了**」——截圖與 SEO 的唯一共同點是**兩者都只來自逐頁掃描迴圈**。

`crawler.py`：

```
page_stage = "screenshot"
await page.screenshot(...)      # ← 失敗
...
pages.append({...})             # ← 永遠到不了
except Exception as exc:
    warnings["failed_urls"].append({"url": url, "reason": f"{page_stage}:..."})
```

**截圖在 `pages.append()` 之前執行，它的例外會被外層 `except Exception` 接住，整頁被丟掉。** 一頁都存不了截圖時，`crawled_pages` 就是空的：

| 現象 | 成因 |
|---|---|
| 截圖空白 | 沒有 `Page` 列 → 前端 `targetPage` 為 null → 連請求都不發 |
| SEO / AEO 分析消失 | 這兩類 finding **只**由 `analyze_page()` 逐頁產生 |
| 掃描仍顯示完成 | 只剩站台層級檢查（DNS/SSL/header），流程照走完 |

這是既有設計缺陷，**不是這次前端更新造成的**；最可能的觸發是 media volume 寫滿（截圖從專案開始就沒有任何清理機制）。

## 變更內容

### 1. `backend/apps/scans/crawler.py` — 隔離截圖失敗
- 新增 `_capture_screenshot()`：截圖失敗回 `None` 並記錄，不往上拋。頁面照常 `append`，`screenshot_path` 存空字串。
- 新增 `_prepare_screenshot_dir()`：建目錄失敗（磁碟滿、唯讀掛載）回 `None`，不讓整次掃描在爬第一頁前就失敗。
- 失敗記進 `warning_summary["screenshot_failures"]`，**不是 `failed_urls`**——那一頁其實抓到也分析過了，記錯地方會讓報告誤報成「頁面擷取失敗」。

### 2. `backend/apps/scans/reports.py` — 報告如實反映
「掃描警示」新增：「有 N 個頁面的截圖未能保存（不影響該頁的檢測結果，僅少了畫面佐證）」，措辭刻意與「頁面擷取失敗」分開。

### 3. 新增 `manage.py cleanup_screenshots`
`--older-than-days`（預設 90）、`--dry-run`。截圖是全頁擷取、體積遠大於報告，是 media volume 上真正無限成長的那一塊——我上一階段做了報告檔的保留期限卻沒注意到這點。

### 4. 新增測試
- `tests_crawler_screenshot.py`（6 項）：磁碟錯誤／逾時不拋出、記進 `screenshot_failures` 而非 `failed_urls`、建目錄失敗回 None。
- `tests_screenshot_cleanup.py`（3 項）：逾期刪除、未逾期保留、dry-run 不刪。用暫存 `MEDIA_ROOT`，不碰開發用的 `backend/media/`。
- `tests_report_content.py` +1：報告要報出截圖失敗且不得誤報成頁面擷取失敗。

### 5. 文件同步
`backend/apps/scans/CLAUDE.md`：新增「截圖失敗不得讓整頁分析作廢」章節，含三條硬規則與保留期限說明。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 761 tests，OK（skipped=1）**（前次 751，+10，無回歸）
- 控制流人工複核：截圖回 `None` 後仍走 `links` → `element_boxes` → `pages.append()`，`screenshot_path` 存空字串；既有的 `screenshot_path is not None` 判斷全部仍成立。

## 未處理／待決事項

- **尚未確認正式站的實際觸發原因**。需要在部署機執行：
  - `kubectl -n <ns> exec deploy/worker -- df -h /app/backend/media`
  - `kubectl -n <ns> logs deploy/worker | grep -iE "screenshot|No space|OSError"`
  - 或直接看最近一次報告的「掃描警示」章節有無「未抓到任何頁面」。
- **此修正只讓掃描在截圖失敗時仍能完整分析，不會讓截圖回來**。若確實是磁碟滿，仍須清理（`cleanup_screenshots`）或擴容。
- **`cleanup_screenshots` 與 `cleanup_reports` 都還沒接排程**（專案尚無 Celery beat）。
- 「0 個 finding = 100 分」與 worker rollout 砍掉進行中掃描兩項仍未處理。
