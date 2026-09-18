import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  createVerifiedDomain,
  deleteVerifiedDomain,
  fetchVerifiedDomains,
  verifyVerifiedDomain,
} from "../../api";
import { apiErrorMessage, useConfirmDialogs } from "../../shared/AppShared.jsx";

// ============================================================
// 網域所有權驗證頁（/domains）
// 主動式資安測試僅限已通過驗證的網站；本頁負責「新增 → 設定 → 驗證」三段流程。
// ============================================================

// 顯示狀態（綜合 status＋is_effectively_verified）：
// 生效中（人工核准或已驗證未過期）→ verified；verified 但已失效 → expired
const STATUS_LABELS = {
  pending: "待驗證",
  verified: "已驗證",
  rejected: "已否決",
  expired: "已過期",
};

// 三種驗證方法（與後端 VerifiedDomain.Method 對齊）
const METHOD_OPTIONS = [
  { value: "dns_txt", label: "DNS TXT" },
  { value: "meta_tag", label: "meta 標籤" },
  { value: "html_file", label: "驗證檔" },
];

const METHOD_LABELS = {
  dns_txt: "DNS TXT 記錄",
  meta_tag: "HTML meta 標籤",
  html_file: "驗證檔案",
};

function displayStatus(domain) {
  if (domain.is_effectively_verified) return "verified";
  if (domain.status === "verified") return "expired";
  return domain.status;
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("zh-Hant", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  });
}

// 一鍵複製：優先 clipboard API，不支援（如非 HTTPS 環境）時退回 execCommand
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      // 動態計算值：移出視野避免頁面跳動，屬必要 inline style
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(textarea);
      return ok;
    } catch {
      return false;
    }
  }
}

// 單一欄位（標籤 + 值 + 一鍵複製）
function CopyField({ label, value, copiedKey, onCopy }) {
  return (
    <div className="domain-ins-field">
      <dt>{label}</dt>
      <dd>
        <code>{value}</code>
        <button
          type="button"
          className={`domain-copy-btn ${copiedKey === value ? "is-copied" : ""}`}
          onClick={() => onCopy(value)}
          aria-label={`複製${label}`}
        >
          {copiedKey === value ? "已複製 ✓" : "複製"}
        </button>
      </dd>
    </div>
  );
}

// 後端 instructions 的三方法頁籤渲染
function VerificationInstructions({ data, methodTab, onTabChange, copiedKey, onCopy }) {
  const instructions = data.instructions || {};
  const token = data.token || "";

  return (
    <section className="panel domain-instructions">
      <div className="domain-ins-head">
        <div>
          <p className="eyebrow">步驟 2 · 設定驗證資料</p>
          <h2 className="section-title">{data.domain}</h2>
          <p className="domain-ins-lead">
            用以下任一種方法證明你控制這個網域（三選一即可），設定完成後回到下方清單按「驗證」。
          </p>
        </div>
        <div className="domain-token-box">
          <span className="domain-token-label">專屬驗證 Token</span>
          <code>{token}</code>
          <button
            type="button"
            className={`domain-copy-btn ${copiedKey === token ? "is-copied" : ""}`}
            onClick={() => onCopy(token)}
          >
            {copiedKey === token ? "已複製 ✓" : "複製"}
          </button>
        </div>
      </div>

      <div className="domain-ins-tabs" role="tablist" aria-label="驗證方法">
        {METHOD_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={methodTab === option.value}
            className={`domain-ins-tab ${methodTab === option.value ? "active" : ""}`}
            onClick={() => onTabChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {methodTab === "dns_txt" && instructions.dns_txt && (
        <div className="domain-ins-panel" role="tabpanel">
          <p className="domain-ins-hint">到你的 DNS 管理介面新增一筆 TXT 記錄：</p>
          <dl className="domain-ins-fields">
            <CopyField label="記錄名稱（Host）" value={instructions.dns_txt.record_name} copiedKey={copiedKey} onCopy={onCopy} />
            <CopyField label="記錄類型（Type）" value={instructions.dns_txt.record_type} copiedKey={copiedKey} onCopy={onCopy} />
            <CopyField label="記錄值（Value）" value={instructions.dns_txt.value} copiedKey={copiedKey} onCopy={onCopy} />
          </dl>
          <p className="domain-ins-note">DNS 傳播需要一點時間，設定後若馬上驗證失敗，等幾分鐘再試一次。</p>
        </div>
      )}

      {methodTab === "meta_tag" && instructions.meta_tag && (
        <div className="domain-ins-panel" role="tabpanel">
          <p className="domain-ins-hint">
            將以下標籤放入{instructions.meta_tag.location}：
          </p>
          <div className="domain-ins-code-wrap">
            <pre className="domain-ins-code">{instructions.meta_tag.snippet}</pre>
            <button
              type="button"
              className={`domain-copy-btn ${copiedKey === instructions.meta_tag.snippet ? "is-copied" : ""}`}
              onClick={() => onCopy(instructions.meta_tag.snippet)}
            >
              {copiedKey === instructions.meta_tag.snippet ? "已複製 ✓" : "複製原始碼"}
            </button>
          </div>
        </div>
      )}

      {methodTab === "html_file" && instructions.html_file && (
        <div className="domain-ins-panel" role="tabpanel">
          <p className="domain-ins-hint">在網站根目錄建立指定路徑的驗證檔，內容即為 Token：</p>
          <dl className="domain-ins-fields">
            <CopyField label="檔案路徑" value={instructions.html_file.path} copiedKey={copiedKey} onCopy={onCopy} />
            <CopyField label="完整網址" value={instructions.html_file.url} copiedKey={copiedKey} onCopy={onCopy} />
            <CopyField label="檔案內容" value={instructions.html_file.content} copiedKey={copiedKey} onCopy={onCopy} />
          </dl>
        </div>
      )}
    </section>
  );
}

export function DomainVerifyPage() {
  const navigate = useNavigate();
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();
  const [domains, setDomains] = useState(null); // null = 載入中
  const [listError, setListError] = useState("");
  const [newDomain, setNewDomain] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [justAdded, setJustAdded] = useState(null); // { ...網域欄位, token, instructions }
  const [methodTab, setMethodTab] = useState("dns_txt");
  const [copiedKey, setCopiedKey] = useState("");
  const copiedTimer = useRef(null);
  const [verifyMethod, setVerifyMethod] = useState({}); // domainId -> 方法
  const [verifyBusyId, setVerifyBusyId] = useState(null);
  const [verifyFlash, setVerifyFlash] = useState({}); // domainId -> { ok, message }
  const [deletingId, setDeletingId] = useState(null);

  async function loadDomains() {
    setListError("");
    try {
      const data = await fetchVerifiedDomains();
      setDomains(data.results || []);
    } catch (err) {
      setDomains([]);
      setListError(apiErrorMessage(err, "載入網域清單失敗，請重新整理再試。"));
    }
  }

  useEffect(() => {
    loadDomains();
  }, []);

  useEffect(() => () => clearTimeout(copiedTimer.current), []);

  async function handleCopy(text) {
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopiedKey(text);
      clearTimeout(copiedTimer.current);
      copiedTimer.current = setTimeout(() => setCopiedKey(""), 2000);
    } else {
      notifyDialog("複製失敗，請手動選取文字複製。");
    }
  }

  async function handleCreate(event) {
    event.preventDefault();
    const value = newDomain.trim();
    if (!value) {
      setCreateError("請先輸入網域，例如 example.com");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const data = await createVerifiedDomain(value);
      setJustAdded(data);
      setMethodTab("dns_txt");
      setNewDomain("");
      await loadDomains();
    } catch (err) {
      setJustAdded(null);
      setCreateError(apiErrorMessage(err, "新增網域失敗，請確認網域格式正確。"));
    } finally {
      setCreating(false);
    }
  }

  // 以目前選的方法執行驗證：成功綠色閃示、失敗顯示後端 last_error
  async function handleVerify(domain) {
    const method = verifyMethod[domain.id] || "dns_txt";
    setVerifyBusyId(domain.id);
    setVerifyFlash((flash) => ({ ...flash, [domain.id]: null }));
    try {
      const data = await verifyVerifiedDomain(domain.id, method);
      setDomains((list) =>
        (list || []).map((item) => (item.id === domain.id ? { ...item, ...data } : item)),
      );
      setJustAdded((current) =>
        current && current.id === domain.id ? { ...current, ...data } : current,
      );
      if (data.verified) {
        setVerifyFlash((flash) => ({
          ...flash,
          [domain.id]: { ok: true, message: "驗證成功！此網域（含子網域）已可使用主動式資安測試。" },
        }));
      } else {
        setVerifyFlash((flash) => ({
          ...flash,
          [domain.id]: {
            ok: false,
            message: `驗證未通過：${data.last_error || "找不到驗證資料，請確認設定後再試。"}`,
          },
        }));
      }
    } catch (err) {
      notifyDialog(apiErrorMessage(err, "驗證執行失敗，請稍後再試。"));
    } finally {
      setVerifyBusyId(null);
    }
  }

  async function handleDelete(domain) {
    const ok = await confirmDialog(
      `確定刪除網域「${domain.domain}」？刪除後若要再進行主動式測試，需重新加入並驗證。`,
      { danger: true },
    );
    if (!ok) return;
    setDeletingId(domain.id);
    try {
      await deleteVerifiedDomain(domain.id);
      setDomains((list) => (list || []).filter((item) => item.id !== domain.id));
      setJustAdded((current) => (current && current.id === domain.id ? null : current));
    } catch (err) {
      notifyDialog(apiErrorMessage(err, "刪除失敗，請稍後再試。"));
    } finally {
      setDeletingId(null);
    }
  }

  const pendingCount = useMemo(
    () => (domains || []).filter((item) => !item.is_effectively_verified && item.status !== "rejected").length,
    [domains],
  );

  return (
    <div className="domain-page">
      <button
        type="button"
        className="domain-back"
        onClick={() => navigate("/dashboard")}
      >
        ← 返回 Dashboard
      </button>

      <header className="domain-header">
        <p className="eyebrow">所有權證明</p>
        <h1 className="domain-title">網域驗證</h1>
        <p className="domain-lead">
          主動式資安測試僅限已通過所有權驗證的網站。
          證明你擁有網域後，該網域與其子網域即可啟用主動測試模式。
        </p>
        <ol className="domain-steps" aria-label="驗證流程">
          <li className="domain-step"><span aria-hidden="true">1</span>新增網域</li>
          <li className="domain-step" aria-hidden="true">→</li>
          <li className="domain-step"><span aria-hidden="true">2</span>設定驗證資料</li>
          <li className="domain-step" aria-hidden="true">→</li>
          <li className="domain-step"><span aria-hidden="true">3</span>執行驗證</li>
        </ol>
      </header>

      <form className="panel domain-add" onSubmit={handleCreate}>
        <div>
          <p className="eyebrow">步驟 1 · 新增網域</p>
          <h2 className="section-title">加入你要驗證的網域</h2>
          <p className="domain-add-hint">輸入註冊網域即可（不用含 www 或路徑），例如 example.com。</p>
        </div>
        <div className="domain-add-row">
          <input
            className="input"
            type="text"
            placeholder="example.com"
            value={newDomain}
            onChange={(event) => setNewDomain(event.target.value)}
            aria-label="網域名稱"
            autoComplete="off"
            spellCheck="false"
          />
          <button className="primary-button" type="submit" disabled={creating}>
            {creating ? "新增中…" : "新增網域"}
          </button>
        </div>
        {createError && <p className="error-text">{createError}</p>}
      </form>

      {justAdded && (
        <VerificationInstructions
          data={justAdded}
          methodTab={methodTab}
          onTabChange={setMethodTab}
          copiedKey={copiedKey}
          onCopy={handleCopy}
        />
      )}

      <section className="panel domain-list-panel">
        <div className="domain-list-head">
          <div>
            <p className="eyebrow">步驟 3 · 執行驗證</p>
            <h2 className="section-title">我的網域</h2>
            <p className="domain-add-hint">
              {domains === null
                ? "載入中…"
                : pendingCount > 0
                  ? `有 ${pendingCount} 個網域待驗證：完成設定後選擇方法按「驗證」。`
                  : "目前沒有待驗證的網域。"}
            </p>
          </div>
          <button className="secondary-button" type="button" onClick={loadDomains}>
            重新整理
          </button>
        </div>

        {listError && <p className="error-text">{listError}</p>}

        {domains !== null && domains.length === 0 && !listError && (
          <p className="domain-empty">還沒有任何網域。從上方「新增網域」開始！</p>
        )}

        <div className="domain-list">
          {(domains || []).map((domain) => {
            const status = displayStatus(domain);
            const canVerify = !domain.is_effectively_verified && domain.status !== "rejected";
            const flash = verifyFlash[domain.id];
            const busy = verifyBusyId === domain.id;
            return (
              <article key={domain.id} className={`domain-row status-${status}`}>
                <div className="domain-row-main">
                  <div className="domain-row-title">
                    <p className="domain-name">{domain.domain}</p>
                    <span className={`domain-status-badge is-${status}`}>
                      {STATUS_LABELS[status]}
                    </span>
                    {domain.admin_override && (
                      <span className="domain-chip is-override" title="由管理員人工核准，同等於驗證通過">
                        人工核准
                      </span>
                    )}
                    {domain.method && (
                      <span className="domain-chip is-method">{METHOD_LABELS[domain.method]}</span>
                    )}
                  </div>
                  <dl className="domain-row-meta">
                    {domain.is_effectively_verified && domain.expires_at && (
                      <div>
                        <dt>驗證到期</dt>
                        <dd>
                          {formatDate(domain.expires_at)}
                          {typeof domain.days_until_expiry === "number" &&
                            `（剩 ${Math.max(0, domain.days_until_expiry)} 天）`}
                        </dd>
                      </div>
                    )}
                    {!domain.is_effectively_verified && domain.last_checked_at && (
                      <div>
                        <dt>最後檢查</dt>
                        <dd>{formatDate(domain.last_checked_at)}</dd>
                      </div>
                    )}
                  </dl>
                </div>

                {domain.status === "rejected" && (
                  <p className="domain-row-note is-rejected">
                    此網域已由管理員否決；若你確實擁有該網域，請聯絡管理員或重新加入。
                  </p>
                )}

                {flash && (
                  <p className={`domain-flash ${flash.ok ? "is-ok" : "is-fail"}`} role="status">
                    {flash.ok ? "✓ " : "✕ "}{flash.message}
                  </p>
                )}

                {!flash?.ok && domain.last_error && !domain.is_effectively_verified && domain.status !== "rejected" && (
                  <p className="domain-row-note is-error">上次失敗原因：{domain.last_error}</p>
                )}

                {canVerify && (
                  <div className="domain-verify-controls">
                    <div className="domain-verify-methods" role="group" aria-label={`${domain.domain} 的驗證方法`}>
                      {METHOD_OPTIONS.map((option) => {
                        const selected = (verifyMethod[domain.id] || "dns_txt") === option.value;
                        return (
                          <button
                            key={option.value}
                            type="button"
                            className={`domain-method-btn ${selected ? "active" : ""}`}
                            onClick={() =>
                              setVerifyMethod((current) => ({ ...current, [domain.id]: option.value }))
                            }
                            aria-pressed={selected}
                          >
                            {option.label}
                          </button>
                        );
                      })}
                    </div>
                    <button
                      className="domain-verify-btn"
                      type="button"
                      onClick={() => handleVerify(domain)}
                      disabled={busy}
                    >
                      {busy ? "驗證中…" : "驗證"}
                    </button>
                  </div>
                )}

                <div className="domain-row-actions">
                  <button
                    className="domain-delete-btn"
                    type="button"
                    onClick={() => handleDelete(domain)}
                    disabled={deletingId === domain.id}
                  >
                    {deletingId === domain.id ? "刪除中…" : "刪除"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {dialogHost}
    </div>
  );
}

export default DomainVerifyPage;
