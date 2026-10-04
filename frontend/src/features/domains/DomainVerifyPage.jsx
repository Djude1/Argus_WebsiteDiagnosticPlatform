import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  connectDomainSearchConsole,
  createVerifiedDomain,
  deleteVerifiedDomain,
  disconnectDomainSearchConsole,
  fetchDomainSearchConsole,
  fetchVerifiedDomain,
  fetchVerifiedDomains,
  syncDomainSearchConsole,
  verifyVerifiedDomain,
} from "../../api";
import { apiErrorMessage, useConfirmDialogs } from "../../shared/AppShared.jsx";
import { copyToClipboard } from "../../shared/clipboard";
import { CheckCircleIcon, ClockIcon, GlobeIcon, LockIcon, SearchIcon, ShieldIcon } from "../../shared/LineIcons.jsx";

// ============================================================
// 網域所有權驗證頁（/domains）——主動式資安測試的閘門。
// 2026-10-04 改版：Google Search Console 一鍵連接為主（帳號層級連線，後端
// /api/domains/gsc/*），連接後 Search Console 裡你是「擁有者」的網站全部自動
// 匯入並通過驗證；DNS TXT／meta 標籤／驗證檔收在每個網域的「其他驗證方式」。
// ============================================================

const STATUS_LABELS = {
  pending: "待驗證",
  verified: "已驗證",
  rejected: "已否決",
  expired: "已過期",
};

const METHOD_LABELS = {
  search_console: "Google Search Console",
  dns_txt: "DNS TXT 記錄",
  meta_tag: "HTML meta 標籤",
  html_file: "驗證檔案",
};

// 備用方法（沒有 Search Console 的人用）
const MANUAL_METHODS = [
  { value: "dns_txt", label: "DNS TXT" },
  { value: "meta_tag", label: "meta 標籤" },
  { value: "html_file", label: "驗證檔" },
];

// 剩幾天內到期就提醒重新驗證
const EXPIRY_WARNING_DAYS = 14;

function displayStatus(domain) {
  if (domain.is_effectively_verified) return "verified";
  if (domain.status === "verified") return "expired";
  return domain.status;
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("zh-Hant", { year: "numeric", month: "numeric", day: "numeric" });
}

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

// 「其他驗證方式」：三種備用方法的設定說明＋以該方法驗證
function ManualMethods({ detail, method, onMethod, onVerify, busy, copiedKey, onCopy }) {
  const instructions = detail?.instructions || {};
  return (
    <div className="domain-manual">
      <div className="domain-ins-tabs" role="tablist" aria-label="其他驗證方式">
        {MANUAL_METHODS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={method === option.value}
            className={`domain-ins-tab ${method === option.value ? "active" : ""}`}
            onClick={() => onMethod(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {!detail && <p className="domain-ins-hint">載入設定說明中…</p>}
      {method === "dns_txt" && instructions.dns_txt && (
        <div className="domain-ins-panel" role="tabpanel">
          <p className="domain-ins-hint">到 DNS 管理介面新增一筆 TXT 記錄：</p>
          <dl className="domain-ins-fields">
            <CopyField label="記錄名稱（Host）" value={instructions.dns_txt.record_name} copiedKey={copiedKey} onCopy={onCopy} />
            <CopyField label="記錄類型（Type）" value={instructions.dns_txt.record_type} copiedKey={copiedKey} onCopy={onCopy} />
            <CopyField label="記錄值（Value）" value={instructions.dns_txt.value} copiedKey={copiedKey} onCopy={onCopy} />
          </dl>
          <p className="domain-ins-note">DNS 生效需要一點時間，剛設定完驗證失敗的話，幾分鐘後再試。</p>
        </div>
      )}
      {method === "meta_tag" && instructions.meta_tag && (
        <div className="domain-ins-panel" role="tabpanel">
          <p className="domain-ins-hint">把這個標籤放進{instructions.meta_tag.location}：</p>
          <dl className="domain-ins-fields">
            <CopyField label="標籤" value={instructions.meta_tag.snippet} copiedKey={copiedKey} onCopy={onCopy} />
          </dl>
        </div>
      )}
      {method === "html_file" && instructions.html_file && (
        <div className="domain-ins-panel" role="tabpanel">
          <p className="domain-ins-hint">在網站放一個驗證檔，內容就是下面的 Token：</p>
          <dl className="domain-ins-fields">
            <CopyField label="完整網址" value={instructions.html_file.url} copiedKey={copiedKey} onCopy={onCopy} />
            <CopyField label="檔案內容" value={instructions.html_file.content} copiedKey={copiedKey} onCopy={onCopy} />
          </dl>
        </div>
      )}
      <div className="domain-manual-actions">
        <button className="secondary-button" type="button" onClick={onVerify} disabled={busy || !detail}>
          {busy ? "驗證中…" : `以 ${MANUAL_METHODS.find((m) => m.value === method)?.label} 驗證`}
        </button>
      </div>
    </div>
  );
}

// Search Console 連線卡：這頁唯一的主要動作
function SearchConsoleCard({ status, busy, onConnect, onSync, onDisconnect }) {
  if (!status) {
    return <section className="panel domain-gsc-card" aria-busy="true"><p className="domain-ins-hint">載入 Search Console 狀態中…</p></section>;
  }
  const connected = status.connected && !status.needs_reconnect;
  return (
    <section className={`panel domain-gsc-card ${connected ? "is-connected" : ""}`} aria-labelledby="domain-gsc-title">
      <div className="domain-gsc-main">
        <span className="domain-gsc-icon" aria-hidden="true"><SearchIcon /></span>
        <div>
          <p className="eyebrow">建議方式</p>
          <h2 id="domain-gsc-title" className="section-title">用 Google Search Console 一鍵驗證</h2>
          <p className="domain-gsc-lead">
            連接後，你在 Search Console 是<strong>擁有者</strong>的網站會自動加入並通過驗證，不用再改 DNS 或上傳檔案。
          </p>
          <ul className="domain-gsc-facts">
            <li><LockIcon aria-hidden="true" />只申請唯讀權限，不會修改你的 Search Console</li>
            <li><ShieldIcon aria-hidden="true" />只有「擁有者」權限算數，被加為使用者的人無法冒用</li>
            <li><GlobeIcon aria-hidden="true" />「網域」資源會涵蓋所有子網域</li>
          </ul>
        </div>
      </div>
      <div className="domain-gsc-side">
        {!status.enabled ? (
          <p className="domain-gsc-state is-muted">網站尚未設定 Search Console 串接，請改用各網域的「其他驗證方式」。</p>
        ) : connected ? (
          <>
            <p className="domain-gsc-state is-ok"><CheckCircleIcon aria-hidden="true" />已連接 Search Console</p>
            <button className="primary-button" type="button" onClick={onSync} disabled={busy}>
              {busy === "sync" ? "同步中…" : "重新同步網站"}
            </button>
            {status.account_connection && (
              <button className="domain-text-btn" type="button" onClick={onDisconnect} disabled={Boolean(busy)}>
                中斷連線
              </button>
            )}
          </>
        ) : (
          <>
            {status.needs_reconnect && <p className="domain-gsc-state is-warn">授權已失效，請重新連接。</p>}
            <button className="primary-button domain-gsc-connect" type="button" onClick={onConnect} disabled={Boolean(busy)}>
              {busy === "connect" ? "前往 Google…" : "連接 Google Search Console"}
            </button>
            <p className="domain-gsc-note">會前往 Google 授權頁，完成後自動回到這裡。</p>
          </>
        )}
      </div>
    </section>
  );
}

export function DomainVerifyPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();
  const [domains, setDomains] = useState(null); // null = 載入中
  const [listError, setListError] = useState("");
  const [gscStatus, setGscStatus] = useState(null);
  const [gscBusy, setGscBusy] = useState("");
  const [banner, setBanner] = useState(null); // { tone, text }
  const [manualOpen, setManualOpen] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [expanded, setExpanded] = useState({}); // domainId -> { detail, method }
  const [busyId, setBusyId] = useState(null);
  const [rowFlash, setRowFlash] = useState({}); // domainId -> { ok, message }
  const [deletingId, setDeletingId] = useState(null);
  const [copiedKey, setCopiedKey] = useState("");
  const copiedTimer = useRef(null);

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

  async function loadGsc() {
    try {
      setGscStatus(await fetchDomainSearchConsole());
    } catch {
      setGscStatus({ enabled: false, connected: false });
    }
  }

  useEffect(() => {
    loadDomains();
    loadGsc();
  }, []);

  useEffect(() => () => clearTimeout(copiedTimer.current), []);

  // Google 授權導回：?gsc=connected&verified=<數量> / ?gsc=error&reason=…
  useEffect(() => {
    const result = searchParams.get("gsc");
    if (!result) return;
    if (result === "connected") {
      const count = Number(searchParams.get("verified") || 0);
      setBanner(searchParams.get("synced") === "0"
        ? { tone: "warn", text: "已連接 Search Console，但暫時讀不到你的網站清單；請稍後按「重新同步網站」。" }
        : count > 0
          ? { tone: "ok", text: `已連接 Search Console，${count} 個網域已自動通過驗證。` }
          : { tone: "warn", text: "已連接 Search Console，但這個 Google 帳號沒有任何「擁有者」權限的網站。請確認連接的是網站擁有者的帳號，或改用其他驗證方式。" });
    } else {
      setBanner({ tone: "fail", text: searchParams.get("reason") || "Search Console 連接失敗，請再試一次。" });
    }
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  async function handleCopy(text) {
    if (await copyToClipboard(text)) {
      setCopiedKey(text);
      clearTimeout(copiedTimer.current);
      copiedTimer.current = setTimeout(() => setCopiedKey(""), 2000);
    } else {
      notifyDialog("複製失敗，請手動選取文字複製。");
    }
  }

  async function handleConnect() {
    setGscBusy("connect");
    try {
      const { authorization_url: url } = await connectDomainSearchConsole();
      window.location.assign(url);
    } catch (err) {
      setGscBusy("");
      setBanner({ tone: "fail", text: apiErrorMessage(err, "無法連接 Search Console，請稍後再試。") });
    }
  }

  async function handleSync() {
    setGscBusy("sync");
    setBanner(null);
    try {
      const data = await syncDomainSearchConsole();
      setGscStatus(data);
      setBanner(data.verified?.length
        ? { tone: "ok", text: `同步完成：${data.verified.length} 個網域已通過驗證（${data.verified.join("、")}）。` }
        : { tone: "warn", text: "同步完成，但這個 Google 帳號沒有任何「擁有者」權限的網站。" });
      await loadDomains();
    } catch (err) {
      setBanner({ tone: "fail", text: apiErrorMessage(err, "同步失敗，請稍後再試。") });
      loadGsc();
    } finally {
      setGscBusy("");
    }
  }

  async function handleDisconnect() {
    const ok = await confirmDialog("中斷 Search Console 連線？Argus 會向 Google 撤銷授權；已驗證的網域照常有效到期滿。", { danger: true });
    if (!ok) return;
    setGscBusy("disconnect");
    try {
      setGscStatus(await disconnectDomainSearchConsole());
      setBanner({ tone: "ok", text: "已中斷 Search Console 連線。" });
    } catch (err) {
      notifyDialog(apiErrorMessage(err, "中斷連線失敗，請稍後再試。"));
    } finally {
      setGscBusy("");
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
      setNewDomain("");
      await loadDomains();
      // 新增後直接展開設定說明（建立回應已含 token 與 instructions）
      setExpanded((current) => ({ ...current, [data.id]: { detail: data, method: "dns_txt" } }));
    } catch (err) {
      setCreateError(apiErrorMessage(err, "新增網域失敗，請確認網域格式正確。"));
    } finally {
      setCreating(false);
    }
  }

  async function toggleManual(domain) {
    if (expanded[domain.id]) {
      setExpanded(({ [domain.id]: _removed, ...rest }) => rest);
      return;
    }
    setExpanded((current) => ({ ...current, [domain.id]: { detail: null, method: "dns_txt" } }));
    try {
      const detail = await fetchVerifiedDomain(domain.id);
      setExpanded((current) => (current[domain.id] ? { ...current, [domain.id]: { ...current[domain.id], detail } } : current));
    } catch (err) {
      notifyDialog(apiErrorMessage(err, "載入設定說明失敗。"));
    }
  }

  async function handleVerify(domain, method) {
    setBusyId(domain.id);
    setRowFlash((flash) => ({ ...flash, [domain.id]: null }));
    try {
      const data = await verifyVerifiedDomain(domain.id, method);
      setDomains((list) => (list || []).map((item) => (item.id === domain.id ? { ...item, ...data } : item)));
      setRowFlash((flash) => ({
        ...flash,
        [domain.id]: data.verified
          ? { ok: true, message: "驗證成功！此網域（含子網域）已可使用主動式資安測試。" }
          : { ok: false, message: data.last_error || "驗證未通過，請確認設定後再試。" },
      }));
      if (data.verified) setExpanded(({ [domain.id]: _removed, ...rest }) => rest);
    } catch (err) {
      notifyDialog(apiErrorMessage(err, "驗證執行失敗，請稍後再試。"));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(domain) {
    const ok = await confirmDialog(`確定刪除網域「${domain.domain}」？之後要再做主動式測試，需重新加入並驗證。`, { danger: true });
    if (!ok) return;
    setDeletingId(domain.id);
    try {
      await deleteVerifiedDomain(domain.id);
      setDomains((list) => (list || []).filter((item) => item.id !== domain.id));
    } catch (err) {
      notifyDialog(apiErrorMessage(err, "刪除失敗，請稍後再試。"));
    } finally {
      setDeletingId(null);
    }
  }

  const counts = useMemo(() => {
    const list = domains || [];
    return {
      verified: list.filter((d) => d.is_effectively_verified).length,
      pending: list.filter((d) => !d.is_effectively_verified && d.status !== "rejected").length,
      expiring: list.filter((d) => d.is_effectively_verified && typeof d.days_until_expiry === "number" && d.days_until_expiry <= EXPIRY_WARNING_DAYS).length,
    };
  }, [domains]);

  const gscConnected = Boolean(gscStatus?.connected && !gscStatus?.needs_reconnect);

  // 需要處理的排前面：待驗證／已過期 → 即將到期 → 其餘（同組依原本的建立時間）
  const sortedDomains = useMemo(() => {
    const rank = (d) => {
      if (!d.is_effectively_verified && d.status !== "rejected") return 0;
      if (d.is_effectively_verified && typeof d.days_until_expiry === "number" && d.days_until_expiry <= EXPIRY_WARNING_DAYS) return 1;
      return d.status === "rejected" ? 3 : 2;
    };
    return [...(domains || [])].sort((a, b) => rank(a) - rank(b));
  }, [domains]);

  return (
    <div className="domain-page">
      <button type="button" className="domain-back" onClick={() => navigate("/projects")}>
        ← 返回所有專案
      </button>

      <header className="domain-header">
        <p className="eyebrow">所有權證明</p>
        <h1 className="domain-title">網域驗證</h1>
        <p className="domain-lead">
          主動式資安測試只開放給你證明擁有的網站。驗證通過後，該網域與子網域都能使用主動測試，有效期 90 天。
        </p>
      </header>

      <SearchConsoleCard
        status={gscStatus}
        busy={gscBusy}
        onConnect={handleConnect}
        onSync={handleSync}
        onDisconnect={handleDisconnect}
      />

      {banner && (
        <div className={`domain-banner is-${banner.tone}`} role="status">
          <span>{banner.text}</span>
          <button type="button" className="domain-text-btn" onClick={() => setBanner(null)}>知道了</button>
        </div>
      )}

      <section className="panel domain-list-panel" aria-labelledby="domain-list-title">
        <div className="domain-list-head">
          <div>
            <h2 id="domain-list-title" className="section-title">我的網域</h2>
            <ul className="domain-stats" aria-label="網域統計">
              <li><strong>{counts.verified}</strong> 已驗證</li>
              <li><strong>{counts.pending}</strong> 待驗證</li>
              {counts.expiring > 0 && <li className="is-warn"><strong>{counts.expiring}</strong> 即將到期</li>}
            </ul>
          </div>
          <button className="secondary-button" type="button" onClick={() => setManualOpen((open) => !open)} aria-expanded={manualOpen}>
            {manualOpen ? "收起" : "手動新增網域"}
          </button>
        </div>

        {manualOpen && (
          <form className="domain-add-inline" onSubmit={handleCreate}>
            <label htmlFor="domain-new">沒有 Search Console？輸入網域，之後用 DNS、meta 標籤或驗證檔證明</label>
            <div className="domain-add-row">
              <input
                id="domain-new"
                className="input"
                type="text"
                placeholder="example.com"
                value={newDomain}
                onChange={(event) => setNewDomain(event.target.value)}
                autoComplete="off"
                spellCheck="false"
              />
              <button className="secondary-button" type="submit" disabled={creating}>
                {creating ? "新增中…" : "新增網域"}
              </button>
            </div>
            {createError && <p className="error-text">{createError}</p>}
          </form>
        )}

        {listError && <p className="error-text">{listError}</p>}
        {domains === null && <p className="domain-empty">載入中…</p>}
        {domains !== null && domains.length === 0 && !listError && (
          <div className="domain-empty">
            <GlobeIcon aria-hidden="true" />
            <p>{gscConnected
              ? "Search Console 裡沒有你是擁有者的網站。確認帳號後按「重新同步網站」，或手動新增網域。"
              : "還沒有網域。連接 Google Search Console，你擁有的網站會自動出現在這裡。"}</p>
          </div>
        )}

        <div className="domain-list">
          {sortedDomains.map((domain) => {
            const status = displayStatus(domain);
            const canVerify = !domain.is_effectively_verified && domain.status !== "rejected";
            const expiring = domain.is_effectively_verified && typeof domain.days_until_expiry === "number" && domain.days_until_expiry <= EXPIRY_WARNING_DAYS;
            const flash = rowFlash[domain.id];
            const manual = expanded[domain.id];
            const busy = busyId === domain.id;
            return (
              <article key={domain.id} className={`domain-row status-${status}`}>
                <div className="domain-row-main">
                  <div className="domain-row-title">
                    <p className="domain-name">{domain.domain}</p>
                    <span className={`domain-status-badge is-${status}`}>{STATUS_LABELS[status]}</span>
                    {domain.admin_override && <span className="domain-chip is-override">人工核准</span>}
                    {domain.method && domain.is_effectively_verified && (
                      <span className="domain-chip is-method">{METHOD_LABELS[domain.method]}</span>
                    )}
                  </div>
                  <dl className="domain-row-meta">
                    {domain.is_effectively_verified && domain.expires_at && (
                      <div className={expiring ? "is-warn" : ""}>
                        <dt><ClockIcon aria-hidden="true" />有效到</dt>
                        <dd>
                          {formatDate(domain.expires_at)}
                          {typeof domain.days_until_expiry === "number" && `（剩 ${Math.max(0, domain.days_until_expiry)} 天）`}
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
                  <p className="domain-row-note is-rejected">此網域已由管理員否決；若你確實擁有該網域，請聯絡管理員。</p>
                )}
                {flash && (
                  <p className={`domain-flash ${flash.ok ? "is-ok" : "is-fail"}`} role="status">{flash.message}</p>
                )}
                {!flash && canVerify && domain.last_error && (
                  <p className="domain-row-note is-error">上次未通過：{domain.last_error}</p>
                )}

                {(canVerify || expiring) && (
                  <div className="domain-row-actions-bar">
                    {gscConnected ? (
                      <button className="domain-verify-btn" type="button" onClick={() => handleVerify(domain, "search_console")} disabled={busy}>
                        {busy ? "驗證中…" : expiring ? "用 Search Console 續期" : "用 Search Console 驗證"}
                      </button>
                    ) : (
                      <span className="domain-row-hint">連接上方的 Search Console 即可自動{expiring ? "續期" : "驗證"}</span>
                    )}
                    {canVerify && (
                      <button className="domain-text-btn" type="button" onClick={() => toggleManual(domain)} aria-expanded={Boolean(manual)}>
                        {manual ? "收起其他驗證方式" : "其他驗證方式"}
                      </button>
                    )}
                  </div>
                )}

                {manual && (
                  <ManualMethods
                    detail={manual.detail}
                    method={manual.method}
                    onMethod={(method) => setExpanded((current) => ({ ...current, [domain.id]: { ...current[domain.id], method } }))}
                    onVerify={() => handleVerify(domain, manual.method)}
                    busy={busy}
                    copiedKey={copiedKey}
                    onCopy={handleCopy}
                  />
                )}

                <div className="domain-row-actions">
                  <button className="domain-delete-btn" type="button" onClick={() => handleDelete(domain)} disabled={deletingId === domain.id}>
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
