# Top bar RWD：nav 連結收行斷點 900px → 1140px

**日期**：2026-06-10
**操作者**：Claude

## 變更內容

- `frontend/src/styles.css`：把登入後導覽列（`.argus-nav`）「連結列收到第二行、全寬可橫向捲動」
  的規則，從 `@media (max-width: 900px)` 拆出，獨立成 `@media (max-width: 1140px)`：
  `.argus-nav-inner`、`.argus-brand`、`.argus-brand-title`、`.argus-brand-sub`（隱藏）、
  `.argus-nav-links`（order:3 / width:100% / overflow-x:auto）、`.argus-nav-link`、
  `.coin-chip / .install-chip / .nav-logout-btn`。
- 原 `@media (max-width: 900px)` 只保留非 nav 的規則（`.argus-main` padding、`.scan-layout.list-mode`
  改 block、`.scope-grid / .billing-plan-grid` 改單欄），維持不變。

## 原因

使用者回報：約 **634–1133px** 之間（介於既有 640 與 desktop 之間）登入後 top bar 的連結與 brand
擠在一起、換行雜亂，希望此區間呈現與 <634px 一致的「連結獨佔一列、可橫向捲動」樣式。
原斷點 900px 沒涵蓋 900–1133px，故把 nav 收行斷點提高到 1140px（>1133）。

## 影響範圍

- 僅影響登入後 `.argus-nav` top bar 在 901–1140px 的呈現（連結改為獨立全寬列）。
- **不影響** scan 版面 / 方案格等其餘 900px 規則（仍維持 ≤900px 觸發）。
- 純前端 CSS，需 build 後生效。

## 驗證方式

- 本機 `docker compose -p argusnew up -d --build frontend` 重建成功（exit 0）。
- `/dashboard`、`/team`、`/download` 皆回 HTTP 200。
- CSS bundle 含 `max-width:1140px`。
- 需使用者肉眼確認：瀏覽器寬度 ~700–1130px 時，top bar 連結收成獨立一列、可橫向捲動。
