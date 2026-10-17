# 正式環境實機驗證 runbook（分支 claude/relaxed-hypatia-8xjr49）

本輪 7 項改動（跨層去重、ZAP 主動觀測性、authz BOLA 探測、ADR-0005 第 1–4 刀）都**無法在開發容器
實機驗證**（沒有真目標／worker／ZAP／真模型）。本檔列出在**正式環境**照著跑一次授權全站掃描即可
確認「有生效、沒退步」的具體訊號。操作者執行。

> 前置：需把本分支部署到正式環境——合併 → backend image build → bot 回寫 `k8s/kustomization.yaml`
> → Argo Sync/Health → PreSync `migrate` Job `Completed/0`（本輪**無新 migration**，應為 no-op）→
> web/worker pod rollout。部署驗證矩陣見 `k8s/README.md`。本輪無 model／計費／migration 變更。

## 0. 建議的驗證掃描設定
挑一個**已完成網域驗證**的授權測試目標，跑「**全站＋主動＋勾全部維度（含資安）**」。
要完整驗到 agent 與 ZAP 主動，正式環境需另設（本輪不改這些預設）：
- `ARGUS_AGENT_ENABLED=true`（Hermes，驗第 2 刀）
- `ARGUS_ZAP_ENABLED=true` 且 ZAP daemon 連得到（驗 ZAP 主動觀測性）
- `ARGUS_ZAP_ACTIVE_ENABLED=true`（要真的跑主動掃描才設）

## 1. crawler 外部 JS 秘鑰（第 1 刀）
- **設**：無（預設生效）。目標最好是有外部 .js bundle 且內含金鑰樣式的站。
- **看**：掃描詳情出現 `exposure-hardcoded-secret` 或 `exposure-browser-api-key`，證據來源標 `js_bundle`、
  位置是某個 .js URL。掃描 log 的 deep_security 階段問題數包含它。
- **沒退步**：原本 HTML／inline script 的秘鑰偵測照常。

## 2. agent 吃確定性發現、不重報（第 2 刀）
- **設**：`ARGUS_AGENT_ENABLED=true`，授權全站主動掃描。
- **看**：`warning_summary.agent` 有 steps/issues；agent 的 `agent-observed-security-*` 發現**不應**與
  確定性層（exposure/nuclei/authz）同一端點重複。若仍有同端點重複，`cross_layer` 會在計分前刪掉，
  掃描 log 出現「跨層去重：N 筆 Agent 觀察與確定性探測指向同一端點」。
- **判讀**：這是 prompt 層改動，效益看「agent 有沒有少重報」，對照同目標改動前後的 agent issues。

## 3. 退 ZAP 被動 ＋ 自家被動檢查（第 3 刀）
- **看覆蓋**：`ScanJob.coverage.checks` **不應**再出現 `zap_passive`（已退役）。
- **看自家被動新檢查**（視目標而定，只讀已抓頁面）：
  - `security-mixed-content`（HTTPS 頁載 http:// 子資源）
  - `security-sensitive-url-param`（網址查詢字串帶 token/password 等）
  - `security-error-disclosure`（頁面含堆疊追蹤／框架除錯頁）
  - `header-permissions-policy`（缺 Permissions-Policy 標頭，幾乎每站都會有，低）
- **沒退步（關鍵）**：拿一個**改動前會被 ZAP 被動報混合內容／Permissions-Policy** 的目標對照——
  現在應由上述自家 rule_id 報出等價問題，不該整個消失。
- **工具版本**：若跑了 ZAP 主動，`warning_summary.tools["OWASP ZAP"]` 由主動階段寫入（被動已不寫）。

## 4. authz 探測端點上限可調（第 4 刀）
- **設**：預設 `ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS=60`。
- **看**：對有「多個 API 端點」的授權目標，覆蓋 `authz_probe=completed`；掃描 log「未授權存取探測完成：
  探測 N 個 API 端點」，N 可達 60（改動前上限 20）。

## 5. authz BOLA 確定性探測（本輪稍早）
- **看**：若目標有「無需登入就回成批帳號／成員記錄」的 API →出現 `security-unauth-api-records`
  （含 PII／password/token/身分證升 high，否則 medium）。覆蓋 `authz_probe`。
- **沒誤報（關鍵）**：公開 JSON 清單、公開人員目錄、姓名＋email 清單、單筆**不應**被報。

## 6. ZAP 主動觀測性（本輪稍早）
- **看**：勾資安但未開 `ARGUS_ZAP_ACTIVE_ENABLED`／未授權／ZAP 未部署時，覆蓋 `zap_active=skipped`
  並帶原因（旗標／授權／部署）。開啟並授權時才 `completed`／`partial`。

## 7. 跨層去重（本輪稍早）
- **看**：同一個 API 文件端點若被確定性 `exposure-file-apidoc` 與 agent 各抓到一次，最終只留確定性那筆，
  掃描 log 出現「跨層去重」。報告與問題清單不再同端點列兩次。

## 整體不退步檢查
- 全站掃描跑完、`completed`、有分數；`coverage` 無 `zap_passive`、有 `authz_probe`。
- 和改動前同目標比：資安發現**總數不應莫名變少**（ZAP 被動退役的部分應由自家 rule 補回）。
- 掃描時間不應暴增（本輪沒放寬 Nuclei；authz 60 端點 ÷ RPS 約 +30 秒）。

## 回滾
本輪純程式／設定、無 migration。回滾＝部署前一版 image。新設定（`ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS`）
不設則用預設 60；要回到舊行為設 20。
