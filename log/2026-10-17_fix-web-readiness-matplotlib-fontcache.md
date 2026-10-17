# 修 web readiness probe 逾時：預建 matplotlib 字型快取＋放寬 probe

**日期**：2026-10-17
**操作者**：Claude
**來源**：正式機 web pod readiness probe `context deadline exceeded`、標 Unhealthy。

## 根因（web pod log 時間軸）
```
14:38:55 gunicorn 啟動、2 個 gthread worker boot
14:39:19~20 matplotlib font_manager: generated new fontManager  ← 啟動後約 25 秒才完成
```
matplotlib **首次 import 時現掃系統字型建快取**（noto-cjk／NotoColorEmoji／unifont 等大檔），
正式機約 25 秒，期間處理該 import 的 gunicorn worker 被卡住。readiness probe `initialDelaySeconds:15`
＋**預設 `timeoutSeconds` 只有 1 秒**，剛好打在這段 → 逾時、pod 被標 Unhealthy，直到快取建好才恢復。
這是**每個新 pod 首啟**都會踩的事，與近期掃描提速／ZAP 等改動無關（報告用 matplotlib 畫圖，
`report_render/theme.py` import 時設定字型）。

## 修法
1. **預建字型快取並烤進 image（根因）**：`Dockerfile` 在裝完 `fonts-noto-cjk` 後設
   `ENV MPLCONFIGDIR=/app/.matplotlib` 並 `python -c "import matplotlib.pyplot"`，把 `fontlist-*.json`
   建進 image。runtime 讀同一份、不再現掃。app／k8s 都沒另設 MPLCONFIGDIR，ENV 在 build 與 runtime
   一致生效（已 grep 確認）。本容器實測預建會寫出 `fontlist-v3.11.0.json`。
2. **放寬 probe（防護，`k8s/04-backend.yaml` web）**：readiness／liveness 都加 `timeoutSeconds: 5`、
   `failureThreshold: 3`；liveness `periodSeconds` 20→30。單核＋2 worker 下，一次報告 PDF 轉檔
   （LibreOffice 吃 CPU）就可能讓 `SELECT 1` 健康檢查擠不進 1 秒；liveness 1 秒逾時更會誤殺正在
   服務的 pod。

## 部署性質
- Dockerfile 改動 → 觸發 **backend image build**，成功後 bot 回寫 kustomization、Argo sync。
- `k8s/04` probe 改動是 Deployment template，Argo sync 時 web rollout 自動帶上。
- 兩者都要等 image build 完才完整生效；probe 放寬在下次 web rollout 立即生效。

## 驗證
- `k8s/04-backend.yaml` YAML 可解析；Dockerfile 預建指令在本容器實測成功（約 4.6s，正式機字型更多會久一些，但只在 build 一次）。
- 實機確認（使用者）：新 image rollout 後，web pod log **不再出現** `generated new fontManager`；
  readiness 啟動即過、不再 flap。

## 備註
不含真實站名／路徑／機密值；pod 名稱與 IP 屬叢集內部、未寫入。
