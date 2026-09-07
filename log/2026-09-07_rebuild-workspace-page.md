# 複刻工作區獨立頁面（階段一）

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

- 新增 `frontend/src/features/scans/RebuildWorkspace.jsx` 與路由
  `/scans/:scanId/rebuild/:rebuildId`（`App.jsx` 以 `lazyNamed` 掛載，
  獨立 chunk 4.84 kB）
- 版面：左側 AI 思考過程（推理／工具／回覆三色分流、自動捲到最新）、
  右側產出預覽（原稿／優化版切換）＋下載
- **內容比對**：兩份都載入後直接標示「完全相同」或字元數變化
- polling 從 5 秒降到 **1 秒**（這一頁是使用者盯著看的畫面）
- `PageRebuildPanel` 側欄改為只顯示狀態與入口連結，思考流移到專屬頁
- 後端 `SiteRebuildDetailSerializer`：`trace` 只在單筆檢視回傳，列表不帶
- `_TRACE_MAX_CHARS` 400 → 1500（專屬頁面看得到完整內容）

## 原因

使用者回報思考流「不如 AI-Wealth-Manager 流暢」且「頁面比較緊湊」。

評估後分兩階段，本次是階段一。**沒有直接做真串流**：Argus 的 agent 呼叫跑在
Celery worker，瀏覽器連不到；要做到 AIWM 那種逐字流動，得補
`worker → Redis pub/sub → Django SSE → 瀏覽器`，而那會動到 Gunicorn 的 worker
class 與 gateway 的長連線超時——那是影響整站的改動，不該跟這個功能綁在一起。

1 秒 polling + 寬版面已經拿到大部分體感差距，風險低很多。

比對功能是順帶解掉使用者稍早踩的「優化版與原稿沒有差異」——有這個畫面，
同樣的問題下次一眼就會看見。

## 影響範圍

- 列表端點不再回傳 `trace`：任何依賴列表拿思考流的程式都要改用單筆端點
  （目前只有側欄面板，已一併調整）
- 產出預覽用 `<iframe sandbox="">`，**不加任何 `allow-*`**：這份 HTML 來自
  受測網站，必須在 opaque origin 內且完全不執行 script

## 驗證方式

- `apps.rebuild` 51 tests OK（新增「列表不得帶 trace」的回歸測試）
- 前端 `vite build` 通過；確認 `RebuildWorkspace-*.js` 獨立 chunk 產生，
  且「AI 思考過程」「兩份內容完全相同」「查看即時進度」與 `.rebuild-ws-*`
  樣式都進了 production bundle
- 換行完整性檢查通過

## 未驗證（需使用者）

- **畫面外觀沒有親眼看過**：這台沒有瀏覽器工具，只驗到進 bundle
- 階段二（真串流）尚未評估 Gunicorn 與 gateway 的超時設定
