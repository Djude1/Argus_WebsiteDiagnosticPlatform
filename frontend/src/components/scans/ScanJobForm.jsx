import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, fetchVerifiedDomains } from "../../api";
import { useArgusStore } from "../../store";
import { apiErrorMessage, CATEGORY_LABELS } from "../../shared/AppShared.jsx";
import { GlobeIcon, LockIcon, TargetIcon } from "../../shared/LineIcons.jsx";
import { formatNumber } from "../../shared/formatters";

export const MAX_SITE_SCAN_PAGES = 50;

// 掃描維度選項（value 必須與後端 ALL_CATEGORIES 一致）
const SCAN_CATEGORY_OPTIONS = [
  { value: "seo", label: "SEO", desc: "搜尋引擎優化" },
  { value: "aeo", label: "AEO", desc: "AI 答案引擎可讀性" },
  { value: "geo", label: "GEO", desc: "生成式搜尋整備" },
  { value: "ux", label: "UX", desc: "行動版版面" },
  { value: "security", label: CATEGORY_LABELS.security, desc: "被動資安；主動測試必勾" },
];
const DEFAULT_SCAN_CATEGORIES = SCAN_CATEGORY_OPTIONS.map((option) => option.value);

// localStorage 暫存表單草稿的 key
const SCAN_DRAFT_KEY = "argus_scan_draft_v1";

function loadScanDraft() {
  try {
    const raw = window.localStorage.getItem(SCAN_DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveScanDraft(draft) {
  try {
    window.localStorage.setItem(SCAN_DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // localStorage 滿了或被禁用時，安靜失敗
  }
}

function clearScanDraft() {
  try {
    window.localStorage.removeItem(SCAN_DRAFT_KEY);
  } catch {
    // 同上
  }
}

/** 表單分步的區段：左側編號＋完成勾，讓使用者一眼看出還差哪一步。 */
function FormStep({ index, title, hint, done, children }) {
  return (
    <section className={`scan-step ${done ? "is-done" : ""}`} aria-label={`步驟 ${index}：${title}`}>
      <div className="scan-step-rail" aria-hidden="true">
        <span className="scan-step-num">{done ? "✓" : index}</span>
      </div>
      <div className="scan-step-body">
        <div className="scan-step-head">
          <h3 className="scan-step-title">{title}</h3>
          {hint ? <p className="scan-step-hint">{hint}</p> : null}
        </div>
        {children}
      </div>
    </section>
  );
}

/**
 * 建立授權掃描表單（含 F5 防丟失與草稿持久化）。
 * 分成五步：範圍 → 維度 → 網址 → 預估費用 → 授權確認；費用隨選項即時更新。
 */
function ScanJobForm({ onCreated }) {
  // 從 localStorage 還原草稿，避免 F5 後重打網址
  const [initial] = useState(() => loadScanDraft() || {});
  const [scope, setScope] = useState(initial.scope || "site"); // "single" | "site"
  const [url, setUrl] = useState(initial.url || "");
  const [authorizationConfirmed, setAuthorizationConfirmed] = useState(
    initial.authorizationConfirmed || false,
  );
  const [thirdPartyReconfirmed, setThirdPartyReconfirmed] = useState(
    initial.thirdPartyReconfirmed || false,
  );
  const [activeMode, setActiveMode] = useState(initial.activeMode || false);
  const [activeAuthorized, setActiveAuthorized] = useState(initial.activeAuthorized || false);
  // 掃描維度多選（至少一項；費用＝頁數 × 勾選維度數 × 每維單價）
  const [categories, setCategories] = useState(initial.categories || DEFAULT_SCAN_CATEGORIES);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const [estimate, setEstimate] = useState(null); // { estimated_pages, estimated_cost, confidence }
  const [verifiedDomains, setVerifiedDomains] = useState([]); // 已通過驗證的網域（URL 徽章提示用）
  const navigate = useNavigate();
  const wallet = useArgusStore((s) => s.wallet);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);
  const me = useArgusStore((s) => s.me);
  // 後端 user_owns_domain 對 staff／superuser 一律放行（管理員測試旁路）
  const staffDomainBypass = Boolean(me && (me.is_staff || me.is_superuser));

  // 只抓一次已驗證網域清單（提示用途；失敗時安靜略過，後端仍會擋主動模式）
  useEffect(() => {
    let cancelled = false;
    fetchVerifiedDomains()
      .then((data) => {
        if (!cancelled) setVerifiedDomains(data.results || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // 從目標 URL 抽 hostname（容錯：沒打協定時補 https:// 再試）
  const urlHostname = useMemo(() => {
    const raw = url.trim();
    if (!raw) return "";
    try {
      return new URL(raw).hostname.toLowerCase();
    } catch {
      try {
        return new URL(`https://${raw}`).hostname.toLowerCase();
      } catch {
        return "";
      }
    }
  }, [url]);

  // 命中已有效驗證的網域（含子網域：hostname===domain 或 endswith('.'+domain)）
  const matchedVerifiedDomain = useMemo(() => {
    if (!urlHostname) return null;
    return (
      verifiedDomains.find(
        (item) =>
          item.is_effectively_verified &&
          (urlHostname === item.domain || urlHostname.endsWith(`.${item.domain}`)),
      ) || null
    );
  }, [verifiedDomains, urlHostname]);

  const coinPerCategory = wallet?.coin_per_category ?? 2;
  const coinPerPage = coinPerCategory * categories.length;
  const effectivePages = scope === "single" ? 1 : MAX_SITE_SCAN_PAGES;
  const estimatedCost = effectivePages * coinPerPage;
  const balance = wallet?.balance ?? 0;
  const insufficient = balance < estimatedCost;
  const securitySelected = categories.includes("security");
  const activeBlocked = activeMode && !matchedVerifiedDomain && !staffDomainBypass;

  function toggleCategory(value) {
    const next = categories.includes(value)
      ? categories.filter((item) => item !== value)
      : [...categories, value];
    if (next.length === 0) return; // 至少保留一個維度
    setCategories(next);
    setEstimate(null);
    // 主動測試屬資安維度：取消資安時連動關閉主動模式與其授權勾選
    if (!next.includes("security")) {
      setActiveMode(false);
      setActiveAuthorized(false);
    }
  }

  useEffect(() => {
    saveScanDraft({
      scope,
      url,
      authorizationConfirmed,
      thirdPartyReconfirmed,
      activeMode,
      activeAuthorized,
      categories,
    });
  }, [scope, url, authorizationConfirmed, thirdPartyReconfirmed, activeMode, activeAuthorized, categories]);

  useEffect(() => {
    if (!submitting) return undefined;
    const handler = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [submitting]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      // 單頁掃描：max_pages=1, max_depth=1（不走連結）
      // 整站掃描：遵守專案預設上限，避免過度爬取與預扣過高
      const payload = {
        url,
        authorization_confirmed: authorizationConfirmed,
        third_party_reconfirmed: thirdPartyReconfirmed,
        scan_mode: activeMode ? "active" : "passive",
        active_testing_authorized: activeMode && activeAuthorized,
        categories,
        max_pages: scope === "single" ? 1 : MAX_SITE_SCAN_PAGES,
        max_depth: scope === "single" ? 1 : 3,
      };
      const response = await api.post("/scans/", payload);
      setUrl("");
      setAuthorizationConfirmed(false);
      setThirdPartyReconfirmed(false);
      setActiveMode(false);
      setActiveAuthorized(false);
      setCategories(DEFAULT_SCAN_CATEGORIES);
      setEstimate(null);
      setScope("site");
      clearScanDraft();
      fetchWallet();
      onCreated(response.data);
      // 保險：直接 navigate 到新掃描的詳情頁。原本依賴 parent ScanLayout 的
      // handleScanCreated 內 navigate，但實機測試發現 setState batch 之後
      // 那個 navigate 偶爾不生效（URL 不變），導致使用者按了「建立掃描」後
      // 還要手動點列表才能進詳情頁。表單自己持有 useNavigate，直接呼叫一次最可靠。
      if (response.data?.id) {
        navigate(`/scans/${response.data.id}`);
      }
    } catch (errorResponse) {
      setError(apiErrorMessage(errorResponse, "建立掃描失敗。"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEstimate() {
    if (!url || scope === "single") return;
    setEstimating(true);
    setEstimate(null);
    setError("");
    try {
      const res = await api.post("/estimate/", {
        url,
        max_pages: effectivePages,
        categories,
      });
      setEstimate(res.data);
    } catch (err) {
      setError(apiErrorMessage(err, "預估費用失敗，請確認網址格式正確。"));
      setEstimate(null);
    } finally {
      setEstimating(false);
    }
  }

  return (
    <form className="panel scan-form" onSubmit={handleSubmit}>
      <header className="scan-form-head">
        <p className="ag-eyebrow">新增任務</p>
        <h2 className="section-title">建立授權掃描</h2>
        <p className="scan-form-lead">
          表單會自動存草稿；重新整理或不小心關閉分頁後再回來，欄位會保留。
        </p>
      </header>

      <FormStep index={1} title="掃描範圍" done>
        <div className="scope-grid">
          <button
            type="button"
            className={`scope-card ${scope === "single" ? "active" : ""}`}
            onClick={() => setScope("single")}
            aria-pressed={scope === "single"}
          >
            <TargetIcon className="scope-icon" />
            <span className="scope-title">單一頁面</span>
            <span className="scope-desc">只掃描輸入的這一頁，最快、最省 coin</span>
            <span className="scope-meta">1 頁 × {coinPerPage} coin</span>
          </button>
          <button
            type="button"
            className={`scope-card ${scope === "site" ? "active" : ""}`}
            onClick={() => setScope("site")}
            aria-pressed={scope === "site"}
          >
            <GlobeIcon className="scope-icon" />
            <span className="scope-title">整個網站</span>
            <span className="scope-desc">從入口爬同網域多頁，產出完整健檢報告</span>
            <span className="scope-meta">最多 {MAX_SITE_SCAN_PAGES} 頁・依實際頁數計費</span>
          </button>
        </div>
      </FormStep>

      <FormStep
        index={2}
        title="掃描維度"
        hint={`每頁每維度 ${coinPerCategory} coin；已選 ${categories.length} 維${
          categories.length === 5 ? "（全選）" : "，少勾維度即省費用"
        }`}
        done={categories.length > 0}
      >
        <div className="category-grid">
          {SCAN_CATEGORY_OPTIONS.map(({ value, label, desc }) => {
            const on = categories.includes(value);
            return (
              <button
                type="button"
                key={value}
                className={`category-card cat-${value} ${on ? "active" : ""}`}
                onClick={() => toggleCategory(value)}
                aria-pressed={on}
              >
                <span className="category-card-check" aria-hidden="true" />
                <span className="category-card-text">
                  <span className="category-card-title">{label}</span>
                  <span className="category-card-desc">{desc}</span>
                </span>
              </button>
            );
          })}
        </div>
      </FormStep>

      <FormStep
        index={3}
        title={scope === "single" ? "目標頁面網址" : "網站入口網址"}
        done={Boolean(urlHostname)}
      >
        <label className="sr-only" htmlFor="scan-url">
          {scope === "single" ? "目標頁面網址" : "網站入口網址"}
        </label>
        <input
          id="scan-url"
          className="input scan-url-input"
          placeholder="https://example.com/"
          value={url}
          inputMode="url"
          autoComplete="url"
          spellCheck="false"
          onChange={(event) => {
            setUrl(event.target.value);
            setEstimate(null);
          }}
        />
        {matchedVerifiedDomain && (
          <p className="scan-verified-badge" role="status">
            <span className="scan-verified-dot" aria-hidden="true" />
            已驗證網域
            {matchedVerifiedDomain.domain !== urlHostname && `（${matchedVerifiedDomain.domain}）`}
            <span className="scan-verified-note">可使用主動式資安測試</span>
          </p>
        )}
      </FormStep>

      <FormStep index={4} title="預估費用" done={!insufficient}>
        <div className={`scan-cost ${insufficient ? "is-insufficient" : ""}`}>
          <div className="scan-cost-main">
            <span className="scan-cost-label">本次預扣</span>
            <span className="scan-cost-value ag-num" aria-live="polite">
              {formatNumber(estimatedCost)}
              <small>coin</small>
            </span>
          </div>
          <p className="scan-cost-formula">
            {effectivePages} 頁 × {categories.length} 維 × {coinPerCategory} coin
          </p>
          <dl className="scan-cost-rows">
            <div>
              <dt>目前餘額</dt>
              <dd className="ag-num">{formatNumber(balance)} coin</dd>
            </div>
            <div>
              <dt>預扣後</dt>
              <dd className={`ag-num ${insufficient ? "is-negative" : ""}`}>
                {formatNumber(balance - estimatedCost)} coin
              </dd>
            </div>
          </dl>
          {scope !== "single" && (
            <div className="scan-cost-estimate">
              <button
                type="button"
                className="ghost-button scan-cost-estimate-btn"
                onClick={handleEstimate}
                disabled={estimating || !url}
              >
                {estimating ? "計算中…" : "依網址計算費用上限"}
              </button>
              {estimate && (
                <p className="scan-cost-estimate-result" role="status" aria-live="polite">
                  最多 <strong>{estimate.estimated_pages}</strong> 頁，費用上限{" "}
                  <strong>{formatNumber(estimate.estimated_cost)}</strong> coin
                </p>
              )}
            </div>
          )}
          {insufficient && (
            <button className="scan-cost-cta" type="button" onClick={() => navigate("/billing")}>
              點數不足，前往購點 →
            </button>
          )}
          <p className="scan-cost-hint">完成後依實際爬到的頁數退回未使用的 coin；失敗或取消全額退回。</p>
        </div>
      </FormStep>

      <FormStep index={5} title="授權確認" done={authorizationConfirmed}>
        <div className="scan-consents">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={authorizationConfirmed}
              onChange={(event) => setAuthorizationConfirmed(event.target.checked)}
            />
            <span>我擁有此網站或已獲得書面授權測試。</span>
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={thirdPartyReconfirmed}
              onChange={(event) => setThirdPartyReconfirmed(event.target.checked)}
            />
            <span>若此網站看似第三方或敏感產業，我已再次確認授權。</span>
          </label>
          <label className={`checkbox-row scan-active-toggle ${securitySelected ? "" : "is-disabled"}`}>
            <input
              type="checkbox"
              checked={activeMode}
              onChange={(event) => setActiveMode(event.target.checked)}
              disabled={!securitySelected}
            />
            <span>
              <LockIcon className="scan-active-icon" />
              啟用主動式資安測試模式。
              {!securitySelected && <span className="scan-active-note">需先勾選「資安」維度</span>}
            </span>
          </label>
          {activeMode && (
            <label className="checkbox-row warning">
              <input
                type="checkbox"
                checked={activeAuthorized}
                onChange={(event) => setActiveAuthorized(event.target.checked)}
              />
              <span>我同意進行侵入式測試，並理解系統會限制 RPS ≤ 2。</span>
            </label>
          )}
          {activeBlocked && (
            <div className="scan-domain-warning" role="alert">
              <p className="scan-domain-warning-title">主動式測試需要先通過網域驗證</p>
              <p className="scan-domain-warning-text">
                {urlHostname
                  ? `目標 ${urlHostname} 尚未通過網域所有權驗證，直接送出會被系統拒絕。`
                  : "目前輸入的目標尚未通過網域所有權驗證，直接送出會被系統拒絕。"}
                請先完成網域驗證（驗證一次即涵蓋子網域）。
              </p>
              <button
                type="button"
                className="scan-domain-warning-link"
                onClick={() => navigate("/domains")}
              >
                前往網域驗證 →
              </button>
            </div>
          )}
          {activeMode && !matchedVerifiedDomain && staffDomainBypass && (
            <p className="scan-verified-badge" role="status">
              <span className="scan-verified-dot" aria-hidden="true" />
              管理員測試模式：已略過網域驗證閘門
              <span className="scan-verified-note">掃描紀錄仍歸屬您的帳號</span>
            </p>
          )}
        </div>
      </FormStep>

      {error && <p className="error-text" role="alert">{error}</p>}
      <button className="primary-button scan-submit" type="submit" disabled={submitting}>
        {submitting ? (
          "送出中…（請勿關閉視窗）"
        ) : (
          <>
            <span>建立掃描</span>
            <span className="scan-submit-cost ag-num">預扣 {formatNumber(estimatedCost)} coin</span>
          </>
        )}
      </button>
    </form>
  );
}

export default ScanJobForm;
