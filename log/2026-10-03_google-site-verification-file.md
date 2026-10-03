# 新增 Google Search Console HTML 驗證檔

**日期**：2026-10-03

## 變更內容

將網站管理者提供的 Google HTML 驗證檔，以 Google 指定的原檔名放入 `frontend/public/`，讓 Vite 產物與 frontend image 保留根路徑下的驗證檔。

## 原因

網站管理者要求將驗證檔發布至自己的網站，以完成 Google Search Console 的網址前置字元資源驗證。

## 影響範圍

僅新增靜態驗證檔，不修改應用程式、登入或掃描行為。驗證成功後仍須保留檔案。HTML 驗證適用於 GSC 網址前置字元資源；若使用 Argus 的網域層級 Google 驗證，另需符合該功能的網域資源與權限條件。

## 驗證方式

- 驗證檔的內容格式與檔名相符；public 與 dist 內的位元組均與來源一致。
- Node 22 production build、ESLint（0 errors，1 項既有 warning）、TypeScript 檢查通過。
- Vitest：17 個測試檔、155 項測試通過。
- 公網檔案仍需在 image 發布與部署後確認 HTTP 200 且內容與來源一致；不能只看狀態碼或 SPA fallback。
