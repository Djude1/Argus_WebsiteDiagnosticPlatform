# Nuclei 偵測到 WAF 保護時自動新增說明 finding

**日期**：2026-06-04
**操作者**：Claude

## 變更內容

- 修改 `backend/apps/scans/tasks.py`：
  - 在合併 katana + nuclei findings 前，加入 WAF 偵測邏輯
  - 條件：`nuclei_findings` 為空 **且** `katana_tech` 中包含已知 WAF / CDN 關鍵字
  - 已知 WAF 清單：`cloudflare`, `fastly`, `akamai`, `aws waf`, `imperva`, `sucuri`, `f5`
  - 觸發時產生一個 `info` / `security` finding，說明 Nuclei 探針遭攔截、保護機制有效
  - 同步新增執行日誌：`偵測到 WAF 保護（...），Nuclei 探針可能被攔截，已新增說明 finding`

## 原因

掃描 Cloudflare 保護的網站時，Nuclei 回傳 0 項，但使用者看不出是「真的沒問題」還是「探針被擋掉」。加入此 finding 後：
1. 使用者看到明確說明，知道我們確實執行了掃描
2. 正向定調：被攔截代表 WAF 有效，是好事
3. 提供行動建議（staging 環境或 WAF IP 例外）

## finding 範例

```
標題：Nuclei 資安掃描受 WAF / CDN 保護攔截（Cloudflare、Cloudflare Browser Insights）
說明：偵測到 Cloudflare、Cloudflare Browser Insights 等 WAF / CDN 保護機制，
     Nuclei 對 11 個頁面發出的主動探針請求可能被攔截，導致掃描回傳 0 項發現。
     這表示您的網站已部署有效的入侵防護，屬正向安全指標。
修補方向：此為資訊性提示，無需修復。如需完整弱點掃描，建議在 WAF 規則中
         加入可信掃描來源 IP 的例外，或在 staging 環境（無 WAF）執行深度資安稽核。
```

## 驗證方式

- 掃描 `aiglasses.qzz.io`（受 Cloudflare 保護）：
  - 執行日誌顯示「偵測到 WAF 保護...，已新增說明 finding」✅
  - `資安補充掃描完成：Nuclei 1 項`（從 0 → 1）✅
  - Findings 列表出現 `info SECURITY Nuclei 資安掃描受 WAF / CDN 保護攔截 (...)` ✅
  - 完整說明面板正確顯示 WAF 名稱、描述、修補方向 ✅
