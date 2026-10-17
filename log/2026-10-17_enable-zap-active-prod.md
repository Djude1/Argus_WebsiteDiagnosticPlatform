# 正式環境預設啟用 OWASP ZAP 主動掃描

**日期**：2026-10-17
**操作者**：Claude
**來源**：使用者指示「zap_active 預設要開」。

## 做法（沿用被動 ZAP 的既有模式）
依專案慣例——攻擊型能力**程式預設關**（本機／CI 不需要 ZAP），**正式環境以 K8s ConfigMap 開**：
- `k8s/01-namespace-config.yaml` 加 `ARGUS_ZAP_ACTIVE_ENABLED: "true"`。
- `k8s/04-backend.yaml` worker 的 `argus.io/config-revision` bump 成 `zap-active-2026-10-17`，強制 worker rollout 吃到新設定（zap_active 跑在 worker）。
- **`backend/config/settings.py` 的 `ARGUS_ZAP_ACTIVE_ENABLED` 預設維持 `False` 不動**。

## 為什麼不需新增前置
`active_enabled() = ARGUS_ZAP_ACTIVE_ENABLED and zap_passive.enabled()`。被動 ZAP 早已啟用，因此其依賴
**全部現成**：ZAP 服務（`12-zap-passive.yaml`）、`argus-zap/zap-api` Secret＋`argus-secret` 的
`ARGUS_ZAP_API_KEY`、worker 出站網路政策（`07` 的 `worker-egress-to-zap`）。本次只多開主動旗標。

## 行為與授權邊界（不變）
只對「全站＋主動模式＋網域已驗證」的授權掃描送攻擊 payload（`scan_plan.run_zap_active`＝`site_active`，
與 Nuclei／Kali 同一組閘）；被動、單頁、未驗證網域一律不送主動流量。先用爬蟲 HAR 建站台樹繞過 CF
再攻擊；逾時／取消照常清理。

## 時間影響（需告知）
會為**授權主動掃描**額外增加約 spider 120s＋active 600s（`ARGUS_ZAP_ACTIVE_TIMEOUT_SECONDS`／
`_SPIDER_SECONDS`）。與本日稍早的掃描提速方向相反——提速省下的是 CF 後 Nuclei 的 ~13 分，這裡為授權
主動掃描加回最多約 ~12 分。對「只被動／未驗證網域」的掃描無影響。

## 部署性質
**k8s-only 變更**：不觸發 image build，走 Argo CD sync；config-revision bump 觸發 worker 重啟。
回滾：ConfigMap 設 `ARGUS_ZAP_ACTIVE_ENABLED="false"` 並重啟 worker。

## 驗證
- `k8s/01`、`k8s/04` YAML 可解析；ConfigMap 值與 config-revision 已確認。
- 程式層無改動（settings 預設仍 False）；既有 `tests_zap_active.py` 不受影響。
- 實機確認（使用者）：worker 重啟後，對已驗證網域跑全站主動掃描，應出現 `zap_active` 階段實際執行
  （非 skipped），報告出現來源標「主動掃描」的 finding；ZAP Pod 無 CreateContainerConfigError。

## 備註
不含真實站名／路徑／內網 IP／任何機密值。
