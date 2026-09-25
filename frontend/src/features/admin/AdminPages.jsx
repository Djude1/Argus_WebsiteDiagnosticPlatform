import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Navigate,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import {
  adminDomainOverride,
  adminUserSubscriptionAction,
  api,
  fetchAdminDomains,
  fetchAdminSubscriptionPlans,
  fetchUserLoginEvents,
  fetchUserSubscription,
} from "../../api";
import { useArgusStore } from "../../store";
import brandLogo from "../../assets/brand-logo.webp";
import { STATUS_LABELS, StatusDoneGlyph, useConfirmDialogs } from "../../shared/AppShared.jsx";
import { AdminField, AdminModal } from "../../components/admin/AdminModal.jsx";
import { AdminPagination } from "../../components/admin/AdminPagination.jsx";
import { AdminSortableTh } from "../../components/admin/AdminSortableTh.jsx";
import { AdminStatCard } from "../../components/admin/AdminStatCard.jsx";
import { AdminEmptyState, AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates.jsx";
import { formatDateTime, formatDuration, formatNtd, formatNumber } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery.js";
import {
  AdminOverviewIcon,
  AdminUsersIcon,
  AdminScansIcon,
  AdminDomainsIcon,
  AdminTransactionsIcon,
  AdminPlansIcon,
  AdminContentIcon,
  AdminReviewsIcon,
  AdminSettingsIcon,
  AdminAuditLogIcon,
  AdminAnnouncementsIcon,
  AdminMenuIcon,
  AdminStarIcon,
  AdminOrdersIcon,
  AdminTokensIcon,
  AdminTrendIcon,
  AdminAlertIcon,
} from "../../components/admin/AdminIcons.jsx";

// 側欄導覽依「使用者來後台做什麼」分組，而非依資料表分。
//
// 改建原因：原本是 10 項平鋪（superuser 12 項），超過專案 argus-ui-design skill
// 訂的 5–7 項上限，掃視成本高且看不出彼此關係。分組後每組 3 項，四組對應四種
// 到訪目的：處理今天的事、回應客戶、維護內容、調整系統。
//
// superuserOnly 的項目對 staff 完全不顯示（不是 disabled）——看得到卻點不了
// 只會製造挫折。
const ADMIN_NAV_GROUPS = [
  {
    key: "operations",
    label: "營運",
    items: [
      { to: "/admin/overview", label: "概覽", Icon: AdminOverviewIcon },
      { to: "/admin/scans", label: "掃描任務", Icon: AdminScansIcon },
      { to: "/admin/domains", label: "網域驗證", Icon: AdminDomainsIcon },
      { to: "/admin/health", label: "系統健康", Icon: AdminAlertIcon },
    ],
  },
  {
    key: "customers",
    label: "客戶",
    items: [
      { to: "/admin/users", label: "使用者", Icon: AdminUsersIcon },
      { to: "/admin/orders", label: "訂單", Icon: AdminOrdersIcon },
      { to: "/admin/transactions", label: "點數交易", Icon: AdminTransactionsIcon },
    ],
  },
  {
    key: "content",
    label: "內容與社群",
    items: [
      { to: "/admin/reviews", label: "評論治理", Icon: AdminReviewsIcon },
      { to: "/admin/content", label: "網站內容", Icon: AdminContentIcon },
      { to: "/admin/announcements", label: "公告", Icon: AdminAnnouncementsIcon, superuserOnly: true },
    ],
  },
  {
    key: "system",
    label: "系統",
    items: [
      { to: "/admin/plans", label: "方案與定價", Icon: AdminPlansIcon },
      { to: "/admin/settings", label: "系統資訊", Icon: AdminSettingsIcon },
      { to: "/admin/audit-log", label: "操作日誌", Icon: AdminAuditLogIcon, superuserOnly: true },
    ],
  },
];

function activateAdminRow(event, action) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    action();
  }
}

function RequireAdmin({ children }) {
  const accessToken = useArgusStore((s) => s.accessToken);
  const me = useArgusStore((s) => s.me);
  const fetchMe = useArgusStore((s) => s.fetchMe);
  useEffect(() => {
    if (accessToken && me === null) fetchMe();
  }, [accessToken, me, fetchMe]);
  if (!accessToken) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (me === null) {
    return <div className="admin-loading">驗證權限中…</div>;
  }
  if (!me.is_staff) {
    return (
      <div className="admin-forbidden">
        <h2>沒有後台權限</h2>
        <p>此帳號（{me.username}）不是管理員。如需後台存取，請聯絡 superuser。</p>
        <NavLink className="primary-button mt-3 inline-block" to="/dashboard">
          回到 Dashboard
        </NavLink>
      </div>
    );
  }
  return children;
}

function AdminLayout() {
  const { setToken, me, replayIntro, theme, toggleTheme } = useArgusStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isMobileDrawer, setIsMobileDrawer] = useState(() => window.matchMedia("(max-width: 900px)").matches);
  const menuButtonRef = useRef(null);
  const sidebarRef = useRef(null);
  function closeDrawer() {
    setDrawerOpen(false);
    if (isMobileDrawer) menuButtonRef.current?.focus();
  }
  async function handleLogout() {
    try {
      await api.post("/auth/logout/");
    } finally {
      setToken(null);
      navigate("/login");
    }
  }
  useEffect(() => setDrawerOpen(false), [location.pathname]);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 900px)");
    const handleChange = (event) => setIsMobileDrawer(event.matches);
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, []);
  useEffect(() => {
    if (!drawerOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = sidebarRef.current?.querySelectorAll("button, a[href]") || [];
    focusable[0]?.focus();
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        closeDrawer();
      }
      if (event.key === "Tab" && focusable.length) {
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
    }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [drawerOpen]);
  // 依權限過濾；整組都被濾掉時連標題一起不顯示，避免出現空的分組標題
  const navGroups = ADMIN_NAV_GROUPS
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !item.superuserOnly || me?.is_superuser),
    }))
    .filter((group) => group.items.length > 0);
  return (
    <div className="admin-shell">
      <header className="admin-mobile-header">
        <button
          ref={menuButtonRef}
          type="button"
          className="admin-menu-button"
          aria-controls="admin-sidebar"
          aria-expanded={drawerOpen}
          aria-label="開啟管理選單"
          onClick={() => setDrawerOpen(true)}
        >
          <AdminMenuIcon />
        </button>
        <strong>ARGUS 管理後台</strong>
      </header>
      {drawerOpen && (
        <button
          type="button"
          className="admin-drawer-backdrop"
          aria-label="關閉管理選單"
          onClick={closeDrawer}
        />
      )}
      <aside
        id="admin-sidebar"
        ref={sidebarRef}
        className={`admin-sidebar ${drawerOpen ? "is-open" : ""}`}
        aria-hidden={isMobileDrawer && !drawerOpen}
        inert={isMobileDrawer && !drawerOpen ? "" : undefined}
      >
        <button type="button" className="admin-brand" onClick={() => { replayIntro(); navigate("/project"); }} title="回到前台首頁" aria-label="回到前台首頁">
          <img src={brandLogo} className="admin-brand-logo" alt="ARGUS" />
          <span className="admin-brand-sub">管理後台</span>
        </button>
        <nav className="admin-nav">
          {navGroups.map((group) => (
            <div className="admin-nav-group" key={group.key}>
              <p className="admin-nav-group-label" id={`admin-nav-${group.key}`}>
                {group.label}
              </p>
              <div role="group" aria-labelledby={`admin-nav-${group.key}`}>
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `admin-nav-link ${isActive ? "active" : ""}`
                    }
                    onClick={closeDrawer}
                  >
                    <item.Icon className="admin-nav-icon" />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="admin-sidebar-footer">
          <button
            type="button"
            className="admin-theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "切換為淺色主題" : "切換為深色主題"}
          >
            <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
            <span>{theme === "dark" ? "淺色主題" : "深色主題"}</span>
          </button>
          <NavLink to="/dashboard" className="admin-side-link" onClick={closeDrawer}>
            ← 回前台
          </NavLink>
          <button
            type="button"
            className="admin-side-link"
            onClick={handleLogout}
          >
            登出
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}

const USERS_QUERY_DEFAULTS = { page: 1, q: "", ordering: "-date_joined" };

function AdminUsersPage() {
  const navigate = useNavigate();
  const { params, setParam, setParams, resetFilters, hasFilters } = useListQuery(USERS_QUERY_DEFAULTS);
  const { page, q, ordering } = params;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchDraft, setSearchDraft] = useState(q);

  useEffect(() => { setSearchDraft(q); }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/users/", {
        params: { q: q || undefined, page, ordering },
      });
      setData(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "無法載入使用者");
    } finally {
      setLoading(false);
    }
  }, [q, page, ordering]);

  useEffect(() => { load(); }, [load]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    // 只改網址，由 load 的 useCallback 依賴觸發重載；
    // 原本 setPage(1) + load() 會因 page 閉包是舊值而連送兩次請求
    setParams({ q: searchDraft.trim() });
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>使用者</h1>
        <p>所有註冊帳號與其點數狀態</p>
      </header>

      <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
        <input
          className="admin-input"
          placeholder="搜尋 email、姓名或帳號"
          aria-label="搜尋使用者"
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
        />
        <button className="admin-btn" type="submit">搜尋</button>
        {hasFilters && (
          <button type="button" className="admin-btn ghost" onClick={resetFilters}>清除篩選</button>
        )}
      </form>

      {error && <AdminErrorState message="無法載入使用者" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入使用者中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <AdminSortableTh field="username" ordering={ordering} onChange={(o) => setParam("ordering", o)}>使用者</AdminSortableTh>
                <th>email</th>
                <AdminSortableTh field="balance" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>餘額</AdminSortableTh>
                <AdminSortableTh field="total_purchased_ntd" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>累積購買</AdminSortableTh>
                <AdminSortableTh field="total_scans_used" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>掃描數</AdminSortableTh>
                <AdminSortableTh field="last_login" ordering={ordering} onChange={(o) => setParam("ordering", o)}>最近登入</AdminSortableTh>
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr
                  key={u.id}
                  className="clickable"
                  role="link"
                  tabIndex={0}
                  onClick={() => navigate(`/admin/users/${u.id}`)}
                  onKeyDown={(event) => activateAdminRow(
                    event,
                    () => navigate(`/admin/users/${u.id}`),
                  )}
                >
                  <td>
                    <div className="admin-cell-primary">{u.full_name}</div>
                    <div className="admin-cell-secondary">@{u.username} {u.is_staff && <span className="admin-staff-chip">staff</span>}</div>
                  </td>
                  <td>{u.email}</td>
                  <td className="num"><span className="admin-coin">{formatNumber(u.balance)}</span></td>
                  <td className="num">{u.total_purchased_ntd > 0 ? formatNtd(u.total_purchased_ntd) : "—"}</td>
                  <td className="num">{u.total_scans_used}</td>
                  <td>{u.last_login ? formatDateTime(u.last_login) : "從未"}</td>
                </tr>
              ))}
              {data.users.length === 0 && (
                <tr><td colSpan="6" className="admin-empty">
                  {hasFilters ? "沒有符合條件的使用者" : "尚無使用者"}
                </td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />
        </>
      )}
    </div>
  );
}

function AdminUserDetailPage() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [error, setError] = useState("");
  const [delta, setDelta] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);
  // 登入記錄（最近 50 筆；null = 載入中）
  const [loginEvents, setLoginEvents] = useState(null);
  // 訂閱管理：進入頁面載入現況（GET），開通／取消動作後以回應即時更新
  const [subscription, setSubscription] = useState(null);
  const [plans, setPlans] = useState([]);
  const [subPlanCode, setSubPlanCode] = useState("");
  const [subPeriods, setSubPeriods] = useState(1);
  const [subBusy, setSubBusy] = useState(false);
  const [subFeedback, setSubFeedback] = useState(null);
  const { confirmDialog, dialogHost } = useConfirmDialogs();

  async function load() {
    try {
      const response = await api.get(`/admin/users/${userId}/`);
      setUser(response.data);
    } catch {
      setError("找不到此使用者");
    }
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [userId]);

  // 登入事件、訂閱方案清單與訂閱現況隨使用者切換載入（失敗不擋頁面）；
  // 各狀態也一併重置，避免切到別位使用者時殘留上一位的資料
  useEffect(() => {
    setLoginEvents(null);
    setSubscription(null);
    setSubFeedback(null);
    fetchUserLoginEvents(userId)
      .then((data) => setLoginEvents(data.events || []))
      .catch(() => setLoginEvents([]));
    fetchUserSubscription(userId)
      .then((data) => setSubscription(data.subscription || null))
      .catch(() => {});
    fetchAdminSubscriptionPlans()
      .then((data) => {
        setPlans(data.plans || []);
        const firstActive = (data.plans || []).find((plan) => plan.is_active);
        if (firstActive) setSubPlanCode(firstActive.code);
      })
      .catch(() => {});
  }, [userId]);

  async function handleGrantSubscription(e) {
    e.preventDefault();
    if (!subPlanCode) {
      setSubFeedback({ tone: "bad", message: "請先選擇要開通的方案。" });
      return;
    }
    setSubBusy(true);
    setSubFeedback(null);
    try {
      const data = await adminUserSubscriptionAction(userId, "grant", subPlanCode, subPeriods);
      setSubscription(data.subscription);
      setSubFeedback({
        tone: "good",
        message: `已開通 ${data.subscription.plan_name}（${data.subscription.periods_remaining} 期），並立即結算本月贈點。`,
      });
      await load();
    } catch (err) {
      setSubFeedback({ tone: "bad", message: err?.response?.data?.detail || "開通失敗，請確認方案與期數。" });
    } finally {
      setSubBusy(false);
    }
  }

  async function handleCancelSubscription() {
    const ok = await confirmDialog(
      `確定取消 ${user?.username ?? "該使用者"} 的訂閱？（已付費的當期權益會保留到期滿）`,
      { danger: true },
    );
    if (!ok) return;
    setSubBusy(true);
    setSubFeedback(null);
    try {
      const data = await adminUserSubscriptionAction(userId, "cancel");
      setSubscription(data.subscription);
      setSubFeedback({ tone: "good", message: "已取消訂閱（當期權益保留到期滿）。" });
    } catch (err) {
      setSubFeedback({ tone: "bad", message: err?.response?.data?.detail || "取消失敗。" });
    } finally {
      setSubBusy(false);
    }
  }

  async function handleAdjust(e) {
    e.preventDefault();
    const value = parseInt(delta, 10);
    if (!value) {
      setFeedback({ tone: "bad", message: "請輸入非 0 的整數" });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const response = await api.post(`/admin/users/${userId}/adjust-coin/`, {
        delta: value,
        note: note || "管理員手動調整",
      });
      setFeedback({
        tone: "good",
        message: `已${value > 0 ? "補" : "扣"} ${Math.abs(response.data.transaction.amount)} coin，當前餘額 ${response.data.wallet_balance}`,
      });
      setDelta("");
      setNote("");
      await load();
    } catch (err) {
      setFeedback({ tone: "bad", message: err?.response?.data?.detail || "調整失敗" });
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="admin-error">{error}</div>;
  if (!user) return <div className="admin-loading">載入中…</div>;
  const w = user.wallet;

  return (
    <div className="admin-page">
      <button
        type="button"
        className="admin-back-link"
        onClick={() => navigate("/admin/users")}
      >← 回使用者列表</button>

      <header className="admin-page-head">
        <h1>{user.full_name}</h1>
        <p>@{user.username} · {user.email}</p>
      </header>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminUsersIcon /></span>基本資料</h3>
          <dl className="admin-dl">
            <dt>狀態</dt><dd>{user.is_active ? "啟用" : "停用"} {user.is_staff && <span className="admin-staff-chip">staff</span>} {user.is_superuser && <span className="admin-super-chip">superuser</span>}</dd>
            <dt>註冊時間</dt><dd>{formatDateTime(user.date_joined)}</dd>
            <dt>最後登入</dt><dd>{user.last_login ? formatDateTime(user.last_login) : "從未"}</dd>
          </dl>
        </section>

        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminTransactionsIcon /></span>點數錢包</h3>
          {w ? (
            <>
              <div className="admin-balance-big">
                {w.balance.toLocaleString()}<span> coin</span>
              </div>
              <dl className="admin-dl">
                <dt>累積購買</dt><dd>NT$ {w.total_purchased_ntd.toLocaleString()}</dd>
                <dt>累積掃描</dt><dd>{w.total_scans_used} 次</dd>
                <dt>最近月贈點</dt><dd>{w.last_bonus_year ? `${w.last_bonus_year}-${String(w.last_bonus_month).padStart(2,"0")}` : "—"}</dd>
              </dl>
            </>
          ) : <p className="admin-empty">尚未建立錢包</p>}
        </section>
      </div>

      <section className="admin-panel">
        <h3><span className="admin-panel-icon-chip"><AdminSettingsIcon /></span>調整點數</h3>
        <form className="admin-adjust-form" onSubmit={handleAdjust}>
          <div className="admin-adjust-row">
            <input
              className="admin-input"
              type="number"
              placeholder="變動金額（正=補、負=扣）"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
            />
            <input
              className="admin-input wide"
              placeholder="備註（將寫入交易紀錄）"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button className="admin-btn primary" type="submit" disabled={busy}>
              {busy ? "處理中…" : "送出"}
            </button>
          </div>
          <div className="admin-quick-row">
            {[100, 500, 1000, -100, -500].map((v) => (
              <button key={v} type="button" className="admin-quick-btn" onClick={() => setDelta(String(v))}>
                {v > 0 ? `+${v}` : v}
              </button>
            ))}
          </div>
          {feedback && (
            <div className={`admin-feedback tone-${feedback.tone}`}>{feedback.message}</div>
          )}
        </form>
      </section>

      <section className="admin-panel">
        <h3><span className="admin-panel-icon-chip"><AdminPlansIcon /></span>訂閱管理</h3>
        {subscription ? (
          <dl className="admin-dl admin-sub-current">
            <dt>方案</dt><dd>{subscription.plan_name}（{subscription.plan_code}）</dd>
            <dt>狀態</dt><dd>{subscription.status_label}</dd>
            <dt>剩餘期數</dt><dd>{subscription.periods_remaining} 期</dd>
            <dt>下次贈點時間</dt><dd>{formatDateTime(subscription.current_period_end)}</dd>
            {subscription.cancelled_at && (
              <><dt>取消時間</dt><dd>{formatDateTime(subscription.cancelled_at)}</dd></>
            )}
          </dl>
        ) : (
          <p className="admin-empty">此使用者目前沒有訂閱（或仍在載入）。</p>
        )}
        <form className="admin-sub-form" onSubmit={handleGrantSubscription}>
          <select
            className="admin-input"
            value={subPlanCode}
            onChange={(e) => setSubPlanCode(e.target.value)}
            aria-label="訂閱方案"
          >
            <option value="">選擇方案…</option>
            {plans.map((plan) => (
              <option key={plan.code} value={plan.code}>
                {plan.name} · NT$ {plan.monthly_price_ntd.toLocaleString()}/月 · {plan.monthly_coins.toLocaleString()} coin{plan.is_active ? "" : "（停用）"}
              </option>
            ))}
          </select>
          <label className="admin-sub-periods">
            期數
            <input
              className="admin-input"
              type="number"
              min={1}
              max={36}
              value={subPeriods}
              onChange={(e) => setSubPeriods(Math.min(36, Math.max(1, Number(e.target.value) || 1)))}
            />
          </label>
          <button className="admin-btn primary" type="submit" disabled={subBusy || !subPlanCode}>
            {subBusy ? "處理中…" : "開通訂閱"}
          </button>
          <button
            className="admin-btn danger"
            type="button"
            onClick={handleCancelSubscription}
            disabled={subBusy}
          >
            取消訂閱
          </button>
        </form>
        {subFeedback && (
          <div className={`admin-feedback tone-${subFeedback.tone}`}>{subFeedback.message}</div>
        )}
      </section>

      <section className="admin-panel">
        <h3><span className="admin-panel-icon-chip"><AdminUsersIcon /></span>登入記錄（最近 50 筆）</h3>
        {loginEvents === null ? (
          <div className="admin-loading">載入中…</div>
        ) : loginEvents.length === 0 ? (
          <p className="admin-empty">尚無登入紀錄</p>
        ) : (
          <ul className="admin-login-timeline">
            {loginEvents.map((event, index) => (
              <li key={`${event.created_at}-${index}`} className="admin-login-item">
                <div className="admin-login-line1">
                  <span className={`admin-login-method method-${event.method}`}>
                    {event.method_label}
                  </span>
                  <span className="admin-login-ip">{event.ip_address || "IP 未記錄"}</span>
                  <time className="admin-login-time">
                    {formatDateTime(event.created_at)}
                  </time>
                </div>
                <p className="admin-login-ua" title={event.user_agent}>{event.user_agent || "—"}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {user.ai_usage && (
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminTokensIcon /></span>AI 使用量</h3>
          <div className="admin-ai-summary">
            <div>
              <div className="admin-stat-label">總 Tokens</div>
              <div className="admin-balance-big tight">
                {user.ai_usage.total_tokens.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="admin-stat-label">Sessions</div>
              <div className="admin-balance-big tight">
                {user.ai_usage.total_sessions}
              </div>
            </div>
          </div>
          {user.ai_usage.by_provider.length > 0 && (
            <div className="admin-table-scroll admin-table-spaced">
              <table className="admin-table compact">
              <thead><tr><th>Provider</th><th>Model</th><th className="num">Sessions</th><th className="num">Tokens</th></tr></thead>
              <tbody>
                {user.ai_usage.by_provider.map((row, i) => (
                  <tr key={`${row.provider}-${row.model}-${i}`}>
                    <td>{row.provider}</td>
                    <td>{row.model || "—"}</td>
                    <td className="num">{row.sessions}</td>
                    <td className="num"><span className="admin-coin">{row.tokens.toLocaleString()}</span></td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* 該使用者的掃描紀錄：客服處理「掃描失敗卻被扣點」時的第一手資料。
          先前要切到掃描頁再搜一次網址才找得到。 */}
      <section className="admin-panel">
        <div className="admin-panel-head-row">
          <h3>
            <span className="admin-panel-icon-chip"><AdminScansIcon /></span>
            掃描紀錄（{formatNumber(user.scans_total, "0")}）
          </h3>
          {user.scans_total > 0 && (
            <NavLink to={`/admin/scans?user=${user.id}`} className="admin-panel-more">
              查看全部 →
            </NavLink>
          )}
        </div>
        {(user.recent_scans || []).length === 0 ? (
          <p className="admin-empty">此使用者尚未建立任何掃描</p>
        ) : (
          <div className="admin-table-scroll">
            <table className="admin-table compact">
              <thead>
                <tr>
                  <th>時間</th><th>網址</th><th>狀態</th>
                  <th className="num">分數</th><th className="num">問題</th>
                </tr>
              </thead>
              <tbody>
                {user.recent_scans.map((scan) => (
                  <tr
                    key={scan.id}
                    className="clickable"
                    role="link"
                    tabIndex={0}
                    onClick={() => navigate(`/admin/scans/${scan.id}`)}
                    onKeyDown={(event) => activateAdminRow(
                      event,
                      () => navigate(`/admin/scans/${scan.id}`),
                    )}
                  >
                    <td>{formatDateTime(scan.created_at)}</td>
                    <td className="truncate" title={scan.origin}>{scan.origin}</td>
                    <td>
                      <span className={`admin-status ${scan.status}`}>
                        {STATUS_LABELS[scan.status]?.label || scan.status}
                      </span>
                    </td>
                    <td className="num">{scan.overall_score ?? "—"}</td>
                    <td className="num">{scan.findings_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="admin-panel">
        <h3><span className="admin-panel-icon-chip"><AdminOrdersIcon /></span>最近 30 筆交易</h3>
        <div className="admin-table-scroll">
          <table className="admin-table compact">
          <thead>
            <tr><th>時間</th><th>類型</th><th className="num">變動</th><th className="num">餘額</th><th>備註</th></tr>
          </thead>
          <tbody>
            {user.recent_transactions.map((tx) => (
              <tr key={tx.id}>
                <td>{formatDateTime(tx.created_at)}</td>
                <td>{tx.kind_label}</td>
                <td className={`num ${tx.amount > 0 ? "tx-pos" : "tx-neg"}`}>{tx.amount > 0 ? "+" : ""}{tx.amount}</td>
                <td className="num">{tx.balance_after}</td>
                <td className="admin-cell-secondary">{tx.note}</td>
              </tr>
            ))}
            {user.recent_transactions.length === 0 && (
              <tr><td colSpan="5" className="admin-empty">尚無交易紀錄</td></tr>
            )}
          </tbody>
          </table>
        </div>
      </section>
      {dialogHost}
    </div>
  );
}

// ------ AdminDomainsPage：網域所有權驗證清單＋人工審核 ------

const DOMAIN_STATUS_OPTIONS = [
  { v: "", label: "全部狀態" },
  { v: "pending", label: "待驗證" },
  { v: "verified", label: "已驗證" },
  { v: "rejected", label: "已否決" },
  { v: "expired", label: "已過期" },
];

function AdminDomainsPage() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState({}); // domainId -> 審核備註草稿
  const [busyId, setBusyId] = useState(null);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  async function load() {
    try {
      const response = await fetchAdminDomains({
        page,
        q: query || undefined,
        status: status || undefined,
      });
      setData(response);
    } catch {
      notifyDialog("載入網域清單失敗，請稍後再試。");
    }
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [page, status, query]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    setPage(1);
    setQuery(searchInput.trim());
  }

  async function handleOverride(domain, approve) {
    const note = (notes[domain.id] || "").trim();
    const ok = await confirmDialog(
      approve
        ? `確定人工核准「${domain.domain}」（${domain.username}）？核准後同等於驗證通過，可直接用於主動式測試。`
        : `確定否決「${domain.domain}」（${domain.username}）？否決後該網域將無法用於主動式測試。`,
      { danger: !approve },
    );
    if (!ok) return;
    setBusyId(domain.id);
    try {
      const updated = await adminDomainOverride(domain.id, approve, note);
      setData((current) =>
        current
          ? { ...current, domains: current.domains.map((d) => (d.id === updated.id ? updated : d)) }
          : current,
      );
      setNotes((current) => ({ ...current, [domain.id]: "" }));
    } catch (err) {
      notifyDialog(err?.response?.data?.detail || "操作失敗，請稍後再試。");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">網域管理</h1>
        <p>所有使用者的網域所有權驗證清單；無法自行驗證的網域可人工核准（同等於驗證通過）或否決。</p>
      </header>

      <div className="admin-filter-bar">
        <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
          <input
            className="admin-input"
            type="search"
            placeholder="搜尋網域或使用者名稱…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            aria-label="搜尋網域或使用者"
          />
          <button className="admin-btn" type="submit">搜尋</button>
        </form>
        <select
          className="admin-input"
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
        >
          {DOMAIN_STATUS_OPTIONS.map((o) => (
            <option key={o.v} value={o.v}>{o.label}</option>
          ))}
        </select>
      </div>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table compact">
              <thead>
                <tr>
                  <th>網域</th>
                  <th>使用者</th>
                  <th>狀態</th>
                  <th>驗證方法</th>
                  <th>到期日</th>
                  <th>人工核准</th>
                  <th>最後錯誤</th>
                  <th>審核</th>
                </tr>
              </thead>
              <tbody>
                {data.domains.map((domain) => (
                  <tr key={domain.id}>
                    <td className="admin-cell-mono">{domain.domain}</td>
                    <td>{domain.username}</td>
                    <td>
                      <span
                        className={`admin-domain-status is-${domain.status}${domain.is_effectively_verified ? " is-effective" : ""}`}
                      >
                        {domain.status_label}
                      </span>
                      {domain.is_effectively_verified && (
                        <span className="admin-domain-effective" title="掃描閘門判定：生效中">生效中</span>
                      )}
                    </td>
                    <td>{domain.method ? domain.method_label : "—"}</td>
                    <td>{formatDateTime(domain.expires_at)}</td>
                    <td className="admin-cell-secondary">
                      {domain.admin_override
                        ? `${domain.admin_actor_username ? `by ${domain.admin_actor_username}` : "是"}${domain.admin_note ? ` · ${domain.admin_note}` : ""}`
                        : "—"}
                    </td>
                    <td className="admin-cell-secondary admin-domain-error">{domain.last_error || "—"}</td>
                    <td>
                      <div className="admin-domain-review">
                        <input
                          className="admin-input admin-domain-note"
                          placeholder="備註（選填）"
                          value={notes[domain.id] || ""}
                          onChange={(e) =>
                            setNotes((current) => ({ ...current, [domain.id]: e.target.value }))
                          }
                          aria-label={`${domain.domain} 審核備註`}
                        />
                        <button
                          className="admin-btn small"
                          type="button"
                          disabled={busyId === domain.id}
                          onClick={() => handleOverride(domain, true)}
                        >
                          {busyId === domain.id ? "…" : "人工核准"}
                        </button>
                        <button
                          className="admin-btn small danger"
                          type="button"
                          disabled={busyId === domain.id}
                          onClick={() => handleOverride(domain, false)}
                        >
                          否決
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {data.domains.length === 0 && (
                  <tr><td colSpan="8" className="admin-empty">沒有符合的網域</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
      {dialogHost}
    </div>
  );
}

const TRANSACTIONS_QUERY_DEFAULTS = { page: 1, kind: "", ordering: "-created_at" };

function AdminTransactionsPage() {
  const { params, setParam, resetFilters, hasFilters } = useListQuery(TRANSACTIONS_QUERY_DEFAULTS);
  const { page, kind, ordering } = params;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/transactions/", {
        params: { page, kind: kind || undefined, ordering },
      });
      setData(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "無法載入交易紀錄");
    } finally {
      setLoading(false);
    }
  }, [page, kind, ordering]);
  useEffect(() => { load(); }, [load]);

  const KIND_OPTIONS = [
    { v: "", label: "全部類型" },
    { v: "monthly_bonus", label: "每月贈點" },
    { v: "purchase", label: "購買" },
    { v: "scan_hold", label: "掃描預扣" },
    { v: "scan_refund", label: "掃描退款" },
    { v: "admin_adjust", label: "管理員調整" },
  ];

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>交易紀錄</h1>
        <p>所有 coin 異動的審計紀錄</p>
      </header>

      <div className="admin-filter-bar">
        <select
          className="admin-input"
          aria-label="交易類型"
          value={kind}
          onChange={(e) => setParam("kind", e.target.value)}
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.v} value={o.v}>{o.label}</option>
          ))}
        </select>
        {hasFilters && (
          <button type="button" className="admin-btn ghost" onClick={resetFilters}>清除篩選</button>
        )}
      </div>

      {error && <AdminErrorState message="無法載入交易紀錄" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入交易中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <AdminSortableTh field="created_at" ordering={ordering} onChange={(o) => setParam("ordering", o)}>時間</AdminSortableTh>
                {/* 這欄實際顯示交易對象（掃描網址或方案名），原欄名「使用者」與內容不符 */}
                <th>來源對象</th>
                <th>類型</th>
                <AdminSortableTh field="amount" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>變動</AdminSortableTh>
                <AdminSortableTh field="balance_after" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>餘額</AdminSortableTh>
                <th>操作者 / 方案</th><th>備註</th>
              </tr>
            </thead>
            <tbody>
              {data.transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{formatDateTime(tx.created_at)}</td>
                  <td>{tx.scan_origin || (tx.plan_name ? `購買 ${tx.plan_name}` : "—")}</td>
                  <td>{tx.kind_label}</td>
                  <td className={`num ${tx.amount > 0 ? "tx-pos" : "tx-neg"}`}>{tx.amount > 0 ? "+" : ""}{tx.amount}</td>
                  <td className="num">{tx.balance_after}</td>
                  <td>{tx.admin_actor_username ? `admin: ${tx.admin_actor_username}` : (tx.plan_name || tx.scan_origin || "—")}</td>
                  <td className="admin-cell-secondary">{tx.note}</td>
                </tr>
              ))}
              {data.transactions.length === 0 && (
                <tr><td colSpan="7" className="admin-empty">沒有符合的交易</td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />
        </>
      )}
    </div>
  );
}

const REVIEWS_QUERY_DEFAULTS = { page: 1, filter: "all" };

function AdminReviewsPage() {
  // filter 進網址，待辦中心才能用 /admin/reviews?filter=reported 帶著篩選跳過來
  const { params, setParam } = useListQuery(REVIEWS_QUERY_DEFAULTS);
  const { page, filter } = params;
  const [data, setData] = useState(null);
  const [draftReplies, setDraftReplies] = useState({});
  const [busyId, setBusyId] = useState(null);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  const load = useCallback(async () => {
    const response = await api.get("/admin/reviews/", {
      params: {
        page,
        pending: filter === "pending" ? "1" : undefined,
        reported: filter === "reported" ? "1" : undefined,
        status: filter === "hidden" ? "hidden" : undefined,
      },
    });
    setData(response.data);
    setDraftReplies(Object.fromEntries(
      response.data.reviews.map((review) => [review.id, review.response?.body || ""]),
    ));
  }, [page, filter]);
  useEffect(() => { load(); }, [load]);

  async function handleReply(review) {
    const reply = (draftReplies[review.id] || "").trim();
    if (!reply) {
      notifyDialog("請先輸入官方回覆；如要移除既有回覆，請使用「移除回覆」。");
      return;
    }
    setBusyId(review.id);
    try {
      await api.post(`/admin/reviews/${review.id}/reply/`, { reply });
      await load();
    } catch (error) {
      notifyDialog(error.response?.data?.detail || "回覆儲存失敗");
    } finally {
      setBusyId(null);
    }
  }

  async function removeReply(review) {
    if (!(await confirmDialog("確定移除這則官方回覆嗎？", { danger: true }))) return;
    setBusyId(review.id);
    try {
      await api.delete(`/admin/reviews/${review.id}/reply/`);
      await load();
    } catch (error) {
      notifyDialog(error.response?.data?.detail || "移除回覆失敗");
    } finally {
      setBusyId(null);
    }
  }

  async function toggleVisibility(review) {
    const hiding = review.status === "published";
    const message = hiding
      ? "確定隱藏這則評論嗎？前台會立即停止顯示，相關待處理檢舉將標記為已處理。"
      : "確定重新公開這則評論嗎？相關待處理檢舉將標記為不成立。";
    if (!(await confirmDialog(message, { danger: hiding }))) return;
    setBusyId(review.id);
    try {
      await api.patch(`/admin/reviews/${review.id}/moderate/`, {
        status: hiding ? "hidden" : "published",
      });
      await load();
    } catch (error) {
      notifyDialog(error.response?.data?.detail || "審核狀態更新失敗");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>評論治理</h1>
        <p>官方回覆、內容檢舉與公開狀態；使用者評分和原文保持唯讀。</p>
      </header>

      {data && (
        <div className="admin-stat-grid">
          <AdminStatCard label="總評論數" value={data.overall_total} tone="cyan" />
          <AdminStatCard label="平均評分" value={data.avg_rating ? <>{data.avg_rating} <AdminStarIcon className="admin-star-icon" /></> : "—"} tone="good" />
          <AdminStatCard label="待回覆" value={data.pending_count} tone={data.pending_count > 0 ? "warn" : "good"} />
          <AdminStatCard label="待審檢舉" value={data.reported_count} tone={data.reported_count > 0 ? "warn" : "good"} />
        </div>
      )}

      <div className="admin-filter-bar">
        <label>
          <span className="sr-only">篩選評論</span>
          <select
            className="admin-input"
            value={filter}
            onChange={(event) => setParam("filter", event.target.value)}
          >
            <option value="all">全部評論</option>
            <option value="pending">只看待回覆</option>
            <option value="reported">只看待審檢舉</option>
            <option value="hidden">只看已隱藏</option>
          </select>
        </label>
        {data && <span className="admin-cell-secondary">目前顯示 {data.total} 則 · 已隱藏 {data.hidden_count} 則</span>}
      </div>

      {data && data.reviews.map((review) => (
        <article
          key={review.id}
          className={[
            "admin-review",
            review.is_pending ? "is-pending" : "",
            review.status === "hidden" ? "is-hidden" : "",
            review.pending_report_count > 0 || review.response_pending_report_count > 0
              ? "is-reported"
              : "",
          ].filter(Boolean).join(" ")}
        >
          <header className="admin-review-head">
            <div>
              <div className="admin-review-user">
                {review.full_name}
                <span className="admin-cell-secondary"> @{review.username}</span>
              </div>
              <div className="admin-review-time">
                {formatDateTime(review.created_at)}
                {review.updated_at !== review.created_at && " · 使用者已編輯"}
              </div>
            </div>
            <div className="admin-review-rating" aria-label={`${review.rating} 顆星`}>
              {Array.from({ length: 5 }, (_, i) => (
                <AdminStarIcon key={i} filled={i < review.rating} className="admin-star-icon" />
              ))}
              <span className="admin-cell-secondary"> ({review.rating})</span>
            </div>
          </header>

          <div className="admin-review-status-row">
            <span className={review.status === "published" ? "status-active" : "status-inactive"}>
              {review.status === "published" ? "前台公開" : "已隱藏"}
            </span>
            {review.is_pending && <span className="admin-status">待回覆</span>}
            {review.pending_report_count > 0 && (
              <span className="admin-status failed">待審檢舉 {review.pending_report_count}</span>
            )}
            {review.response_pending_report_count > 0 && (
              <span className="admin-status failed">
                官方回覆待審 {review.response_pending_report_count}
              </span>
            )}
            {review.report_count > review.pending_report_count && (
              <span className="admin-cell-secondary">歷史檢舉 {review.report_count}</span>
            )}
            {review.response_report_count > review.response_pending_report_count && (
              <span className="admin-cell-secondary">
                官方回覆歷史檢舉 {review.response_report_count}
              </span>
            )}
          </div>

          {review.title && <h2 className="admin-review-title">{review.title}</h2>}
          <p className="admin-review-body">{review.comment || "（舊版評論未填文字）"}</p>
          <p className="admin-review-public-name">
            前台顯示：{review.show_partial_email ? "遮罩後的部分 Email" : "完全匿名"}
          </p>

          <div className="admin-review-reply-section">
            <label className="admin-review-reply-field">
              <span>ARGUS 團隊官方回覆</span>
              <textarea
                className="admin-input admin-reply-input"
                placeholder="清楚回應使用者的具體意見…"
                rows={3}
                maxLength={2000}
                value={draftReplies[review.id] ?? ""}
                onChange={(event) => setDraftReplies({
                  ...draftReplies,
                  [review.id]: event.target.value,
                })}
              />
            </label>
            <div className="admin-review-actions">
              <button
                type="button"
                className="admin-btn primary"
                disabled={busyId === review.id}
                onClick={() => handleReply(review)}
              >
                {review.response ? "更新官方回覆" : "送出官方回覆"}
              </button>
              {review.response && (
                <button
                  type="button"
                  className="admin-btn danger"
                  disabled={busyId === review.id}
                  onClick={() => removeReply(review)}
                >
                  移除回覆
                </button>
              )}
              <button
                type="button"
                className={`admin-btn ${review.status === "published" ? "danger" : ""}`}
                disabled={busyId === review.id}
                onClick={() => toggleVisibility(review)}
              >
                {review.status === "published" ? "隱藏評論" : "重新公開"}
              </button>
            </div>
          </div>

          {review.response && (
            <div className="admin-review-existing-reply">
              <StatusDoneGlyph className="admin-inline-glyph" /> 官方回覆最後更新於 {formatDateTime(review.response.updated_at)}
              {review.response.author_username ? ` · ${review.response.author_username}` : ""}
            </div>
          )}
        </article>
      ))}
      {data && data.reviews.length === 0 && (
        <div className="admin-empty admin-panel">沒有符合條件的評論</div>
      )}
      {data && <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />}
      {dialogHost}
    </div>
  );
}
// user 是從使用者詳情「查看全部」帶過來的精確篩選；必須列在預設裡，
// 否則 useListQuery 不會讀它，網址帶著參數但列表不會套用（靜默失效）。
const SCANS_QUERY_DEFAULTS = { page: 1, q: "", status: "", user: "", ordering: "-created_at" };

function AdminScansPage() {
  const navigate = useNavigate();
  const { params, setParam, setParams, resetFilters, hasFilters } = useListQuery(SCANS_QUERY_DEFAULTS);
  const { page, q, status: statusFilter, user: userFilter, ordering } = params;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchDraft, setSearchDraft] = useState(q);

  useEffect(() => { setSearchDraft(q); }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/scans/", {
        params: {
          q: q || undefined,
          status: statusFilter || undefined,
          user: userFilter || undefined,
          page,
          ordering,
        },
      });
      setData(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "無法載入掃描任務");
    } finally {
      setLoading(false);
    }
  }, [q, statusFilter, userFilter, page, ordering]);
  useEffect(() => { load(); }, [load]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    setParams({ q: searchDraft.trim() });
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>掃描</h1>
        <p>所有使用者的掃描任務</p>
      </header>

      <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
        <input
          className="admin-input"
          placeholder="搜尋網址或使用者"
          aria-label="搜尋掃描"
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
        />
        <select
          className="admin-input"
          aria-label="掃描狀態"
          value={statusFilter}
          onChange={(e) => setParam("status", e.target.value)}
        >
          <option value="">全部狀態</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
        <button className="admin-btn" type="submit">搜尋</button>
        {hasFilters && (
          <button type="button" className="admin-btn ghost" onClick={resetFilters}>清除篩選</button>
        )}
      </form>

      {userFilter && (
        <div className="admin-scope-note">
          <span>目前只顯示單一使用者的掃描</span>
          <button type="button" className="admin-btn ghost" onClick={() => setParam("user", "")}>
            顯示全部使用者
          </button>
        </div>
      )}

      {error && <AdminErrorState message="無法載入掃描任務" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入掃描中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <AdminSortableTh field="created_at" ordering={ordering} onChange={(o) => setParam("ordering", o)}>時間</AdminSortableTh>
                <th>使用者</th><th>網址</th>
                <th>狀態</th><th>模式</th>
                <AdminSortableTh field="overall_score" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>分數</AdminSortableTh>
                <AdminSortableTh field="pages_count" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>頁數</AdminSortableTh>
                <AdminSortableTh field="findings_count" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>問題</AdminSortableTh>
                {/* 耗時不可排序：duration_sec 是 serializer 由 started_at/completed_at 現算的，資料庫無此欄位 */}
                <th className="num">耗時</th>
              </tr>
            </thead>
            <tbody>
              {data.scans.map((s) => (
                <tr
                  key={s.id}
                  className="clickable"
                  role="link"
                  tabIndex={0}
                  onClick={() => navigate(`/admin/scans/${s.id}`)}
                  onKeyDown={(event) => activateAdminRow(
                    event,
                    () => navigate(`/admin/scans/${s.id}`),
                  )}
                >
                  <td>{formatDateTime(s.created_at)}</td>
                  <td>{s.username}</td>
                  <td className="truncate" title={s.origin}>{s.origin}</td>
                  <td><span className={`admin-status ${s.status}`}>{STATUS_LABELS[s.status]?.label || s.status}</span></td>
                  <td>{s.scan_mode === "active" ? "主動" : "被動"}</td>
                  <td className="num">{s.overall_score ?? "—"}</td>
                  <td className="num">{s.pages_count}</td>
                  <td className="num">{s.findings_count}</td>
                  <td className="num">{formatDuration(s.duration_sec)}</td>
                </tr>
              ))}
              {data.scans.length === 0 && (
                <tr><td colSpan="9" className="admin-empty">沒有符合的掃描</td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />
        </>
      )}
    </div>
  );
}

// 爬取警告面板。warning_summary 的結構由 crawler.py 決定：
//   { blocked_urls: [{url, reason}], failed_urls: [{url, reason}],
//     screenshot_failures: [...], tech_stack: [...] }
// 清單可能很長，預設收合只顯示筆數，展開才列出明細。
function AdminScanWarnings({ summary }) {
  const groups = [
    { key: "blocked_urls", label: "被阻擋的 URL", hint: "robots.txt / 403 / 429", tone: "warn" },
    { key: "failed_urls", label: "抓取失敗的 URL", hint: "連線或解析失敗", tone: "bad" },
    { key: "screenshot_failures", label: "截圖失敗", hint: "頁面有抓到，但截圖沒成功", tone: "warn" },
  ];
  const present = groups.filter((g) => (summary?.[g.key] || []).length > 0);
  const techStack = summary?.tech_stack || [];
  if (present.length === 0 && techStack.length === 0) return null;

  return (
    <section className="admin-panel">
      <h3><span className="admin-panel-icon-chip"><AdminAlertIcon /></span>爬取警告</h3>

      {techStack.length > 0 && (
        <div className="admin-tech-stack">
          <span className="admin-cell-secondary">偵測到的技術棧：</span>
          {techStack.map((tech, index) => (
            <span className="admin-tech-chip" key={`${tech}-${index}`}>
              {typeof tech === "string" ? tech : JSON.stringify(tech)}
            </span>
          ))}
        </div>
      )}

      {present.map((group) => {
        const rows = summary[group.key];
        return (
          <details className="admin-warn-group" key={group.key}>
            <summary>
              <span className={`admin-warn-count tone-${group.tone}`}>{rows.length}</span>
              <span className="admin-warn-label">{group.label}</span>
              <span className="admin-cell-secondary">{group.hint}</span>
            </summary>
            <ul className="admin-warn-list">
              {rows.map((row, index) => (
                <li key={`${group.key}-${index}`}>
                  <code className="admin-warn-url">
                    {typeof row === "string" ? row : (row.url || JSON.stringify(row))}
                  </code>
                  {row && row.reason && (
                    <span className="admin-warn-reason">{row.reason}</span>
                  )}
                </li>
              ))}
            </ul>
          </details>
        );
      })}
    </section>
  );
}

// 掃描進行中與可重排的狀態集合；與後端 admin_api/views.py 的判定一致
const CANCELLABLE_STATUSES = ["queued", "crawling", "scanning", "agent_testing"];
const REQUEUEABLE_STATUSES = ["failed", "cancelled"];

function AdminScanDetailPage() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  const load = useCallback(async () => {
    setError(null);
    try {
      const response = await api.get(`/admin/scans/${scanId}/`);
      setData(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "找不到此掃描");
    }
  }, [scanId]);

  useEffect(() => { load(); }, [load]);

  async function handleCancel() {
    const ok = await confirmDialog(
      "確定終止這個掃描嗎？worker 會在下一個檢查點停下，預扣的點數會全額退回使用者。",
      { danger: true },
    );
    if (!ok) return;
    setBusy(true);
    setFeedback(null);
    try {
      const response = await api.post(`/admin/scans/${scanId}/cancel/`);
      setFeedback({
        tone: "good",
        message: response.data.refunded > 0
          ? `已終止，退回 ${response.data.refunded} coin。`
          : "已終止（此掃描沒有待退的預扣）。",
      });
      await load();
    } catch (err) {
      notifyDialog(err?.response?.data?.detail || "終止失敗");
    } finally {
      setBusy(false);
    }
  }

  async function handleRequeue() {
    const ok = await confirmDialog(
      "確定重新排入佇列嗎？依產品決策重排不會再次扣點，等同免費重跑一次，"
      + "這個動作會寫入操作日誌。",
      { danger: false },
    );
    if (!ok) return;
    setBusy(true);
    setFeedback(null);
    try {
      await api.post(`/admin/scans/${scanId}/requeue/`);
      setFeedback({ tone: "good", message: "已重新排入佇列，未扣點。" });
      await load();
    } catch (err) {
      notifyDialog(err?.response?.data?.detail || "重排失敗");
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <div className="admin-page">
        <AdminErrorState message="無法載入掃描" detail={error} onRetry={load} />
      </div>
    );
  }
  if (!data) return <div className="admin-page"><AdminSkeleton variant="detail" rows={3} /></div>;
  const s = data.scan;
  const canCancel = CANCELLABLE_STATUSES.includes(s.status);
  const canRequeue = REQUEUEABLE_STATUSES.includes(s.status);

  return (
    <div className="admin-page">
      <button type="button" className="admin-back-link" onClick={() => navigate("/admin/scans")}>← 回掃描列表</button>
      <header className="admin-page-head">
        <div>
          <h1>掃描 #{s.id}</h1>
          <p>{s.origin} · {s.username}</p>
        </div>
        <div className="admin-page-head-links">
          {canCancel && (
            <button type="button" className="admin-btn danger" disabled={busy} onClick={handleCancel}>
              {busy ? "處理中…" : "終止掃描"}
            </button>
          )}
          {canRequeue && (
            <button type="button" className="admin-btn primary" disabled={busy} onClick={handleRequeue}>
              {busy ? "處理中…" : "重新排入佇列"}
            </button>
          )}
        </div>
      </header>

      {feedback && (
        <div className={`admin-feedback tone-${feedback.tone}`}>{feedback.message}</div>
      )}

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminScansIcon /></span>狀態</h3>
          <dl className="admin-dl">
            <dt>狀態</dt><dd><span className={`admin-status ${s.status}`}>{STATUS_LABELS[s.status]?.label || s.status}</span></dd>
            <dt>模式</dt><dd>{s.scan_mode === "active" ? "主動測試" : "被動偵測"}</dd>
            <dt>建立時間</dt><dd>{formatDateTime(s.created_at)}</dd>
            <dt>完成時間</dt><dd>{formatDateTime(s.completed_at)}</dd>
            <dt>耗時</dt><dd>{formatDuration(s.duration_sec)}</dd>
          </dl>
        </section>

        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminOrdersIcon /></span>結果摘要</h3>
          <dl className="admin-dl">
            <dt>總分</dt><dd>{s.overall_score ?? "—"}</dd>
            <dt>頁數</dt><dd>{s.pages_count}</dd>
            <dt>問題數</dt><dd>{s.findings_count}</dd>
            <dt>最大頁數設定</dt><dd>{s.max_pages}</dd>
          </dl>
        </section>
      </div>

      {data.category_scores && Object.keys(data.category_scores).length > 0 && (
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminTrendIcon /></span>各類別分數</h3>
          <div className="admin-cat-scores">
            {Object.entries(data.category_scores).map(([cat, score]) => (
              <div key={cat} className="admin-cat-score-item">
                <div className="admin-cat-score-label">{cat.toUpperCase()}</div>
                <div className="admin-cat-score-value">{Math.round(score)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 優先處置建議：後端已依 priority_score 降冪排好 */}
      {(data.top_actions || []).length > 0 && (
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminAlertIcon /></span>優先處置建議（{data.top_actions.length}）</h3>
          <ol className="admin-top-actions">
            {data.top_actions.map((action, index) => (
              <li className="admin-top-action" key={`${action.title}-${index}`}>
                <span className="admin-top-action-rank">{index + 1}</span>
                <div className="admin-top-action-body">
                  <div className="admin-top-action-title">{action.title}</div>
                  <div className="admin-top-action-meta">
                    <span className={`severity ${action.severity}`}>{action.severity}</span>
                    <span className={`category-pill cat-${action.category}`}>
                      {String(action.category || "").toUpperCase()}
                    </span>
                    <span className="admin-cell-secondary">
                      priority {Math.round(action.priority_score || 0)}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* 爬取警告：被 robots/403/429 擋掉與抓取失敗的 URL。
          分數偏低時多半能在這裡找到原因（爬不到頁就評不了分）。 */}
      <AdminScanWarnings summary={data.warning_summary} />

      {data.error_message && (
        <section className="admin-panel admin-panel-danger">
          <h3><span className="admin-panel-icon-chip"><AdminAlertIcon /></span>錯誤訊息</h3>
          <pre className="admin-error-pre">{data.error_message}</pre>
        </section>
      )}

      <div className="admin-link-row">
        <NavLink to={`/scans/${s.id}`} className="admin-btn">
          以使用者視角查看詳情報告 →
        </NavLink>
        {/* 已完成的掃描其預扣已結算，不適用 refund_full_for_scan；
            要補償得走使用者頁的「調整點數」，不另做第二套退款路徑。 */}
        {s.user_id && (
          <NavLink to={`/admin/users/${s.user_id}`} className="admin-btn">
            查看使用者 / 調整點數 →
          </NavLink>
        )}
      </div>
      {dialogHost}
    </div>
  );
}

// ------ AdminContentPage：內容速覽（編輯走 Jazzmin Django Admin） ------

// ------ 通用 CMS CRUD 元件 ------
function AdminCmsManager({ schema }) {
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null); // null 或 item or "new"
  const [draft, setDraft] = useState({});
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState(false);
  const { confirmDialog, dialogHost } = useConfirmDialogs();

  async function load() {
    const r = await api.get(schema.endpoint);
    setItems(r.data.items || []);
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [schema.endpoint]);

  function startNew() {
    const blank = {};
    for (const f of schema.fields) {
      blank[f.key] = f.default !== undefined ? f.default :
        (f.type === "boolean" ? false :
        (f.type === "number" ? 0 :
        (f.type === "json" ? [] : "")));
    }
    setDraft(blank);
    setEditing("new");
    setFeedback(null);
  }

  function startEdit(item) {
    setDraft({ ...item });
    setEditing(item);
    setFeedback(null);
  }

  function cancel() {
    setEditing(null);
    setDraft({});
    setFeedback(null);
  }

  async function save(e) {
    e?.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      // 處理 JSON 欄位（skills 等存 array）
      const payload = { ...draft };
      for (const f of schema.fields) {
        if (f.type === "json" && typeof payload[f.key] === "string") {
          payload[f.key] = payload[f.key]
            .split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
        }
      }
      if (editing === "new") {
        await api.post(schema.endpoint, payload);
      } else {
        await api.put(`${schema.endpoint}${editing.id}/`, payload);
      }
      setFeedback({ tone: "good", message: "已儲存" });
      await load();
      setTimeout(() => cancel(), 600);
    } catch (err) {
      const data = err?.response?.data;
      const msg = data
        ? Object.entries(data).map(([k, v]) =>
            `${k}：${Array.isArray(v) ? v.join(",") : v}`).join("；")
        : "儲存失敗";
      setFeedback({ tone: "bad", message: msg });
    } finally {
      setBusy(false);
    }
  }

  async function remove(item) {
    const label = item[schema.titleField || "name"] || "#" + item.id;
    if (!(await confirmDialog(`確定刪除「${label}」？`, { danger: true }))) return;
    await api.delete(`${schema.endpoint}${item.id}/`);
    await load();
  }

  return (
    <>
    <section className="admin-panel">
      <div className="admin-panel-head-row">
        <h3><span className="admin-panel-icon-chip"><AdminContentIcon /></span>{schema.title}（{items.length}）</h3>
        <div className="admin-panel-head-actions">
          {schema.previewPath && (
            <a
              className="admin-btn"
              href={schema.previewPath}
              target="_blank"
              rel="noreferrer noopener"
              title="另開新分頁預覽前台效果"
            >
              {schema.previewLabel || "預覽前台 ↗"}
            </a>
          )}
          <button type="button" className="admin-btn primary" onClick={startNew}>
            + 新增
          </button>
        </div>
      </div>

      {/* 列表 */}
      <div className="admin-table-scroll">
        <table className="admin-table">
        <thead>
          <tr>
            {schema.displayFields.map((f) => (
              <th key={f.key} className={f.num ? "num" : ""}>{f.label}</th>
            ))}
            <th className="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              {schema.displayFields.map((f) => (
                <td key={f.key} className={f.num ? "num" : ""}>
                  {f.render ? f.render(item) : (item[f.key] ?? "—")}
                </td>
              ))}
              <td>
                <button type="button" className="admin-btn small" onClick={() => startEdit(item)}>編輯</button>
                <button type="button" className="admin-btn small danger" onClick={() => remove(item)}>刪</button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={schema.displayFields.length + 1} className="admin-empty">
              尚無資料，點上方「+ 新增」開始
            </td></tr>
          )}
        </tbody>
        </table>
      </div>

      {/* 編輯 form modal */}
      <AdminModal
        open={Boolean(editing)}
        onClose={cancel}
        onSubmit={save}
        title={editing === "new" ? `新增${schema.title}` : `編輯 #${editing?.id}`}
        footer={
          <>
            <button type="button" className="admin-btn" onClick={cancel}>取消</button>
            <button type="submit" className="admin-btn primary" disabled={busy}>
              {busy ? "儲存中…" : "儲存"}
            </button>
          </>
        }
      >
        <>
              {schema.fields.map((f) => (
                <div key={f.key} className="wizard-field">
                  <label htmlFor={`cms-${f.key}`}>
                    {f.label}{f.required && " *"}
                    {f.hint && <span className="wizard-field-hint">{f.hint}</span>}
                  </label>
                  {f.type === "textarea" ? (
                    <textarea
                      id={`cms-${f.key}`}
                      className="admin-input"
                      rows={f.rows || 3}
                      value={draft[f.key] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    />
                  ) : f.type === "boolean" ? (
                    <label className="admin-checkbox">
                      <input
                        type="checkbox"
                        checked={!!draft[f.key]}
                        onChange={(e) => setDraft({ ...draft, [f.key]: e.target.checked })}
                      /> 啟用
                    </label>
                  ) : f.type === "select" ? (
                    <select
                      id={`cms-${f.key}`}
                      className="admin-input"
                      value={draft[f.key] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    >
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  ) : f.type === "json" ? (
                    <input
                      id={`cms-${f.key}`}
                      className="admin-input"
                      placeholder="用逗號分隔，例：React,Django,Figma"
                      value={Array.isArray(draft[f.key]) ? draft[f.key].join(", ") : (draft[f.key] || "")}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    />
                  ) : (
                    <input
                      id={`cms-${f.key}`}
                      className="admin-input"
                      type={f.type === "number" ? "number" : (f.type === "datetime" ? "datetime-local" : "text")}
                      value={draft[f.key] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [f.key]:
                        f.type === "number" ? Number(e.target.value) : e.target.value })}
                    />
                  )}
                </div>
              ))}
        {feedback && (
          <div className={`admin-feedback tone-${feedback.tone}`}>{feedback.message}</div>
        )}
        </>
      </AdminModal>
    </section>
    {dialogHost}
    </>
  );
}

const FEATURE_SCHEMA = {
  endpoint: "/admin/cms/features/",
  title: "專案特色卡片",
  previewPath: "/project",
  previewLabel: "預覽 /project",
  titleField: "title",
  fields: [
    { key: "title", label: "標題", type: "text", required: true },
    { key: "icon", label: "圖示 emoji", type: "text", hint: "例：🕷️ 🔍 🤖" },
    { key: "description", label: "說明", type: "textarea", rows: 3, required: true },
    { key: "sort_order", label: "排序", type: "number", default: 0 },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
  ],
  displayFields: [
    { key: "sort_order", label: "順序", num: true },
    { key: "icon", label: "圖示", render: (i) => <span className="admin-icon-lg">{i.icon}</span> },
    { key: "title", label: "標題" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? <StatusDoneGlyph className="admin-bool-glyph" /> : "—" },
  ],
};

const TEAM_SCHEMA = {
  endpoint: "/admin/cms/team/",
  title: "團隊成員",
  previewPath: "/team",
  previewLabel: "預覽 /team",
  titleField: "name",
  fields: [
    { key: "name", label: "姓名", type: "text", required: true },
    { key: "role", label: "角色", type: "text", required: true },
    { key: "avatar_emoji", label: "頭像 emoji", type: "text", hint: "例：🧑‍💻 🎨" },
    { key: "bio", label: "簡介", type: "textarea", rows: 3 },
    { key: "skills", label: "技能（逗號分隔）", type: "json" },
    { key: "email", label: "email", type: "text" },
    { key: "github_url", label: "GitHub URL", type: "text" },
    { key: "sort_order", label: "排序", type: "number", default: 0 },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
  ],
  displayFields: [
    { key: "sort_order", label: "順序", num: true },
    { key: "avatar_emoji", label: "頭像", render: (i) => <span className="admin-icon-lg">{i.avatar_emoji}</span> },
    { key: "name", label: "姓名" },
    { key: "role", label: "角色" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? <StatusDoneGlyph className="admin-bool-glyph" /> : "—" },
  ],
};

const RELEASE_SCHEMA = {
  endpoint: "/admin/cms/releases/",
  title: "APP / PWA 版本",
  previewPath: "/download",
  previewLabel: "預覽 /download",
  titleField: "version",
  fields: [
    { key: "version", label: "版本", type: "text", required: true, hint: "例：1.0.0" },
    { key: "platform", label: "平台", type: "select", default: "pwa",
      options: [
        { value: "pwa", label: "PWA（瀏覽器安裝）" },
        { value: "android", label: "Android" },
        { value: "ios", label: "iOS" },
        { value: "desktop", label: "桌面" },
      ] },
    { key: "release_notes", label: "更新說明", type: "textarea", rows: 4 },
    { key: "download_url", label: "下載連結", type: "text", hint: "PWA 留空" },
    { key: "icon_url", label: "圖示 URL", type: "text" },
    { key: "is_latest", label: "標記為最新版", type: "boolean", default: false },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
    { key: "released_at", label: "發布時間", type: "datetime", required: true },
  ],
  displayFields: [
    { key: "version", label: "版本" },
    { key: "platform", label: "平台" },
    { key: "is_latest", label: "最新", render: (i) => i.is_latest ? <StatusDoneGlyph className="admin-bool-glyph" /> : "—" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? <StatusDoneGlyph className="admin-bool-glyph" /> : "—" },
  ],
};

const MILESTONE_SCHEMA = {
  endpoint: "/admin/cms/milestones/",
  title: "開發里程碑",
  previewPath: "/project",
  previewLabel: "預覽 /project（timeline）",
  titleField: "title",
  fields: [
    { key: "title", label: "標題", type: "text", required: true },
    { key: "date", label: "日期（YYYY-MM-DD）", type: "text", required: true, hint: "例：2026-06-04" },
    { key: "icon", label: "圖示 emoji", type: "text", hint: "例：🚀 🎯 ✨" },
    { key: "description", label: "說明", type: "textarea", rows: 3 },
    { key: "sort_order", label: "排序", type: "number", default: 0 },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
  ],
  displayFields: [
    { key: "sort_order", label: "順序", num: true },
    { key: "icon", label: "圖示" },
    { key: "title", label: "標題" },
    { key: "date", label: "日期" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? <StatusDoneGlyph className="admin-bool-glyph" /> : "—" },
  ],
};

const CONTENT_TABS = [
  { key: "features", label: "專案特色", schema: FEATURE_SCHEMA },
  { key: "team", label: "團隊成員", schema: TEAM_SCHEMA },
  { key: "releases", label: "APP / PWA 版本", schema: RELEASE_SCHEMA },
  { key: "milestones", label: "開發里程碑", schema: MILESTONE_SCHEMA },
];

function AdminContentPage() {
  const [tab, setTab] = useState("features");
  const active = CONTENT_TABS.find((t) => t.key === tab);
  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>內容管理</h1>
        <p>編輯前台公開頁的卡片內容；存檔後前台即時生效</p>
      </header>

      <div className="admin-tab-row">
        {CONTENT_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`admin-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <AdminCmsManager key={tab} schema={active.schema} />
    </div>
  );
}

// 內部成本估算（依 log/2026-06-14_ui-ux-billing-cms-audit.md 中的推算）：
//   - MiniMax M2 token 成本：每 12 頁 scan ≈ NT$0.43
//   - 伺服器月固定費攤提（200 scans/月）：每 scan ≈ NT$7.5
//   - 合計每 scan ≈ NT$8 → 每頁 ≈ NT$0.67（COIN = PAGE）
const COIN_COST_NTD = 0.67;

function planEconomics(plan) {
  const coin = plan.coin_amount || 0;
  const price = plan.price_ntd || 0;
  const cost = Number((coin * COIN_COST_NTD).toFixed(1));
  const margin = price - cost;
  const marginPct = price > 0 ? Math.round((margin / price) * 100) : 0;
  // pages = coin（五維全選每頁 10 coin＝5 維 × ARGUS_COIN_PER_CATEGORY）
  // 但這裡是「使用者能掃幾頁」直觀感受，所以直接顯示 coin / 10
  const pagesEstimate = Math.floor(coin / 10);
  return { cost, margin, marginPct, pagesEstimate };
}

function AdminSettingsPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/admin/settings/")
      .then((r) => setData(r.data))
      .catch((err) => setError(err.response?.data?.detail || "讀取設定失敗"));
  }, []);

  if (error) return <div className="admin-error">{error}</div>;
  if (!data) return <div className="admin-loading">載入中…</div>;

  const Section = ({ title, rows }) => (
    <section className="admin-panel">
      <h3><span className="admin-panel-icon-chip"><AdminSettingsIcon /></span>{title}</h3>
      <div className="admin-table-scroll">
        <table className="admin-table compact">
        <tbody>
          {rows.map(([k, v]) => {
            let display;
            if (v === true) display = <span className="status-active">是 / 已設定</span>;
            else if (v === false) display = <span className="status-inactive">否 / 未設定</span>;
            else if (Array.isArray(v)) display = v.join(", ");
            else display = String(v);
            return (
              <tr key={k}>
                <td className="admin-cell-mono">{k}</td>
                <td>{display}</td>
              </tr>
            );
          })}
        </tbody>
        </table>
      </div>
    </section>
  );

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>系統資訊</h1>
        <p>{data.note}</p>
      </header>
      <Section title="計費" rows={Object.entries(data.billing)} />
      <Section title="Hermes-Agent" rows={Object.entries(data.agent)} />
      <Section title="Email 寄送" rows={Object.entries(data.email)} />
      <Section title="第三方登入 / API 金鑰" rows={[
        ...Object.entries(data.auth),
        ...Object.entries(data.providers),
      ]} />
      <Section title="部署" rows={Object.entries(data.deployment)} />
    </div>
  );
}

function AdminPlansPage() {
  const [plans, setPlans] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const { confirmDialog, dialogHost } = useConfirmDialogs();

  useEffect(() => {
    api.get("/admin/cms/plans/").then((r) => setPlans(r.data.items || [])).catch(() => {});
  }, []);

  function openNew() {
    setForm({ name: "", price_ntd: 0, coin_amount: 100, description: "", badge: "", is_active: true, sort_order: 0 });
    setEditing("new");
  }
  function openEdit(plan) {
    setForm({ ...plan });
    setEditing(plan);
  }
  async function handleSave() {
    if (editing === "new") {
      await api.post("/admin/cms/plans/", form);
    } else {
      await api.patch(`/admin/cms/plans/${editing.id}/`, form);
    }
    setEditing(null);
    const r = await api.get("/admin/cms/plans/");
    setPlans(r.data.items || []);
  }
  async function handleDelete(id) {
    if (!(await confirmDialog("確定刪除此方案？", { danger: true }))) return;
    await api.delete(`/admin/cms/plans/${id}/`);
    const r = await api.get("/admin/cms/plans/");
    setPlans(r.data.items || []);
  }

  const coinPerNtd = (plan) => plan.price_ntd > 0 ? (plan.coin_amount / plan.price_ntd).toFixed(2) : "—";

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">方案管理</h1>
        <button className="admin-btn primary" onClick={openNew}>＋ 新增方案</button>
      </header>

      <p className="admin-page-note">
        定價建議：每 coin 內部成本約 NT$ {COIN_COST_NTD}（含 MiniMax token 與伺服器攤提）；
        毛利率 80% 以上算健康，低於 50% 請重新定價。
      </p>

      <div className="admin-plans-grid">
        {plans.map((plan) => {
          const econ = planEconomics(plan);
          const marginTone = econ.marginPct >= 80 ? "good" : econ.marginPct >= 50 ? "warn" : "bad";
          return (
            <div key={plan.id} className={`admin-plan-card ${plan.is_active ? "" : "is-inactive"}`}>
              {plan.badge && <span className="admin-plan-badge">{plan.badge}</span>}
              <h3 className="admin-plan-name">{plan.name}</h3>
              <p className="admin-plan-price">NT$ {(plan.price_ntd || 0).toLocaleString()}</p>
              <p className="admin-plan-coin">{(plan.coin_amount || 0).toLocaleString()} Coin</p>
              <p className="admin-plan-rate">{coinPerNtd(plan)} coin/NT$ · ≈ {econ.pagesEstimate.toLocaleString()} 頁掃描</p>

              <dl className="admin-plan-econ">
                <dt>內部成本</dt>
                <dd>NT$ {econ.cost.toLocaleString()}</dd>
                <dt>毛利</dt>
                <dd className={`tone-${marginTone}`}>
                  NT$ {econ.margin.toLocaleString()}（{econ.marginPct}%）
                </dd>
              </dl>

              {plan.description && <p className="admin-plan-desc">{plan.description}</p>}
              <div className="admin-plan-actions">
                <button onClick={() => openEdit(plan)}>編輯</button>
                <button className="danger" onClick={() => handleDelete(plan.id)}>刪除</button>
                <span className={plan.is_active ? "status-active" : "status-inactive"}>
                  {plan.is_active ? "啟用" : "停用"}
                </span>
              </div>
            </div>
          );
        })}
        {!plans.length && <div className="admin-empty">尚無方案</div>}
      </div>

      <AdminModal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "新增方案" : "編輯方案"}
        size="sm"
        footer={
          <>
            <button type="button" className="admin-btn" onClick={() => setEditing(null)}>取消</button>
            <button type="button" className="admin-btn primary" onClick={handleSave}>儲存</button>
          </>
        }
      >
        <AdminField id="plan-name" label="方案名稱" required>
          <input id="plan-name" className="admin-input" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </AdminField>
        <div className="admin-field-row">
          <AdminField id="plan-price" label="價格 NT$" required>
            <input id="plan-price" className="admin-input" type="number" value={form.price_ntd || 0} onChange={(e) => setForm({ ...form, price_ntd: Number(e.target.value) })} />
          </AdminField>
          <AdminField id="plan-coin" label="Coin 數" required>
            <input id="plan-coin" className="admin-input" type="number" value={form.coin_amount || 0} onChange={(e) => setForm({ ...form, coin_amount: Number(e.target.value) })} />
          </AdminField>
        </div>
        <AdminField id="plan-badge" label="徽章" hint="選填，顯示在方案卡片右上角">
          <input id="plan-badge" className="admin-input" value={form.badge || ""} onChange={(e) => setForm({ ...form, badge: e.target.value })} />
        </AdminField>
        <AdminField id="plan-desc" label="描述">
          <textarea id="plan-desc" className="admin-input" rows={3} value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </AdminField>
        {(() => {
          const e = planEconomics(form);
          const tone = e.marginPct >= 80 ? "good" : e.marginPct >= 50 ? "warn" : "bad";
          const toneLabel = e.marginPct >= 80 ? "健康" : e.marginPct >= 50 ? "偏低" : "須重新定價";
          return (
            <div className={`admin-plan-econ-preview tone-${tone}`}>
              內部成本 {formatNtd(e.cost)} · 毛利 {formatNtd(e.margin)}（{e.marginPct}%，{toneLabel}） · ≈ {formatNumber(e.pagesEstimate)} 頁
            </div>
          );
        })()}
        <label className="admin-checkbox">
          <input type="checkbox" checked={form.is_active !== false} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用
        </label>
      </AdminModal>
      {dialogHost}
    </div>
  );
}

// ------ AdminAuditLogPage（僅超級管理員） ------

const AUDIT_ACTION_OPTIONS = [
  { v: "", label: "全部動作" },
  { v: "coin_adjust", label: "調整點數" },
  { v: "review_reply", label: "回覆評論" },
  { v: "review_moderate", label: "審核評論" },
  { v: "review_delete", label: "刪除評論" },
  { v: "user_toggle_staff", label: "切換管理員身份" },
  { v: "other", label: "其他" },
];

function AdminAnnouncementsPage() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ title: "", content: "", type: "temporary", active_days: 7, is_active: true });
  const me = useArgusStore((s) => s.me);
  const { confirmDialog, dialogHost } = useConfirmDialogs();

  function loadList() {
    setLoading(true);
    api.get("/admin/announcements/").then((r) => setList(r.data.announcements || [])).finally(() => setLoading(false));
  }
  useEffect(() => {
    if (me?.is_superuser) loadList();
  }, [me]);

  if (!me?.is_superuser) {
    return <div className="admin-error">需要超級管理員權限才能查看。</div>;
  }

  function openNew() {
    setForm({ title: "", content: "", type: "temporary", active_days: 7, is_active: true });
    setEditing("new");
  }
  function openEdit(ann) {
    setForm({ title: ann.title, content: ann.content, type: ann.type, active_days: ann.active_days, is_active: ann.is_active });
    setEditing(ann);
  }
  async function handleSave() {
    if (editing === "new") {
      await api.post("/admin/announcements/", form);
    } else {
      await api.patch(`/admin/announcements/${editing.id}/`, form);
    }
    setEditing(null);
    loadList();
  }
  async function handleDelete(id) {
    if (!(await confirmDialog("確定刪除此公告？", { danger: true }))) return;
    await api.delete(`/admin/announcements/${id}/`);
    loadList();
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">公告管理</h1>
        <button className="admin-btn primary" onClick={openNew}>＋ 新增公告</button>
      </header>

      {loading ? <div className="admin-loading">載入中…</div> : (
        <div className="admin-ann-list">
          {list.map((ann) => (
            <div key={ann.id} className={`admin-ann-card ${ann.is_active ? "" : "inactive"}`}>
              <div className="admin-ann-card-header">
                <span className="admin-ann-title">{ann.title}</span>
                <span className={`admin-ann-type ${ann.type}`}>
                  {ann.type === "permanent" ? "常駐" : `臨時（${ann.active_days}天）`}
                </span>
              </div>
              <p className="admin-ann-preview">{ann.content.slice(0, 80)}…</p>
              <div className="admin-ann-actions">
                <button onClick={() => openEdit(ann)}>編輯</button>
                <button className="danger" onClick={() => handleDelete(ann.id)}>刪除</button>
                <span className={ann.is_active ? "status-active" : "status-inactive"}>
                  {ann.is_active ? "啟用" : "停用"}
                </span>
              </div>
            </div>
          ))}
          {!list.length && <div className="admin-empty">尚無公告</div>}
        </div>
      )}

      <AdminModal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "新增公告" : "編輯公告"}
        size="lg"
        footer={
          <>
            <button type="button" className="admin-btn" onClick={() => setEditing(null)}>取消</button>
            <button type="button" className="admin-btn primary" onClick={handleSave}>儲存</button>
          </>
        }
      >
        <AdminField id="ann-title" label="標題" required>
          <input id="ann-title" className="admin-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </AdminField>
        <AdminField id="ann-content" label="內容" required>
          <textarea id="ann-content" className="admin-input" rows={6} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />
        </AdminField>
        <fieldset className="admin-radio-group">
          <legend className="admin-field-label">公告類型</legend>
          <label><input type="radio" name="type" checked={form.type === "temporary"} onChange={() => setForm({ ...form, type: "temporary" })} /> 臨時公告</label>
          <label><input type="radio" name="type" checked={form.type === "permanent"} onChange={() => setForm({ ...form, type: "permanent" })} /> 常駐公告</label>
        </fieldset>
        {form.type === "temporary" && (
          <AdminField id="ann-days" label="顯示天數" hint="超過天數後自動停止顯示">
            <input id="ann-days" className="admin-input admin-input-narrow" type="number" min={1} max={365} value={form.active_days} onChange={(e) => setForm({ ...form, active_days: Number(e.target.value) })} />
          </AdminField>
        )}
        <label className="admin-checkbox">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用
        </label>
      </AdminModal>
      {dialogHost}
    </div>
  );
}

function AdminAuditLogPage() {
  const me = useArgusStore((s) => s.me);

  if (!me?.is_superuser) {
    return <div className="admin-error">需要超級管理員權限才能查看。</div>;
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <div>
          <h1 className="admin-page-title">操作日誌</h1>
          <p>管理員操作的稽核軌跡（僅超級管理員可見）</p>
        </div>
        <div className="admin-page-head-links">
          <NavLink to="/admin/transactions" className="admin-btn ghost">點數交易 →</NavLink>
          <NavLink to="/admin/scans" className="admin-btn ghost">掃描紀錄 →</NavLink>
        </div>
      </header>

      <div className="admin-panel">
        <AuditLogTab />
      </div>
    </div>
  );
}

function AuditLogTab() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");

  async function load() {
    const r = await api.get("/admin/audit-log/", {
      params: { page, action: action || undefined },
    });
    setData(r.data);
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [page, action]);

  return (
    <>
      <div className="admin-filter-bar">
        <select
          className="admin-input"
          value={action}
          onChange={(e) => { setAction(e.target.value); setPage(1); }}
        >
          {AUDIT_ACTION_OPTIONS.map((o) => (
            <option key={o.v} value={o.v}>{o.label}</option>
          ))}
        </select>
      </div>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <th>時間</th>
                <th>動作</th>
                <th>操作者</th>
                <th>對象</th>
                <th>細節</th>
              </tr>
            </thead>
            <tbody>
              {data.logs.map((log) => (
                <tr key={log.id}>
                  <td>{formatDateTime(log.created_at)}</td>
                  <td><span className="admin-status">{log.action_label}</span></td>
                  <td><strong>{log.actor_username || "(已刪除)"}</strong></td>
                  <td>{log.target_username || "—"}</td>
                  <td className="admin-cell-secondary">
                    {log.target_object_repr}
                    {Object.keys(log.payload || {}).length > 0 && (
                      <details className="admin-log-payload">
                        <summary>payload</summary>
                        <pre>
                          {JSON.stringify(log.payload, null, 2)}
                        </pre>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
              {data.logs.length === 0 && (
                <tr><td colSpan="5" className="admin-empty">尚無紀錄</td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </>
  );
}

// ============================================================
// 首次進站粒子過場動畫（移植自 過場動畫和網站設計範本/index.html）
// 階段：STORM → ASSEMBLE → DISPLAY → EXPLODE → WARP，結束呼叫 onComplete。
// 尊重 prefers-reduced-motion：偏好減少動態時直接略過。
// ============================================================

export {
  RequireAdmin,
  AdminLayout,
  AdminUsersPage,
  AdminUserDetailPage,
  AdminTransactionsPage,
  AdminReviewsPage,
  AdminScansPage,
  AdminScanDetailPage,
  AdminDomainsPage,
  AdminContentPage,
  AdminPlansPage,
  AdminSettingsPage,
  AdminAuditLogPage,
  AdminAnnouncementsPage,
};
