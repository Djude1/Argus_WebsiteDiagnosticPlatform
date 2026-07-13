# 2026-07 全專案稽核修復

## 範圍

依 `FULL_PROJECT_DESIGN_BUG_AUDIT.md` 與 2026-07-12 remediation playbook，處理 SSRF、上傳、金流、JWT/密碼重設、部署、前端 RWD/可及性、CI、N+1、proxy 與文件漂移。

## 核心決策

- 掃描目標採單一 public HTTP policy，對主文件、redirect、子資源、WebSocket 與外部 scanner 重驗證；Katana/Nuclei 停止跟隨 redirect。DNS rebinding 的解析/連線 TOCTOU 仍須 production egress proxy/firewall。
- 圖片只接受 JPEG/PNG/WebP，限制 5 MiB、4096 px、16 MP；Pillow 完整解碼、EXIF 轉正並重新編碼，media 回應加 `nosniff` 與 sandbox CSP。評論圖片已可由 `ARGUS_MEDIA_STORAGE_BACKEND` 切換至 S3-compatible storage；正式 bucket、credential 與獨立 media domain 仍是 infra 工作。
- `ARGUS_PAYMENT_MODE` 預設 `disabled`；專題付款選定綠界 `payment-stage`。`ecpay_test` 建立 pending 訂單，ReturnURL 驗證 CheckMacValue、商店、訂單與金額後才冪等入點；`SimulatePaid=1` 禁止入點。
- Access JWT 只存在 Zustand 記憶體；refresh 只用 HttpOnly cookie + CSRF，原子輪替。登出、變更密碼與密碼重設撤銷 refresh。
- Password reset DB 只保存以獨立 pepper 計算的 HMAC digest；migration 清除舊 plaintext token。
- Production 使用 Gunicorn 與一次性 migrate；Compose 不公開 DB port、不放 production 密碼；K8s 加 probe 與 7 個 ingress/egress NetworkPolicy。
- Client IP 只信任可信直連 proxy；`X-Forwarded-Proto` 也先經 middleware 驗證直連來源。K8s `TRUSTED_PROXY_CIDRS` 必須和實際 Pod CIDR 一致。
- 掃描 worker 以條件更新推進起始/完成狀態，避免取消任務復活；結算/退款錯誤不得吞掉。
- Admin mobile 使用 drawer、focus trap、inert 與局部表格捲動；後台 modal 具 dialog 語意、Escape、焦點圈限與復原。
- 前端已改為 React domain 分層與 route-level lazy loading；`App.jsx` 164 行，auth/scans/account/public/admin/404/intro 各自產生 chunk，導覽與掃描徽章也有清楚的具名元件，vendor 依模組 ID 穩定分組。
- `ARGUS_EGRESS_PROXY_URL` 可讓 HTTP client、外部 scanner 與 Playwright 走受控 proxy；這是應用層路由能力，不取代部署網路的 deny-direct-egress 規則。

## 外部待辦

1. 綠界測試商店需由部署者在 `.env` 提供測試 MerchantID / HashKey / HashIV 與公開 HTTPS ReturnURL；正式商店不在本專題範圍。
2. K8s 已加入 frontend/migrate/application/data egress 邊界與 web/PostgreSQL/Redis ingress 白名單；仍需組員在實際 CNI 執行 `k8s/README.md` 的允許/阻擋封包矩陣。Compose/其他平台也須配置等效 firewall。
3. 建立正式 S3-compatible bucket、最小權限 credential、生命週期與獨立 media domain，然後切換環境變數。
4. 若單一 feature 日後持續膨脹，再依 domain 抽出具名頁面元件；不得回退成 App.jsx 單檔。

## 驗證

- 完整後端測試：455 項通過；另有 billing 45 項及 scans/agent/reviews 341 項 targeted 測試通過。
- Ruff、Django check、migration drift、uv lock：全部通過。
- Frontend production build：278 modules；entry 9.94 kB、最大 feature 52.44 kB、最大 vendor 187.60 kB，無警告或空 JS chunk。
- Compose production/dev merge：以一次性假環境值驗證通過；K8s Kustomize render 7 個 NetworkPolicy，實際 CNI enforcement 待部署端驗證。
- 瀏覽器：390px/1440px admin、drawer/inert/focus、dialog、local table scroll、Google OAuth 降級與 console 檢查通過。
