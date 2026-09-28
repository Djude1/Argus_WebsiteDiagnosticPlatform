# 品牌標誌還原、首頁 hero 還原、購點／訂閱開放檢測

**日期**：2026-09-27
**操作者**：Claude

## 變更內容
- `frontend/src/components/brand/ArgusMark.tsx`：`ArgusLogo` 改用 `assets/brand-logo.webp`，`ArgusMark` 改用 `assets/argus-eye-still.webp`（登入頁眼睛圖示、狀態圖示、空狀態）；不再使用向量杏眼標誌。`05-brand.css` 同步改為圖片樣式（日間主題以 filter 壓暗；後台側欄維持原色）。
- 專案介紹頁 hero 還原為改版前的掃描動畫（argus-eye.webp 動圖、ARGUS 逐字浮現、光球、網格漂移、掃描線、四角框）。規則取自改版前 01/21/31/33/40/41/70 號檔，改名為 `classic-hero-*` 放在新檔 `34-classic-hero.css`，避免與其他公開頁共用的 `.public-hero` 衝突。移除不再使用的 `HeroQuickCheck` 元件與 `70-home.css` 的 `home-hero*`／`home-quick*` 規則。
- `IntroSequence.jsx`、`public/favicon.svg`、`public/pwa-icon.svg` 還原為改版前版本；`33-intro-hero-brand.css` 只保留 `.argus-intro*` 規則。
- 新增 `scripts/billing_e2e_check.py`：購點與訂閱端到端檢測腳本（獨立實作 CheckMacValue，綠界憑證從 `.env` 讀取）。
- `docs/brand-guidelines.md` 標誌章節改為使用原品牌圖。

## 原因
使用者認為向量標誌太卡通，要求改回原本的 brand-logo.webp／argus-eye-still.webp，並把首頁上方的主題掃描動畫改回原版；同時要求開放購點與訂閱服務並進行檢測。

## 影響範圍
- 所有使用 `ArgusLogo`／`ArgusMark` 的頁面（公開頁導覽列與頁尾、登入頁、會員區導覽、後台側欄、狀態／空狀態圖示）改顯示原品牌圖。
- 購點／訂閱的開關是後端 `ARGUS_PAYMENT_MODE`：`k8s/01-namespace-config.yaml` 已為 `ecpay_test`，正式環境另需 live `argus-secret` 具備 `ECPAY_MERCHANT_ID`／`ECPAY_HASH_KEY`／`ECPAY_HASH_IV`，否則 Django 會拒絕啟動。本次未修改程式預設值（`.env.example` 維持 `disabled`，依 billing/CLAUDE.md 規則憑證只放 `.env`）。

## 驗證方式
- 前端：`npm run lint`、`npm run typecheck`、`npm test`（148 項）、`vite build` 全部通過；1440／390 寬、深／淺主題截圖確認 hero 與 logo。
- 後端：`uv run python backend/manage.py test apps.billing` 78 項通過。
- 端到端（本機 runserver，`ARGUS_PAYMENT_MODE=ecpay_test` ＋綠界公開測試商店 3002607）：`scripts/billing_e2e_check.py` 24/24 通過——CheckMacValue 與綠界官方文件範例一致；購點建立 pending 訂單並導向 payment-stage；偽造簽章、竄改金額、模擬付款、付款失敗的回呼都不入點；成功付款入點且重複回呼冪等；訂閱首月入點、取消訂閱冪等。
- 介面（Playwright，Vite + 真實後端）：購點頁無「服務暫停」提示；購點三步驟 wizard 送出綠界 Stage 表單（MerchantID 3002607、金額 450）；訂閱確認後顯示「生效中」，coin 200 → 500。
- 未能驗證：沙箱無法連線綠界 payment-stage 與正式站，實際刷卡頁與正式環境設定需人工確認。
