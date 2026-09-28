import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  checkMcpConnection,
  createMcpKey,
  fetchMcpOverview,
  revokeMcpKey,
} from "../../api";
import { apiErrorMessage, useConfirmDialogs } from "../../shared/AppShared";
import { copyToClipboard } from "../../shared/clipboard";
import { formatDate, formatDateTime, formatNumber } from "../../shared/formatters";

// ============================================================
// MCP 接入中心（/mcp）
// 流程：選擇工具 → 複製設定（需要一把憑證）→ 驗證連線（等待用戶端真的連上來）。
// 權益、額度與每次呼叫的檢查都在後端（apps/mcp_access），這頁只負責引導與管理。
// ============================================================

const KEY_PLACEHOLDER = "<你的 Argus MCP 憑證>";
const VERIFY_TIMEOUT_MS = 3 * 60 * 1000;
const VERIFY_INTERVAL_MS = 3000;

// 每種用戶端的設定方式；url／key 由頁面帶入
const CLIENTS = [
  {
    id: "claude-code",
    label: "Claude Code",
    where: "在專案目錄的終端機執行（加上 --scope user 可在所有專案使用）：",
    lang: "bash",
    snippet: (url, key) =>
      `claude mcp add --transport http argus ${url} \\\n  --header "Authorization: Bearer ${key}"`,
    verify: "執行 claude mcp list，看到 argus 顯示 ✓ Connected 即完成；也可以直接請 Claude「用 argus 查我的帳號狀態」。",
  },
  {
    id: "codex",
    label: "Codex",
    where: "把憑證放進環境變數，再用 codex mcp add 登記（寫入 ~/.codex/config.toml）：",
    lang: "bash",
    snippet: (url, key) =>
      `export ARGUS_MCP_TOKEN="${key}"\ncodex mcp add argus --url ${url} \\\n  --bearer-token-env-var ARGUS_MCP_TOKEN`,
    verify: "在同一個終端機啟動 codex（需能讀到 ARGUS_MCP_TOKEN），請它「用 argus 列出我的掃描」，即會送出第一次呼叫。",
  },
  {
    id: "cursor",
    label: "Cursor",
    where: "寫入 ~/.cursor/mcp.json（或專案的 .cursor/mcp.json）：",
    lang: "json",
    snippet: (url, key) => JSON.stringify(
      { mcpServers: { argus: { url, headers: { Authorization: `Bearer ${key}` } } } },
      null,
      2,
    ),
    verify: "重新載入 Cursor 後，在 MCP 設定中確認 argus 已啟用，再請它呼叫一次 argus 的工具。",
  },
  {
    id: "vscode",
    label: "VS Code",
    where: "寫入專案的 .vscode/mcp.json（GitHub Copilot 代理模式）：",
    lang: "json",
    snippet: (url, key) => JSON.stringify(
      { servers: { argus: { type: "http", url, headers: { Authorization: `Bearer ${key}` } } } },
      null,
      2,
    ),
    verify: "在 VS Code 啟動 argus 伺服器後，於代理模式請它呼叫一次 argus 的工具。",
  },
  {
    id: "claude-desktop",
    label: "Claude Desktop",
    where: "Claude Desktop 以本機程序連線，透過 mcp-remote 轉接（需要 Node.js）。寫入 claude_desktop_config.json：",
    lang: "json",
    snippet: (url, key) => JSON.stringify(
      {
        mcpServers: {
          argus: {
            command: "npx",
            args: ["-y", "mcp-remote", url, "--header", "Authorization:${ARGUS_AUTH}"],
            env: { ARGUS_AUTH: `Bearer ${key}` },
          },
        },
      },
      null,
      2,
    ),
    verify: "重新啟動 Claude Desktop，在工具清單中看到 argus 即完成。",
  },
  {
    id: "curl",
    label: "其他／curl",
    where: "任何支援 Streamable HTTP 的 MCP 用戶端都能連。也可以先用 curl 測試：",
    lang: "bash",
    snippet: (url, key) =>
      `curl -s ${url} \\\n  -H "Authorization: Bearer ${key}" \\\n  -H "Content-Type: application/json" \\\n  -H "Accept: application/json, text/event-stream" \\\n  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'`,
    verify: "回應中出現 \"serverInfo\":{\"name\":\"argus\"…} 即代表憑證與訂閱都有效。",
  },
];

const OUTCOME_LABELS = {
  ok: "成功",
  tool_error: "工具回報錯誤",
  quota_exceeded: "超過本月額度",
  rate_limited: "呼叫過於頻繁",
  invalid: "未通過權益檢查",
};

const SUB_STATUS_LABELS = { active: "生效中", cancelled: "已取消（本期仍可用）", expired: "已到期" };

function CopyBlock({ text, label }) {
  const [state, setState] = useState("");
  async function copy() {
    setState((await copyToClipboard(text)) ? "已複製" : "複製失敗，請手動選取");
    window.setTimeout(() => setState(""), 2000);
  }
  return (
    <div className="mcp-copy">
      <pre className="mcp-code"><code>{text}</code></pre>
      <button type="button" className="secondary-button mcp-copy-btn" onClick={copy} aria-label={`複製${label}`}>
        {state || "複製"}
      </button>
    </div>
  );
}

function UsageMeter({ used, quota }) {
  const pct = quota > 0 ? Math.min(Math.round((used / quota) * 100), 100) : 0;
  const tone = pct >= 90 ? "tone-bad" : pct >= 70 ? "tone-warn" : "tone-good";
  return (
    <div className="mcp-meter" role="meter" aria-valuemin={0} aria-valuemax={quota} aria-valuenow={used}
      aria-label="本月 MCP 呼叫用量">
      {/* 動態計算值：用量百分比 */}
      <span className={`mcp-meter-fill ${tone}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function ConnectionCheck({ keyId, client }) {
  const [state, setState] = useState({ phase: "idle", calls: [] });
  const timer = useRef(null);
  const stop = useCallback(() => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);
  useEffect(() => stop, [stop]);

  function start() {
    stop();
    const since = new Date().toISOString();
    const deadline = Date.now() + VERIFY_TIMEOUT_MS;
    setState({ phase: "waiting", calls: [] });
    const poll = async () => {
      try {
        const data = await checkMcpConnection(since, keyId);
        if (data.tool_called || data.connected) {
          setState({ phase: data.tool_called ? "tool" : "connected", calls: data.calls });
          if (data.tool_called) return;
        }
      } catch {
        // 暫時性錯誤就繼續等，逾時才停止
      }
      if (Date.now() > deadline) {
        setState((prev) => (prev.phase === "waiting" ? { phase: "timeout", calls: [] } : prev));
        return;
      }
      timer.current = window.setTimeout(poll, VERIFY_INTERVAL_MS);
    };
    poll();
  }

  const clientName = state.calls.find((c) => c.method === "initialize")?.detail;
  return (
    <div className="mcp-verify">
      <p className="set-hint">{client.verify}</p>
      <div className="mcp-verify-row">
        {state.phase === "waiting" ? (
          <button type="button" className="secondary-button" onClick={() => { stop(); setState({ phase: "idle", calls: [] }); }}>
            停止等待
          </button>
        ) : (
          <button type="button" className="primary-button" onClick={start}>
            {state.phase === "idle" ? "開始驗證連線" : "重新驗證"}
          </button>
        )}
        <p className={`mcp-verify-status is-${state.phase}`} role="status" aria-live="polite">
          {state.phase === "idle" && "按下後，在你的工具中連線或呼叫一次 Argus，這裡會即時顯示結果。"}
          {state.phase === "waiting" && (
            <>
              <span className="mcp-spinner" aria-hidden="true" />
              等待 {client.label} 連線…（最多 3 分鐘）
            </>
          )}
          {state.phase === "connected" && `已連線${clientName ? `（${clientName}）` : ""}，等待第一次工具呼叫…`}
          {state.phase === "tool" && `連線成功，已收到工具呼叫${clientName ? `（${clientName}）` : ""}。`}
          {state.phase === "timeout" && "3 分鐘內沒有收到連線。請確認設定中的網址與憑證，並重新啟動工具後再試一次。"}
        </p>
      </div>
    </div>
  );
}

function McpAccessPage() {
  const { confirmDialog, dialogHost } = useConfirmDialogs();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [clientId, setClientId] = useState(CLIENTS[0].id);
  const [keyName, setKeyName] = useState("");
  const [creating, setCreating] = useState(false);
  const [keyError, setKeyError] = useState("");
  // 剛建立的憑證明文：只存在這個畫面的記憶體，離開頁面就消失
  const [newKey, setNewKey] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await fetchMcpOverview());
      setLoadError("");
    } catch (err) {
      setLoadError(apiErrorMessage(err, "無法載入 MCP 接入資訊。"));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const client = CLIENTS.find((c) => c.id === clientId) || CLIENTS[0];

  async function handleCreate(e) {
    e.preventDefault();
    setCreating(true);
    setKeyError("");
    try {
      const result = await createMcpKey(keyName.trim() || client.label);
      setNewKey({ id: result.key.id, secret: result.secret, name: result.key.name });
      setKeyName("");
      await load();
    } catch (err) {
      setKeyError(apiErrorMessage(err, "建立憑證失敗。"));
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(key) {
    const ok = await confirmDialog(
      `撤銷「${key.name}」（${key.prefix}…）？使用這把憑證的工具會立即無法連線，此操作無法復原。`,
      { danger: true },
    );
    if (!ok) return;
    try {
      await revokeMcpKey(key.id);
      if (newKey?.id === key.id) setNewKey(null);
      await load();
    } catch (err) {
      setKeyError(apiErrorMessage(err, "撤銷失敗。"));
    }
  }

  if (loadError) {
    return (
      <div className="acct-page">
        <p className="set-msg tone-bad" role="alert">{loadError}</p>
        <button type="button" className="secondary-button" onClick={load}>重試</button>
      </div>
    );
  }
  if (!data) {
    return <div className="acct-page"><p className="set-hint">載入中…</p></div>;
  }

  const ent = data.entitlement;
  const activeKeys = data.keys.filter((k) => k.is_active);
  const url = data.endpoint_url;
  const snippet = client.snippet(url, newKey?.secret || KEY_PLACEHOLDER);

  return (
    <div className="acct-page mcp-page">
      <header className="acct-page-head">
        <div>
          <p className="ag-eyebrow">MCP</p>
          <h1 className="acct-page-title">MCP 接入中心</h1>
          <p className="acct-page-sub">
            讓 Claude Code、Codex 等本地 AI 工具直接查詢已驗證網域、估價並建立掃描、讀取結果與報告。
            掃描的授權聲明、網域驗證、點數預扣與退款規則和網站上完全相同。
          </p>
        </div>
      </header>

      <div className="set-layout">
        <aside className="set-summary">
          <section className="set-card">
            <p className="set-card-label">訂閱狀態</p>
            {ent.plan_name ? (
              <>
                <p className="set-value">{ent.plan_name}</p>
                <p className="set-hint">
                  {SUB_STATUS_LABELS[ent.subscription_status] || ent.subscription_status}
                  {ent.paid_through ? ` · 權益至 ${formatDate(ent.paid_through)}` : ""}
                </p>
              </>
            ) : (
              <p className="set-value">尚未訂閱</p>
            )}
            <span className={`mcp-badge ${ent.allowed ? "is-on" : "is-off"}`}>
              {ent.allowed ? "MCP 可使用" : "MCP 未開通"}
            </span>
          </section>

          <section className="set-card">
            <p className="set-card-label">本月用量</p>
            <p className="set-wallet-balance ag-num">
              {formatNumber(ent.used_this_month)}<span> / {formatNumber(ent.monthly_quota)} 次</span>
            </p>
            <UsageMeter used={ent.used_this_month} quota={ent.monthly_quota} />
            <p className="set-hint">
              只計工具呼叫（連線與列出工具不計），{formatDate(ent.period_end)} 重置；
              每分鐘最多 {data.rate_per_minute} 次。掃描費用另依點數計算。
            </p>
          </section>

          <section className="set-card">
            <p className="set-card-label">MCP 端點</p>
            <p className="set-readonly">{url}</p>
            <p className="set-hint">Streamable HTTP，以 Authorization: Bearer 憑證驗證。</p>
          </section>
        </aside>

        <main className="set-main">
          {!ent.allowed && (
            <section className="set-section mcp-locked">
              <div className="set-section-head">
                <h2>開通 MCP 接入</h2>
                <p>{ent.reason}</p>
              </div>
              <div className="set-form-actions">
                <Link to="/billing" className="primary-button">前往訂閱方案</Link>
              </div>
            </section>
          )}

          <section className="set-section" aria-labelledby="mcp-steps-title">
            <div className="set-section-head">
              <h2 id="mcp-steps-title">三步驟接上 Argus</h2>
              <p>選擇你使用的工具，複製設定，然後讓工具連一次，確認連線成功。</p>
            </div>

            <ol className="mcp-steps">
              <li className="mcp-step">
                <h3 className="mcp-step-title"><span className="mcp-step-no">1</span>選擇工具</h3>
                <div className="mcp-client-bar" role="tablist" aria-label="MCP 用戶端">
                  {CLIENTS.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      role="tab"
                      aria-selected={c.id === clientId}
                      className={`mcp-client-tab ${c.id === clientId ? "active" : ""}`}
                      onClick={() => setClientId(c.id)}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </li>

              <li className="mcp-step">
                <h3 className="mcp-step-title"><span className="mcp-step-no">2</span>複製設定</h3>
                {newKey ? (
                  <div className="mcp-secret" role="status">
                    <p>
                      <strong>新憑證「{newKey.name}」已建立，只會顯示這一次。</strong>
                      下方設定已自動帶入；請妥善保存，遺失只能撤銷後重建。
                    </p>
                    <CopyBlock text={newKey.secret} label="憑證" />
                  </div>
                ) : (
                  <form className="mcp-key-form" onSubmit={handleCreate}>
                    <p className="set-hint">
                      設定需要一把憑證。建立後會自動填入下方設定（已有憑證可直接把 {KEY_PLACEHOLDER} 換成它）。
                    </p>
                    <div className="mcp-key-form-row">
                      <label className="set-field">
                        <span className="set-label">憑證名稱</span>
                        <input
                          className="input"
                          value={keyName}
                          onChange={(e) => setKeyName(e.target.value)}
                          placeholder={`例如：${client.label}（公司筆電）`}
                          maxLength={60}
                          disabled={!ent.allowed}
                        />
                      </label>
                      <button
                        type="submit"
                        className="primary-button"
                        disabled={!ent.allowed || creating || activeKeys.length >= data.max_keys}
                      >
                        {creating ? "建立中…" : "建立憑證"}
                      </button>
                    </div>
                    {activeKeys.length >= data.max_keys && (
                      <p className="set-hint">已達 {data.max_keys} 把有效憑證上限，請先撤銷不用的憑證。</p>
                    )}
                  </form>
                )}
                {keyError && <p className="set-msg tone-bad" role="alert">{keyError}</p>}
                <p className="set-hint">{client.where}</p>
                <CopyBlock text={snippet} label={`${client.label} 設定`} />
              </li>

              <li className="mcp-step">
                <h3 className="mcp-step-title"><span className="mcp-step-no">3</span>驗證連線</h3>
                <ConnectionCheck key={`${clientId}-${newKey?.id || ""}`} keyId={newKey?.id} client={client} />
              </li>
            </ol>
          </section>

          <section className="set-section" aria-labelledby="mcp-keys-title">
            <div className="set-section-head">
              <h2 id="mcp-keys-title">憑證管理</h2>
              <p>
                有效憑證 {activeKeys.length} / {data.max_keys} 把。建議每個工具或裝置各用一把，
                遺失或不再使用時立即撤銷；撤銷後下一次呼叫就會被拒絕。
              </p>
            </div>
            {data.keys.length === 0 ? (
              <p className="set-hint">還沒有憑證。</p>
            ) : (
              <div className="mcp-table-wrap">
                <table className="mcp-table">
                  <thead>
                    <tr>
                      <th scope="col">名稱</th>
                      <th scope="col">憑證</th>
                      <th scope="col">建立</th>
                      <th scope="col">最後使用</th>
                      <th scope="col">狀態</th>
                      <th scope="col" aria-label="操作" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.keys.map((k) => (
                      <tr key={k.id} className={k.is_active ? "" : "is-revoked"}>
                        <td>{k.name}</td>
                        <td className="mcp-mono">{k.prefix}…</td>
                        <td>{formatDate(k.created_at)}</td>
                        <td>
                          {k.last_used_at ? formatDateTime(k.last_used_at) : "尚未使用"}
                          {k.last_client && <small className="mcp-sub">{k.last_client}</small>}
                        </td>
                        <td>
                          <span className={`mcp-badge ${k.is_active ? "is-on" : "is-off"}`}>
                            {k.is_active ? "有效" : `已撤銷 ${formatDate(k.revoked_at)}`}
                          </span>
                        </td>
                        <td>
                          {k.is_active && (
                            <button type="button" className="mcp-danger-link" onClick={() => handleRevoke(k)}>
                              撤銷
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="set-section" aria-labelledby="mcp-calls-title">
            <div className="set-section-head">
              <h2 id="mcp-calls-title">最近呼叫</h2>
              <p>最近 20 次連線與工具呼叫；建立的掃描可直接點開查看。</p>
            </div>
            {data.recent_calls.length === 0 ? (
              <p className="set-hint">還沒有任何呼叫。</p>
            ) : (
              <ul className="mcp-calls">
                {data.recent_calls.map((c) => (
                  <li key={c.id} className="mcp-call">
                    <span className="mcp-call-time">{formatDateTime(c.created_at)}</span>
                    <span className="mcp-mono">{c.tool || c.method}</span>
                    <span className={`mcp-badge ${c.outcome === "ok" ? "is-on" : "is-off"}`}>
                      {OUTCOME_LABELS[c.outcome] || c.outcome}
                    </span>
                    {c.scan_id && <Link to={`/scans/${c.scan_id}`} className="mcp-call-link">掃描 #{c.scan_id} →</Link>}
                    {c.detail && <small className="mcp-sub">{c.detail}</small>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="set-section" aria-labelledby="mcp-tools-title">
            <div className="set-section-head">
              <h2 id="mcp-tools-title">可用工具（{data.tools.length}）</h2>
              <p>AI 工具會依你的指示自行選用；會預扣點數或變更掃描狀態的工具已標示。</p>
            </div>
            <ul className="mcp-tools">
              {data.tools.map((t) => (
                <li key={t.name} className="mcp-tool">
                  <div className="mcp-tool-head">
                    <strong>{t.title}</strong>
                    {!t.read_only && <span className="mcp-badge is-warn">會變更資料</span>}
                  </div>
                  <code className="mcp-mono">{t.name}</code>
                  <p>{t.description}</p>
                </li>
              ))}
            </ul>
          </section>
        </main>
      </div>
      {dialogHost}
    </div>
  );
}

export default McpAccessPage;
export { McpAccessPage };
