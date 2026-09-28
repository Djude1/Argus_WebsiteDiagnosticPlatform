# mcp_access 模組規則

Claude Code 進 `backend/apps/mcp_access/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀。

會員透過 Claude Code、Codex 等本地 AI 工具，以 **MCP（Model Context Protocol）** 使用 Argus：查已驗證網域、估價、建立／取消掃描、查結果與報告。前端頁面是會員區 `/mcp`（`frontend/src/features/account/McpAccessPage.jsx`）。

---

## 端點

| 路徑 | 用途 | 驗證 |
|---|---|---|
| `POST /api/mcp/` | MCP Streamable HTTP 端點（JSON-RPC 2.0） | `Authorization: Bearer argus_mcp_…`（**只**吃 MCP 憑證，不吃 JWT／session，因此 `csrf_exempt`） |
| `GET /api/mcp/reports/<token>/` | `get_scan_report` 發出的短效報告下載連結 | `TimestampSigner` 簽章綁定 `scan_id:user_id`，`ARGUS_MCP_REPORT_LINK_TTL` 秒後失效 |
| `/api/mcp-access/overview/`、`keys/`、`keys/<id>/revoke/`、`connection/` | 會員頁管理 API | JWT（`IsAuthenticated`），只能看／改自己的憑證 |

協定採**無狀態**模式：POST 直接回 `application/json`，不開 SSE、不發 `Mcp-Session-Id`；GET／DELETE 回 405。這讓 Gunicorn（WSGI）即可承載，也是規格允許的最簡實作。支援 `initialize`、`ping`、`tools/list`、`tools/call`，通知一律 202；有 `Origin` 標頭時必須是 `ALLOWED_HOSTS` 允許的主機（規格要求的 DNS rebinding 防護）。協定版本清單在 `protocol.SUPPORTED_PROTOCOL_VERSIONS`。

## 權益：每一次請求都重新判定

`entitlements.get_entitlement(user)`：

1. 帳號 `is_active`
2. 先跑 `settle_subscription_safe`，再要求訂閱 `status ∈ {active, cancelled}` 且 `now < current_period_end`（已取消的訂閱保留到當期結束）
3. `tools/call` 另查本月額度（`ARGUS_MCP_PLAN_QUOTAS`，查無方案用 `ARGUS_MCP_DEFAULT_MONTHLY_CALLS`；台北時間月份）與每分鐘上限（`ARGUS_MCP_RATE_PER_MINUTE`，cache 計數）

入口（`views.mcp_endpoint`）：無／錯憑證 → 401＋`WWW-Authenticate`；無權益 → 403；任何請求（含 initialize）每分鐘超過工具上限 × 4 → 429（避免反覆 initialize 灌爆呼叫紀錄）。額度與頻率超過時回 `isError=true` 的工具結果（讓 AI 工具看得到原因），不是 HTTP 錯誤。

**只有 `tools/call` 計入額度**（`McpCallLog.counted=True`）；initialize／tools/list 不計；伺服器內部錯誤不計；工具回報的業務錯誤（找不到掃描、點數不足…）計入。

## 工具必須沿用既有路徑（不得另寫一套）

| 工具 | 沿用 |
|---|---|
| `create_scan` | `ScanJobCreateSerializer`（授權聲明、SSRF、點數檢查＋`hold_for_scan`、主動模式網域所有權閘門、第三方網域再確認、`AuthorizationConsent`）＋ `scans.views.enqueue_created_scan`（派工失敗 → `fail_scan_job_before_start` 全額退款） |
| `cancel_scan` | `scans.tasks.request_scan_cancel`（合作式取消＋`refund_full_for_scan`） |
| `get_scan_report` | `scans.views.ensure_report_file`（快取規則與防偽編號與網頁下載相同） |
| `estimate_scan` | `billing.services.estimate_scan_cost`／`agent_ux_fee` |
| `get_scan_findings` | 證據一律過 `reports.mask_pii_evidence` 再截斷 |

`create_scan` 必須帶 `confirm_authorization=true`；主動模式等同網頁勾選主動授權，仍要過網域所有權驗證。所有查詢以 `user=` 篩選，他人的掃描一律回「找不到」。

## 憑證

- 格式 `argus_mcp_` ＋ `secrets.token_urlsafe(32)`；DB 只存 SHA-256（高熵亂數不需慢雜湊）與辨識用前綴
- 明文只在建立 API 的回應出現一次；前端只放在頁面記憶體
- 每人有效憑證上限 `ARGUS_MCP_MAX_KEYS`；撤銷＝寫 `revoked_at`，下一次請求即 401
- 建立憑證需要有效權益；撤銷不需要（訂閱到期後仍能清掉舊憑證）

## 設定（皆有預設值，`.env.example` 有列）

`ARGUS_MCP_ENABLED`、`ARGUS_MCP_DEFAULT_MONTHLY_CALLS`、`ARGUS_MCP_PLAN_QUOTAS`（`方案代碼:次數,…`）、`ARGUS_MCP_MAX_KEYS`、`ARGUS_MCP_RATE_PER_MINUTE`、`ARGUS_MCP_REPORT_LINK_TTL`、`ARGUS_MCP_PUBLIC_BASE_URL`（反向代理鏈沒轉送 https 時固定對外網址）。

## 驗證方式

- 單元測試：`uv run python backend/manage.py test apps.mcp_access`
- 真實用戶端（2026-09-28 已驗證）：官方 MCP Python SDK（Streamable HTTP）、Claude Code（`claude mcp add --transport http …` → `claude mcp list` 顯示 Connected；`claude -p --mcp-config …` 實際呼叫工具）、`mcp-remote`（stdio 橋接，供 Claude Desktop）。Codex 已驗證 `codex mcp add --url … --bearer-token-env-var …` 寫出的設定，實際呼叫需 OpenAI 登入。

## 禁止事項

| 禁止 | 原因 |
|---|---|
| 讓 `/api/mcp/` 接受 JWT 或 session cookie | 端點 `csrf_exempt`，吃 cookie 就是 CSRF 洞 |
| 在工具裡直接建 `ScanJob`、直接改 `CoinWallet` 或 `ScanJob.status` | 繞過授權／計費／退款與狀態機；一律走上表的既有函式 |
| 只在建立憑證時檢查訂閱 | 訂閱到期、帳號停用後憑證仍可用 |
| 在回應、log 或 `McpCallLog.detail` 放憑證明文 | 憑證等同帳號操作權 |
