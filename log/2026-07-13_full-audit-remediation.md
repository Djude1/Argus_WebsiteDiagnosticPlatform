# 全專案稽核修復

**日期**：2026-07-13  
**操作者**：Codex

## 變更內容

- 建立統一 SSRF public target policy，覆蓋 crawler、redirect、子資源、WebSocket、外部 scanner 與安全掃描器。
- 強化評論圖片解碼/尺寸/像素/重新編碼與 media response header。
- 將購點預設關閉；選定綠界測試環境，加入 CheckMacValue、pending 訂單、ReturnURL 驗證與冪等入點，後台 `SimulatePaid=1` 通知不入點。
- 將 JWT 改為記憶體 access + HttpOnly refresh cookie，加入 CSRF、原子輪替、登出與密碼事件撤銷。
- 將 password reset 改為 HMAC digest 儲存與單次使用，加入 migration 清除舊 token。
- Production 改 Gunicorn + 一次性 migrate，強化 Compose/K8s secret、proxy、health、ingress/egress policy 與 CI quality gate。
- 修復 mobile admin drawer、表格、dialog、圖片鍵盤操作、Dashboard 公告、Google OAuth 缺設定降級與 intro deep-link。
- 修復 reviews N+1、掃描取消/完成競態、結算錯誤吞例外、proxy client IP 與 scheme 信任邊界。
- 加入 S3-compatible 評論圖片 storage、受控 egress proxy 設定與 Playwright proxy 傳遞，並將前端大型 vendor 分包。
- 將 8,000 行級 App.jsx 改成 React domain feature modules 與 route-level lazy loading，根 App 僅保留路由殼層。
- 同步 README、ONBOARDING、使用說明、各模組 CLAUDE、K8s 文件與專案記憶。
- 使用者後續解除 K8s 凍結後，將 NetworkPolicy 獨立為 `07-network-policies.yaml`，限制 CoreDNS、資料服務與公開 IPv4 出站，並補資料層 ingress、data deny-egress、CI render gate 與叢集封包驗證手冊。

## 原因

完整稽核指出 21 項安全、正確性、部署、效能、可用性與文件漂移問題；交接要求依風險順序修復並提供可重現驗證。

## 影響範圍

- 後端：accounts、billing、reviews、scans、insights、admin_api、config。
- 前端：登入、Dashboard、評論、購點、React admin、公開導覽與 PWA 資產。
- 部署：Dockerfile、Compose、Nginx、K8s、GitHub Actions、環境變數。
- 外部相依：綠界測試 MerchantID/HashKey/HashIV 與公開 ReturnURL、正式 media bucket/domain/credential、Compose/平台層 deny-direct-egress 與 K8s CNI enforcement 實測仍需部署端完成；正式金流不在本專題範圍。

## 驗證方式

- 完整後端測試 455 項：通過；另分別執行 billing 45 項及 scans/agent/reviews 341 項 targeted 測試，皆通過。
- Ruff 全 backend、Django check、migration drift、uv lock：通過。
- Frontend production build：通過（278 modules）；entry 9.94 kB / gzip 3.61 kB、最大 feature 52.44 kB / gzip 13.63 kB、最大 vendor 187.60 kB / gzip 61.29 kB，無警告或空 JS chunk。
- Docker Compose production/dev config：以一次性假環境值驗證通過；K8s Kustomize 可離線 render 7 個 NetworkPolicy，實際 CNI enforcement 需由部署叢集依手冊驗證。
- Browser 390px：document 375/375 無全頁溢位、table 351/680 局部捲動；drawer inert/焦點/escape、dialog 語意/焦點復原、圖片鍵盤入口通過。
- Browser 1440px：sidebar 256px、document 1440/1440，console error/warning 為 0。
- React 分檔後再次以 390px 登入、Dashboard 與 `/billing` smoke test；綠界測試方案按鈕可用、document 無橫向溢位、破圖與 console error/warning 均為 0，未送出外部付款表單。
- 三路獨立只讀 QA 重驗：綠界 URL 矩陣、出口/Agent/Kali、S3 settings/遠端 URL 的殘留問題皆為 0；精準測試分別 45、7、3 項通過。
- MD checklist：相對連結、MEMORY 索引、3 個 skill 索引/觸發規則、跨檔舊敘述掃描通過；修改檔 UTF-8 strict decode 通過。
- 變更檔敏感字串與 email log pattern 掃描：0 項。
