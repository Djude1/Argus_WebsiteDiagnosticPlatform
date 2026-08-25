# 專案介紹頁技術棧改為 4 欄全彩商標捲動牆

**日期**：2026-08-25  
**操作者**：Claude

## 變更內容

- 新增 `frontend/src/components/public/TechMarquee.jsx`：4 欄垂直 marquee，欄與欄反向、速度錯開（28/36/32/40s），hover 只暫停滑鼠所在那一欄。欄位用輪流（round-robin）分派而非連續切片，項目數不是 4 的倍數時各欄長度才不會差太多。
- 新增 `frontend/src/components/public/brandMarks.jsx`：21 個**多路徑全彩**品牌商標，內聯為 JSX，**不新增執行期相依套件**、也不需要 `dangerouslySetInnerHTML`。
  - 19 個取自 Iconify `logos` 集合（SVG Logos, CC0-1.0）；Celery 與 uv 該集合未收錄，改用 Simple Icons 的單一路徑填官方品牌色（這兩個商標本身就是單色）。
  - 各圖示的 `defs` id 都加 `am-<name>` 前綴，避免同頁多個漸層 id 互相覆蓋。
- `frontend/src/features/public/PublicPages.jsx`
  - `ProjectPage` 技術棧區塊：移除 `TECH_STACK_CHIPS` 彩色圓角 chip 列，改為「敘述 + 4 欄商標牆」共用同一張玻璃面板的構圖。
  - 保留原本的字：`技術棧` 當 eyebrow、`全棧現代化選型` 當標題（使用者要求拿掉「不偷工」，語氣太突兀）。
  - 新增 `PROJECT_STACK_POINTS`：3 條各約 20 字的短句，長度對齊參考頁的 bullets；取代原本只有標籤沒有說明的 chip。
  - Hero 次要 CTA：`/download`「下載 PWA」→ `/free-tools`「免登入先試單頁檢查」。
- `frontend/src/styles.css`
  - 新增 `.project-stack*`、`.tech-marquee*`、`.tech-tile*` 樣式與 `tech-marquee-up` / `tech-marquee-down` keyframes。
  - `.project-stack` 本身是唯一的玻璃面板（沿用 `.public-feature-card` 語言）；`.tech-tile` 不帶邊框與底色，只有 logo 圓形徽章 + 名稱，對齊參考頁右側純 `Avatar`、無卡片的做法。
  - 新增 `prefers-reduced-motion: reduce` 分支：關閉捲動與遮罩、隱藏循環用的複製區塊，退回靜態網格。
  - 移除 `.public-tech-chips` / `.public-tech-chip` 三處孤兒樣式（主樣式、`.public-shell` 放大規則、light theme 覆寫），改為對應的 `.tech-tile*` 規則。

## 原因

使用者指定參考 `TradingGoose-Studio` 首頁 `apps/tradinggoose/app/(landing)/components/integrations/integrations.tsx:177` 的 `relative grid shrink-0 grid-cols-4 gap-4`，把原本一整排彩虹色文字 chip 換掉。原設計的問題是 11 個標籤只有顏色差異、資訊密度低，且彩色 chip 與專案既有的 navy + cyan 科技風不一致。

第一版用 Simple Icons 的單色路徑做成灰階圖示，使用者反饋與參考的全彩商標牆差距明顯，因此改用全彩來源。

Hero 次要 CTA 改動的理由：hero 的次要按鈕應該給低承諾入口，而「下載 PWA」在 `PublicNav` 與 footer 都已經有入口。

## 影響範圍

- 只影響 `/project` 公開頁，其他頁面與後台未動。
- 技術項目從 11 個擴充為 21 個，全部對照 `pyproject.toml`、`frontend/package.json`、`frontend/Dockerfile`、`.github/workflows/`、`k8s/` 確認為專案實際使用；未收錄目前 disabled 的 Kali Linux 與純開發期的 Ruff。
- Zustand、DRF、Axios 沒有可用的全彩商標（devicon 的 Zustand / DRF 原圖分別是 124 KB、28 KB，40px 尺寸不划算；Axios 只有 6.8:1 的橫式字標），改在左側敘述文字中點名，不放進商標牆，也不用通用圖示假冒 logo。
- 深淺商標混排時有一半會糊在深底上，統一放在近白色圓形底板上呈現。
- 內聯 SVG 約 52 KB 原始碼，落在 lazy-load 的 `PublicPages` chunk：88.76 kB / gzip 32.02 kB，未逼近 `vite.config.js` 關注的 500 kB 門檻。

## 驗證方式

- `vite build`（在 `frontend/` 內執行）：pass，無警告。
- Playwright 截圖確認 1440px 深色 / 淺色主題、390px 手機、hover、`prefers-reduced-motion` 五種狀態。
- 21 個商標在靜態網格截圖中逐一確認可辨識；含漸層的 Python / Vite / Tailwind / Gunicorn 正常顯示，證明 id 前綴有效。
- 逐欄 hover 實測 `animationPlayState`：只有游標所在欄 `paused`，其餘三欄維持 `running`，移開後四欄全部恢復：pass。
- `prefers-reduced-motion: reduce` 下複製區塊可見數為 0、區塊改為靜態網格：pass。
- Hero 次要 CTA 實測 `["免登入先試單頁檢查", "/free-tools"]`：pass。
- 分屏寬度實測 768 / 860 / 960 / 1024 / 1280 / 1440：全部維持並排，文字欄與商標牆的垂直中線完全對齊（例如 960px 兩者中心皆為 225），無水平溢位。
- 過程中修掉五個問題：(-1) 半屏寬度（約 768–1280px）文字與商標牆上下錯開，兩個原因疊加：`.project-stack` 同時掛了 `.public-section`，其 `space-y-5` 會在第二個子元素加 `margin-top: 20px`，橫排 `items-center` 之下就是固定偏移 10px；以及 `.tech-marquee` 的 `shrink-0` + 固定寬度不肯讓寬度、把文字欄壓到 172–354px。→ 移除 `.public-section` class，兩個 flex 項目都改成 `md:flex-1` + `min-width: 0` 可縮，橫排斷點降到 `md`(768px) 讓半屏維持並排；(0) 左側敘述卡與右側 21 張 tile 卡形成兩組互相競爭的卡片系統，整段看起來像兩個分開的區塊 → 改為共用一張面板、tile 去卡片化；(1) marquee `width:100%` + `shrink-0` 把左欄擠成 0 寬 → 加 `max-width: 32rem`；(2) 窄螢幕用 `grid-cols-3` 導致第 4 欄折到第二列 → 固定 `grid-cols-4` 並縮小 tile；(3) 首版灰階圖示 → 換全彩商標來源。

- 附帶修掉：768–1023px 欄位過窄時 `PostgreSQL` 標籤撐爆欄寬（降字級 + `overflow-wrap: anywhere`）；條列折行時破折號跑到兩行中間（改 `items-start` + 固定 `mt-2.5`）。

## 未完成 / 待確認

- 尚未 commit，等使用者確認視覺後再一起提交。
- 專案介紹頁其他區塊（安全邊界、四維檢測、開發歷程）仍是原本的 emoji 圖示，本次未動——使用者先前已撤銷該範圍的改動。
- `docker-compose.yml` 的 `DJANGO_ALLOWED_HOSTS` 缺少 `ars.clouda.dpdns.org`（導致該網域所有 `/api/*` 回 400）尚未處理，與本次改動無關。
