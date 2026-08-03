# 後台概覽頁面板升級：品牌敘事、監控波形圖、圖示化面板標頭

**日期**：2026-08-03
**操作者**：Claude
**呼叫者**：無檔案 import 此變更涉及的內部函式（`App.jsx` 只 lazy import 整個 `AdminPages.jsx` 模組）；純 UI 呈現層，無資料檔案異動。

## 背景

使用者對前一輪 icon／背景色修正的回饋：面板仍然「很簡單樸素、一看就是 AI 生成的」，要求要有明顯系統特色與品牌設計水準，作為畢業專題需能跟評委介紹「用心與特別設計之處」。

## 變更內容(可跟評委介紹的設計重點)

1. **品牌敘事貫穿頁首**：`/admin/overview` 標題旁新增「Argus 即時監控中」狀態徽章(cyan 淡底 + 綠點 pulse)。呼應 Argus(希臘神話百眼巨人,永不闔眼的守衛者)品牌意涵——後台是「一直在看」的監控台,非單純資料頁。這是後台唯一常駐動畫,且僅用於傳達真實系統狀態(非裝飾),符合尊重 `prefers-reduced-motion` 與「後台動效克制、只留功能性回饋」的既有設計準則。
2. **視覺語言貫穿全站卡片**:`.admin-panel`(4 個內容面板:14 天活動、AI Provider 用量、Top 10 AI 用戶、最近購買)補上與 `.admin-stat-card` 相同手法的頂部 cyan 微光條 + 角落 ⟡ 品牌浮水印(4% 透明度)。兩種卡片、sidebar 頂部微光,三處共用同一視覺 DNA,是可以直接跟評委說明的「系統一致性」設計證據。
3. **監控波形圖升級**(`AdminMiniChart`):原本是無填色的裸折線圖,現在改為**漸層區域填色 + 端點光點**(SOC 監控台常見樣式,貼合「網站安全診斷平台」的產品定位),3 條線疊層漸層透明度足夠低,不互相干擾閱讀。
4. **面板標頭圖示化**:4 個內容面板標頭補上與 sidebar nav 同一套 icon 系統的圖示(新增 `AdminOrdersIcon` 收據圖示、`AdminTokensIcon` 晶片+閃電圖示、`AdminTrendIcon` 趨勢折線圖示),讓 sidebar 導覽圖示與頁面內容圖示是「同一套語言」而非兩套不相關的視覺系統。
5. **Stat card 加圖示**:6 張 stat card 各補上對應語意圖示(人像/硬幣/收據/雷達/晶片/星星),且圖示顏色會隨卡片 tone(cyan/good/warn)自動變色,呼應頂條顏色。
6. **移除殘留離品牌色**:圖表「訂單金額」線與 Provider 用量長條原本用 `#6366f1`(indigo,AI 生成後台的典型顏色,未曾被前兩輪配色重設觸及)改為 `--tone-good`/cyan token,去除全站最後一處離品牌色殘留。

## 檔案

- `frontend/src/components/admin/AdminIcons.jsx`:新增 `AdminOrdersIcon`、`AdminTokensIcon`、`AdminTrendIcon`。
- `frontend/src/features/admin/AdminPages.jsx`:`AdminStatCard` 支援 `icon` prop;`AdminMiniChart` 加漸層區域填色與端點光點;`AdminOverviewPage` 加狀態徽章、面板標頭圖示、圖表配色修正。
- `frontend/src/styles.css`:新增 `--argus-brand-mark` 共用 token(去重複 data-URI)、`.admin-status-badge`/`.admin-status-dot`/`@keyframes admin-status-pulse`、`.admin-panel::before/::after`、`.admin-panel-icon`、`.admin-stat-head`/`.admin-stat-icon`,圖例與長條顏色改用品牌 token。

## 驗證方式

- `npm run build`(WSL/Linux Node 20):✓ 2039 modules、4.73s、無錯誤
- `docker compose build frontend && docker compose up -d --no-deps frontend`:成功(過程中遇到 Docker Desktop WSL credsStore 暫時性 `exec format error`,以 `DOCKER_CONFIG` 指向暫存空設定繞過,未動使用者機器上的 `~/.docker/config.json`)
- curl 已部署 bundle 逐項確認:狀態徽章文字、新 icon path、CSS 新 class 均已在線上生效;舊離品牌色 `#6366f1` 在該 chunk 中已完全消失
- **仍無法完成**:環境無 Chrome,無法截圖做視覺自我檢查
- **待使用者手動確認**(需登入 staff + 強制重新整理):`/admin/overview` 整體觀感是否已達到可以跟評委介紹的水準
