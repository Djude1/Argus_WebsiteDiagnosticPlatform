# 掃描 loader：黑底去背 + 放大，讓它融入淺色卡片

**日期**：2026-09-22  
**操作者**：Claude

## 變更內容
- 資產換新（舊的 `argus-loader.webp` / `argus-loader-still.webp` 刪除）：
  - `frontend/src/assets/argus-eye.webp` — 256×202、24 幀、2 秒循環、356 KB，**已去背（RGBA）**
  - `frontend/src/assets/argus-eye-still.webp` — 靜態首幀、32 KB
- `frontend/src/features/scans/ScanExperience.jsx`：import 與 `<picture>` 改用新資產，`width/height` 由 256×256 改為 256×202。
- `frontend/src/styles.css`：`.crawl-anim-eye` 移除深色方框（`background` / `border` / `box-shadow` / `object-fit: cover` / `transform: scale()`），改為單純 `width: 140px`（compact 104px）、`height: auto`，只保留一層淡 cyan `drop-shadow` 讓霓虹看起來會發光。

## 原因
使用者實際看到上線結果後的回饋：**「太小不明顯，且有黑色的背景，沒有融入到網站」**。

- 黑底問題：原稿是深 navy 底的霓虹眼，而 `.crawl-anim` 卡片是淺藍（`#f0f9ff → #eef2ff`）、外層 `.panel` 是白底，先前用「深色掃描視窗」把黑底包起來的作法，在淺色頁面上就是一個突兀的黑方塊。
- 去背作法：不能單純「暗色轉透明」——眼睛的**瞳孔與眼內暗部也是近黑色**，會被一起挖空。改用連通區域判斷（`scipy.ndimage.label`）：只有**從畫面邊緣連通**的暗區才視為背景，被亮部包圍的瞳孔保留；背景區的 alpha 再依亮度平滑淡出，保住霓虹光暈的柔邊。
- 太小問題：原稿 768×768 但內容 bbox 只有 738×583，上下是大片空白，等於在 56px 方框裡又浪費一截。裁掉透明邊界後同樣尺寸的視覺份量大得多，再把顯示寬度從 56px 提到 140px。

## 影響範圍
- 只影響掃描詳情頁「掃描進行中」的 `CrawlingAnimation` header；卡片其餘元素（標題、hint、進度條、chip 列、終止按鈕）維持原樣，不需要改成深色。
- 資產從 237 KB 增為 356 KB（alpha 通道讓 WebP 明顯變大）。曾試 384 寬／48 幀達 2140 KB，經尺寸×幀數×品質掃描後取 256×202／24 幀／q58 這一組；16 幀（8fps）光流會頓，不採用。
- 檔名改變（`argus-loader-*` → `argus-eye-*`）連帶讓 `ScanExperience` chunk hash 換新，順帶避開先前被污染的 CDN 快取網址。

## 驗證方式
- `npx vite build` 通過（13.07s），產出 `argus-eye-IXQvva_4.webp`（364.82 kB）、`argus-eye-still-0e27pH6_.webp`（32.69 kB）、`ScanExperience-BVaVK4GA.js`。
- 以 Pillow 把去背首幀合成到卡片實際底色上檢查：黑方塊消失、瞳孔與眼內暗部保留、光暈邊緣平滑無鋸齒；首幀透明像素佔 58.7%。
- 以 Pillow 模擬完整卡片版面（眼睛 + 標題 + hint + 進度條 + chip 列），比對 140px 與 56px，確認新尺寸是視覺主體且不擠壓文字。
- **待人工確認**：rollout 後在瀏覽器看實際播放流暢度，以及 140px 在窄螢幕上的表現。
