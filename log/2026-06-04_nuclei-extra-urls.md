# Nuclei 改為整批掃描所有爬取頁面（extra_urls）

**日期**：2026-06-04
**操作者**：Claude

## 變更內容

- 修改 `backend/apps/scans/nuclei_scanner.py`：
  - 新增 `extra_urls: list[str] | None = None` 參數
  - 單一 URL 繼續用 `-u`；多 URL 寫入 temp file 並用 `-l` 旗標整批傳入
  - 加入 `import os / import tempfile`
  - temp file 在 `finally` 區塊確保清除（即使例外也不留殘檔）
  - URL 以 `dict.fromkeys()` 去重，入口 URL 始終排第一
  - 新增 `Nuclei 完成（模式）：N 項發現` log 行（方便除錯）
- 修改 `backend/apps/scans/tasks.py`：
  - 在呼叫 `run_nuclei()` 前收集 `crawled_urls`（排除 `blocked_reason` 的頁面）
  - 傳入 `extra_urls=crawled_urls`
- 新增 `backend/apps/scans/tests_nuclei_scanner.py` 測試（3 項）：
  - `test_single_url_uses_u_flag`：無 extra_urls 時確認使用 `-u` 旗標
  - `test_extra_urls_uses_l_flag_with_temp_file`：多 URL 時確認使用 `-l`、temp file 執行時存在且執行後刪除
  - `test_extra_urls_deduplicates_entry_url`：入口 URL 重複出現在 extra_urls 時不應重複

## 原因

之前 Nuclei 只掃入口 URL（`-u entry_url`），爬取到的其他頁面（如 `/admin/`、`/product/1`、`/purchase`）完全不在 Nuclei 掃描範圍內，導致覆蓋率不足。

## 影響範圍

- Nuclei 現在對所有已爬取頁面執行模板掃描，提升覆蓋率
- 無 extra_urls（如單頁模式）行為不變，backward compatible
- 整合測試（掃描 `aiglasses.qzz.io`）：Nuclei 確實收到 10 個 URL（用 `-l`），7 秒完成

## 驗證方式

- `uv run python backend/manage.py test apps.scans.tests_nuclei_scanner -v 2` → 11/11 通過 ✅
- 實際掃描日誌顯示 `Nuclei 完成（快速（免費））：0 項發現`（新日誌行，代表有正確執行）✅

## 已知限制

**Cloudflare 保護的網站，Nuclei 仍為 0 項**：Cloudflare WAF/Bot Protection 識別 Nuclei 的探針請求特徵並攔截，導致所有 matcher 不觸發。這是 Nuclei 對 CDN 保護網站的既知限制，並非程式 bug。未受 CDN 保護的網站（如 `testphp.vulnweb.com`）將受益於多 URL 掃描。
