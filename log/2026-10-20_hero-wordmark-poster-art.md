# 專案介紹頁 hero 字標改用海報的 ARGUS 藝術字

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- 從使用者提供的海報 SVG（第115401組－海報1）取出內嵌的 ARGUS 字標 PNG（720×108、RGBA 透明底），存為 `frontend/src/assets/argus-wordmark.png`（約 101 KB）。
- `frontend/src/features/public/PublicPages.jsx`：hero 的 `public-hero-wordmark` 由逐字動畫的 `<span>` 改為 `<img src={argusWordmark} alt="ARGUS" width="720" height="108">`（保留無障礙名稱）。
- `frontend/src/styles/70-home.css`：`.public-hero-wordmark` 改為圖片尺寸（依高度 `clamp(2.3rem,5.6vw,4.4rem)` 縮放、寬度 auto），保留整體浮起進場動畫與 `prefers-reduced-motion` 靜態；淺色主題加投影讓白色玻璃質感字標在亮底仍看得出邊緣。移除原本逐字 `> span` 的漸層填色規則。

## 原因
使用者要求把專案介紹頁（/project）最上面 hero 的 ARGUS 文字，改用海報中的 ARGUS 藝術字（三角形 A 內含藍色漸層、玻璃質感描邊）。這是使用者自己專題的品牌字標。

## 影響範圍
- 只影響 `/project`（與 `/` 共用的 `ProjectPage`）hero 最上面的品牌字標；其他頁面的品牌字（`ArgusLogo`／`ArgusMark`）不動。
- 字標改為圖片後不再有逐字 stagger，改為整體淡入上浮（與 public-shell 進場一致）。
- `/project` 是預先渲染頁，字標改成匯入資產的 `<img>`，SSR 與瀏覽器皆輸出相同 `<img>`，不影響 hydration。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning）。
- `npm run typecheck`：clean。
- `npx vitest run src/features/public/`：5 pass。
- 取出的 PNG 以 PNG IHDR 確認 720×108、colortype 6（RGBA，有 alpha 透明底）。
- 未自動驗證：實際畫面需 `build-node22.ps1`（禁用 `npm run build`）後由 CI 前端 image build 產出；部署後請在深色與淺色主題各看一次 /project hero，確認字標清晰、縮放比例正確、淺色底邊緣可辨。
