import { useEffect, useMemo, useRef, useState } from "react";
import {
  Navigate,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import brandLogo from "../../assets/brand-logo.webp";
import { STATUS_LABELS, StatusDoneGlyph, useConfirmDialogs, useDialogFocus } from "../../shared/AppShared.jsx";
import {
  AdminOverviewIcon,
  AdminUsersIcon,
  AdminScansIcon,
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

const ADMIN_NAV_ITEMS = [
  { to: "/admin/overview", label: "概覽", Icon: AdminOverviewIcon },
  { to: "/admin/users", label: "使用者", Icon: AdminUsersIcon },
  { to: "/admin/scans", label: "掃描", Icon: AdminScansIcon },
  { to: "/admin/transactions", label: "交易", Icon: AdminTransactionsIcon },
  { to: "/admin/plans", label: "方案", Icon: AdminPlansIcon },
  { to: "/admin/content", label: "內容", Icon: AdminContentIcon },
  { to: "/admin/reviews", label: "評論", Icon: AdminReviewsIcon },
  { to: "/admin/settings", label: "設定", Icon: AdminSettingsIcon },
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
  const { setToken, me, replayIntro } = useArgusStore();
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
  // 超級管理員額外看到「操作日誌」分頁
  const navItems = me?.is_superuser
    ? [...ADMIN_NAV_ITEMS, { to: "/admin/audit-log", label: "操作日誌", Icon: AdminAuditLogIcon }, { to: "/admin/announcements", label: "公告管理", Icon: AdminAnnouncementsIcon }]
    : ADMIN_NAV_ITEMS;
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
          {navItems.map((item) => (
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
        </nav>
        <div className="admin-sidebar-footer">
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

function AdminStatCard({ label, value, hint, tone = "cyan", icon: Icon, hero = false, spark }) {
  return (
    <div className={`admin-stat-card tone-${tone}${hero ? " hero" : ""}`}>
      <div className="admin-stat-head">
        <div className="admin-stat-label">{label}</div>
        {Icon && (
          <span className="admin-stat-icon-chip">
            <Icon />
          </span>
        )}
      </div>
      <div className="admin-stat-value">{value}</div>
      {hint && <div className="admin-stat-hint">{hint}</div>}
      {spark && <div className="admin-stat-spark">{spark}</div>}
    </div>
  );
}

function AdminSparkline({ series, dataKey, color = "#0ea5e9", height = 40 }) {
  if (!series || series.length < 2) return null;
  const w = 240;
  const values = series.map((row) => row[dataKey] || 0);
  const maxV = Math.max(...values, 1);
  const minV = Math.min(...values, 0);
  const range = maxV - minV || 1;
  const step = w / (series.length - 1);
  const yFor = (v) => height - ((v - minV) / range) * height;
  const linePoints = values.map((v, i) => `${i * step},${yFor(v)}`).join(" ");
  const areaPoints = `0,${height} ${linePoints} ${w},${height}`;
  const gradId = `admin-spark-${dataKey}`;
  return (
    <svg className="admin-stat-spark-svg" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#${gradId})`} stroke="none" />
      <polyline points={linePoints} fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AdminMiniChart({ series, keys, height = 110 }) {
  // series: [{date, ...values}]；keys: [{key, label, color}]
  if (!series || series.length === 0) {
    return <div className="admin-empty">尚無資料</div>;
  }
  const w = 480;
  const padding = { top: 8, right: 8, bottom: 24, left: 36 };
  const plotW = w - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const allValues = series.flatMap((row) => keys.map((k) => row[k.key] || 0));
  const maxV = Math.max(...allValues, 1);
  const step = series.length > 1 ? plotW / (series.length - 1) : 0;
  const yFor = (v) => padding.top + plotH - (v / maxV) * plotH;
  const xFor = (i) => padding.left + i * step;
  const yTicks = [0, Math.round(maxV / 2), maxV];

  return (
    <svg className="admin-mini-chart" viewBox={`0 0 ${w} ${height}`} width="100%" height={height}>
      <defs>
        {keys.map((k) => (
          <linearGradient key={k.key} id={`admin-chart-fill-${k.key}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={k.color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={k.color} stopOpacity="0" />
          </linearGradient>
        ))}
      </defs>
      {yTicks.map((t) => (
        <g key={t}>
          <line
            x1={padding.left}
            x2={w - padding.right}
            y1={yFor(t)}
            y2={yFor(t)}
            stroke="#e2e8f0"
            strokeDasharray="2 4"
          />
          <text x={padding.left - 6} y={yFor(t) + 3} fontSize="10" fill="#94a3b8" textAnchor="end">
            {t.toLocaleString()}
          </text>
        </g>
      ))}
      {keys.map((k) => {
        const points = series.map((row, i) => [xFor(i), yFor(row[k.key] || 0)]);
        const linePoints = points.map(([x, y]) => `${x},${y}`).join(" ");
        const areaPoints = [
          `${points[0][0]},${padding.top + plotH}`,
          ...points.map(([x, y]) => `${x},${y}`),
          `${points[points.length - 1][0]},${padding.top + plotH}`,
        ].join(" ");
        const [lastX, lastY] = points[points.length - 1];
        return (
          <g key={k.key}>
            <polygon points={areaPoints} fill={`url(#admin-chart-fill-${k.key})`} stroke="none" />
            <polyline
              points={linePoints}
              fill="none"
              stroke={k.color}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <circle
              className="admin-mini-chart-dot"
              cx={lastX}
              cy={lastY}
              r="3.5"
              fill={k.color}
            />
          </g>
        );
      })}
      {series.length > 0 && (
        <>
          <text x={xFor(0)} y={height - 4} fontSize="10" fill="#94a3b8" textAnchor="start">
            {series[0].date.slice(5)}
          </text>
          <text x={xFor(series.length - 1)} y={height - 4} fontSize="10" fill="#94a3b8" textAnchor="end">
            {series[series.length - 1].date.slice(5)}
          </text>
        </>
      )}
    </svg>
  );
}

function AdminOverviewPage() {
  const [data, setData] = useState(null);
  const [dash, setDash] = useState(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([api.get("/admin/overview/"), api.get("/admin/dashboard/")])
      .then(([o, d]) => { setData(o.data); setDash(d.data); })
      .catch(() => setError("無法載入概覽。"));
  }, []);

  if (error) return <div className="admin-error">{error}</div>;
  if (!data || !dash) return <div className="admin-loading">載入中…</div>;
  const t = data.totals;
  const providerMaxTokens = Math.max(
    ...(dash.provider_breakdown || []).map((r) => r.tokens), 1,
  );

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <div>
          <h1>概覽</h1>
          <p>系統整體狀態與最近 14 天活動</p>
        </div>
        <div className="admin-status-badge">
          <span className="admin-status-dot" aria-hidden="true" />
          Argus 即時監控中
        </div>
      </header>

      <div className="admin-stat-grid admin-stat-grid--bento">
        <AdminStatCard
          label="累計營收"
          value={`NT$ ${t.revenue_ntd.toLocaleString()}`}
          hint={`流通 coin ${t.coin_balance_total.toLocaleString()}`}
          tone="cyan"
          icon={AdminTransactionsIcon}
          hero
          spark={<AdminSparkline series={dash.series} dataKey="revenue_ntd" color="#0ea5e9" />}
        />
        <AdminStatCard
          label="使用者總數"
          value={t.users.toLocaleString()}
          hint={`錢包 ${t.wallets.toLocaleString()} 個`}
          tone="cyan"
          icon={AdminUsersIcon}
        />
        <AdminStatCard
          label="訂單"
          value={t.orders.toLocaleString()}
          hint={`本月 ${t.orders_this_month} / 已付 ${t.orders_paid}`}
          tone="good"
          icon={AdminOrdersIcon}
        />
        <AdminStatCard
          label="掃描總數"
          value={t.scans.toLocaleString()}
          hint={`本月 ${t.scans_this_month.toLocaleString()}`}
          tone="cyan"
          icon={AdminScansIcon}
        />
        <AdminStatCard
          label="AI Token 用量"
          value={t.ai_tokens_total.toLocaleString()}
          hint={`本月 ${t.ai_tokens_this_month.toLocaleString()} / Sessions ${t.ai_sessions_total}`}
          tone="cyan"
          icon={AdminTokensIcon}
        />
        <AdminStatCard
          label="評論"
          value={<>{t.avg_rating ?? "—"} <AdminStarIcon className="admin-star-icon" /></>}
          hint={`共 ${t.reviews} 則 / 待回覆 ${t.reviews_pending}`}
          tone={t.reviews_pending > 0 ? "warn" : "good"}
          icon={AdminReviewsIcon}
        />
      </div>

      {/* 14 天時序圖：3 條線（訂單、AI tokens、掃描） */}
      <section className="admin-panel">
        <div className="admin-panel-head-row">
          <h3><span className="admin-panel-icon-chip"><AdminTrendIcon /></span>最近 14 天活動</h3>
          <div className="admin-chart-legend">
            <span><i className="tone-cyan" />AI tokens</span>
            <span><i className="tone-good" />訂單金額</span>
            <span><i className="tone-amber" />掃描數</span>
          </div>
        </div>
        <AdminMiniChart
          series={dash.series}
          keys={[
            { key: "ai_tokens", color: "#0ea5e9" },
            { key: "revenue_ntd", color: "#10b981" },
            { key: "scans", color: "#f59e0b" },
          ]}
          height={140}
        />
      </section>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminTokensIcon /></span>AI Provider 用量分佈</h3>
          {dash.provider_breakdown.length === 0 ? (
            <p className="admin-empty">尚無 AI 使用紀錄</p>
          ) : (
            <div className="admin-provider-bars">
              {dash.provider_breakdown.map((row) => (
                <div className="admin-provider-row" key={`${row.provider}-${row.model}`}>
                  <div className="admin-provider-meta">
                    <span className="admin-provider-name">{row.provider}</span>
                    <span className="admin-provider-model">{row.model || "—"}</span>
                  </div>
                  <div className="admin-provider-track">
                    <div
                      className="admin-provider-fill"
                      style={{ width: `${(row.tokens / providerMaxTokens) * 100}%` }}
                    />
                  </div>
                  <div className="admin-provider-stats">
                    <span className="admin-provider-tokens">{row.tokens.toLocaleString()}</span>
                    <span className="admin-provider-sessions">{row.sessions} sess</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminUsersIcon /></span>Top 10 AI 用戶</h3>
          {dash.top_ai_users.length === 0 ? (
            <p className="admin-empty">尚無 AI 使用紀錄</p>
          ) : (
            <div className="admin-table-scroll">
              <table className="admin-table compact">
              <thead><tr><th>使用者</th><th className="num">tokens</th><th className="num">sessions</th></tr></thead>
              <tbody>
                {dash.top_ai_users.map((u) => (
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
                      <div className="admin-cell-primary">{u.username}</div>
                      <div className="admin-cell-secondary">{u.email}</div>
                    </td>
                    <td className="num"><span className="admin-coin">{u.ai_tokens.toLocaleString()}</span></td>
                    <td className="num">{u.ai_sessions}</td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminOrdersIcon /></span>最近購買</h3>
          {data.recent_purchases.length === 0 ? (
            <p className="admin-empty">尚無購買紀錄</p>
          ) : (
            <div className="admin-table-scroll">
              <table className="admin-table compact">
              <thead><tr><th>時間</th><th>方案</th><th className="num">金額</th></tr></thead>
              <tbody>
                {data.recent_purchases.map((tx) => (
                  <tr key={tx.id}>
                    <td>{new Date(tx.created_at).toLocaleString("zh-Hant")}</td>
                    <td>{tx.plan_name || "—"}</td>
                    <td className="num">+{tx.amount} coin</td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function AdminPagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null;
  return (
    <div className="admin-pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >← 上一頁</button>
      <span>{page} / {totalPages}</span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >下一頁 →</button>
    </div>
  );
}

function AdminUsersPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  async function load() {
    const response = await api.get("/admin/users/", {
      params: { q: search, page },
    });
    setData(response.data);
  }

  useEffect(() => { load(); /* eslint-disable-line */ }, [page]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    setPage(1);
    load();
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
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button className="admin-btn" type="submit">搜尋</button>
      </form>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <th>使用者</th>
                <th>email</th>
                <th className="num">餘額</th>
                <th className="num">累積購買</th>
                <th className="num">掃描數</th>
                <th>最近登入</th>
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
                  <td className="num"><span className="admin-coin">{u.balance.toLocaleString()}</span></td>
                  <td className="num">{u.total_purchased_ntd > 0 ? `NT$ ${u.total_purchased_ntd.toLocaleString()}` : "—"}</td>
                  <td className="num">{u.total_scans_used}</td>
                  <td>{u.last_login ? new Date(u.last_login).toLocaleString("zh-Hant") : "從未"}</td>
                </tr>
              ))}
              {data.users.length === 0 && (
                <tr><td colSpan="6" className="admin-empty">沒有符合的使用者</td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
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

  async function load() {
    try {
      const response = await api.get(`/admin/users/${userId}/`);
      setUser(response.data);
    } catch {
      setError("找不到此使用者");
    }
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [userId]);

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
            <dt>註冊時間</dt><dd>{new Date(user.date_joined).toLocaleString("zh-Hant")}</dd>
            <dt>最後登入</dt><dd>{user.last_login ? new Date(user.last_login).toLocaleString("zh-Hant") : "從未"}</dd>
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
                <td>{new Date(tx.created_at).toLocaleString("zh-Hant")}</td>
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
    </div>
  );
}

function AdminTransactionsPage({ embedded }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState("");

  async function load() {
    const response = await api.get("/admin/transactions/", {
      params: { page, kind: kind || undefined },
    });
    setData(response.data);
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [page, kind]);

  const KIND_OPTIONS = [
    { v: "", label: "全部類型" },
    { v: "monthly_bonus", label: "每月贈點" },
    { v: "purchase", label: "購買" },
    { v: "scan_hold", label: "掃描預扣" },
    { v: "scan_refund", label: "掃描退款" },
    { v: "admin_adjust", label: "管理員調整" },
  ];

  const content = (
    <>
      {!embedded && (
        <header className="admin-page-head">
          <h1>交易紀錄</h1>
          <p>所有 coin 異動的審計紀錄</p>
        </header>
      )}

      <div className="admin-filter-bar">
        <select
          className="admin-input"
          value={kind}
          onChange={(e) => { setKind(e.target.value); setPage(1); }}
        >
          {KIND_OPTIONS.map((o) => (
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
                <th>時間</th><th>使用者</th><th>類型</th>
                <th className="num">變動</th><th className="num">餘額</th>
                <th>來源</th><th>備註</th>
              </tr>
            </thead>
            <tbody>
              {data.transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{new Date(tx.created_at).toLocaleString("zh-Hant")}</td>
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
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </>
  );

  if (embedded) return content;
  return <div className="admin-page">{content}</div>;
}

function AdminReviewsPage() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("all");
  const [draftReplies, setDraftReplies] = useState({});
  const [busyId, setBusyId] = useState(null);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  async function load() {
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
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [page, filter]);

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
            onChange={(event) => { setFilter(event.target.value); setPage(1); }}
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
                {new Date(review.created_at).toLocaleString("zh-Hant")}
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
              <StatusDoneGlyph className="admin-inline-glyph" /> 官方回覆最後更新於 {new Date(review.response.updated_at).toLocaleString("zh-Hant")}
              {review.response.author_username ? ` · ${review.response.author_username}` : ""}
            </div>
          )}
        </article>
      ))}
      {data && data.reviews.length === 0 && (
        <div className="admin-empty admin-panel">沒有符合條件的評論</div>
      )}
      {data && <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />}
      {dialogHost}
    </div>
  );
}
function AdminScansPage({ embedded }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  async function load() {
    const response = await api.get("/admin/scans/", {
      params: { q: search, status: statusFilter || undefined, page },
    });
    setData(response.data);
  }
  useEffect(() => { load(); /* eslint-disable-line */ }, [page, statusFilter]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    setPage(1);
    load();
  }

  const content = (
    <>
      {!embedded && (
        <header className="admin-page-head">
          <h1>掃描</h1>
          <p>所有使用者的掃描任務</p>
        </header>
      )}

      <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
        <input
          className="admin-input"
          placeholder="搜尋網址或使用者"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="admin-input"
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
        >
          <option value="">全部狀態</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
        <button className="admin-btn" type="submit">搜尋</button>
      </form>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <th>時間</th><th>使用者</th><th>網址</th>
                <th>狀態</th><th>模式</th>
                <th className="num">分數</th><th className="num">頁數</th><th className="num">問題</th>
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
                  <td>{new Date(s.created_at).toLocaleString("zh-Hant")}</td>
                  <td>{s.username}</td>
                  <td className="truncate" title={s.origin}>{s.origin}</td>
                  <td><span className={`admin-status ${s.status}`}>{STATUS_LABELS[s.status]?.label || s.status}</span></td>
                  <td>{s.scan_mode === "active" ? "主動" : "被動"}</td>
                  <td className="num">{s.overall_score ?? "—"}</td>
                  <td className="num">{s.pages_count}</td>
                  <td className="num">{s.findings_count}</td>
                  <td className="num">{s.duration_sec ? `${s.duration_sec}s` : "—"}</td>
                </tr>
              ))}
              {data.scans.length === 0 && (
                <tr><td colSpan="9" className="admin-empty">沒有符合的掃描</td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </>
  );

  if (embedded) return content;
  return <div className="admin-page">{content}</div>;
}

function AdminScanDetailPage() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/admin/scans/${scanId}/`)
      .then((r) => setData(r.data))
      .catch(() => setError("找不到此掃描"));
  }, [scanId]);

  if (error) return <div className="admin-error">{error}</div>;
  if (!data) return <div className="admin-loading">載入中…</div>;
  const s = data.scan;

  return (
    <div className="admin-page">
      <button type="button" className="admin-back-link" onClick={() => navigate("/admin/scans")}>← 回掃描列表</button>
      <header className="admin-page-head">
        <h1>掃描 #{s.id}</h1>
        <p>{s.origin} · {s.username}</p>
      </header>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminScansIcon /></span>狀態</h3>
          <dl className="admin-dl">
            <dt>狀態</dt><dd><span className={`admin-status ${s.status}`}>{STATUS_LABELS[s.status]?.label || s.status}</span></dd>
            <dt>模式</dt><dd>{s.scan_mode === "active" ? "主動測試" : "被動偵測"}</dd>
            <dt>建立時間</dt><dd>{new Date(s.created_at).toLocaleString("zh-Hant")}</dd>
            <dt>完成時間</dt><dd>{s.completed_at ? new Date(s.completed_at).toLocaleString("zh-Hant") : "—"}</dd>
            <dt>耗時</dt><dd>{s.duration_sec ? `${s.duration_sec} 秒` : "—"}</dd>
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
      </div>
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
  const dialogRef = useDialogFocus(Boolean(editing), cancel);
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
      {editing && (
        <div className="admin-modal-backdrop" onClick={cancel}>
          <form
            ref={dialogRef}
            className="admin-modal"
            role="dialog"
            aria-modal="true"
            aria-label={editing === "new" ? `新增${schema.title}` : `編輯${schema.title}`}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            onSubmit={save}
          >
            <div className="admin-modal-head">
              <h4>{editing === "new" ? `新增${schema.title}` : `編輯 #${editing.id}`}</h4>
              <button type="button" className="admin-modal-close" onClick={cancel}>×</button>
            </div>
            <div className="admin-modal-body">
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
            </div>
            <div className="admin-modal-foot">
              <button type="button" className="admin-btn" onClick={cancel}>取消</button>
              <button type="submit" className="admin-btn primary" disabled={busy}>
                {busy ? "儲存中…" : "儲存"}
              </button>
            </div>
          </form>
        </div>
      )}
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
    { key: "student_id", label: "學號", type: "text", hint: "例：11246034" },
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
    { key: "student_id", label: "學號" },
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
  // pages = coin（每頁 10 coin 是 settings 的 ARGUS_COIN_PER_PAGE）
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
        <h1>系統設定（唯讀）</h1>
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
  const dialogRef = useDialogFocus(Boolean(editing), () => setEditing(null));
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
        <button className="admin-add-btn" onClick={openNew}>＋ 新增方案</button>
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

      {editing && (
        <div className="ann-backdrop" onClick={() => setEditing(null)}>
          <div
            ref={dialogRef}
            className="ann-modal sm"
            role="dialog"
            aria-modal="true"
            aria-label={editing === "new" ? "新增方案" : "編輯方案"}
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="ann-modal-header">
              <h2 className="ann-modal-title">{editing === "new" ? "新增方案" : "編輯方案"}</h2>
            </header>
            <div className="ann-modal-body">
              <input className="input" placeholder="名稱" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <div className="ann-form-row">
                <input className="input" type="number" placeholder="價格 NT$" value={form.price_ntd || 0} onChange={(e) => setForm({ ...form, price_ntd: Number(e.target.value) })} />
                <input className="input" type="number" placeholder="Coin 數" value={form.coin_amount || 0} onChange={(e) => setForm({ ...form, coin_amount: Number(e.target.value) })} />
              </div>
              <input className="input" placeholder="徽章（選填）" value={form.badge || ""} onChange={(e) => setForm({ ...form, badge: e.target.value })} />
              <textarea className="input" rows={3} placeholder="描述" value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              {(() => {
                const e = planEconomics(form);
                const tone = e.marginPct >= 80 ? "good" : e.marginPct >= 50 ? "warn" : "bad";
                return (
                  <div className={`admin-plan-econ-preview tone-${tone}`}>
                    內部成本 NT$ {e.cost} · 毛利 NT$ {e.margin}（{e.marginPct}%） · ≈ {e.pagesEstimate} 頁
                  </div>
                );
              })()}
              <label><input type="checkbox" checked={form.is_active !== false} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用</label>
            </div>
            <footer className="ann-modal-footer">
              <button type="button" className="ann-btn-dismiss" onClick={() => setEditing(null)}>取消</button>
              <button type="button" className="ann-btn-confirm" onClick={handleSave}>儲存</button>
            </footer>
          </div>
        </div>
      )}
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
  const dialogRef = useDialogFocus(Boolean(editing), () => setEditing(null));
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
        <button className="admin-add-btn" onClick={openNew}>＋ 新增公告</button>
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

      {editing && (
        <div className="ann-backdrop" onClick={() => setEditing(null)}>
          <div
            ref={dialogRef}
            className="ann-modal lg"
            role="dialog"
            aria-modal="true"
            aria-label={editing === "new" ? "新增公告" : "編輯公告"}
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="ann-modal-header">
              <h2 className="ann-modal-title">{editing === "new" ? "新增公告" : "編輯公告"}</h2>
            </header>
            <div className="ann-modal-body">
              <input className="input" placeholder="標題" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <textarea className="input" rows={6} placeholder="內容" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />
              <div className="ann-form-radio-group">
                <label><input type="radio" name="type" checked={form.type === "temporary"} onChange={() => setForm({ ...form, type: "temporary" })} /> 臨時公告</label>
                <label><input type="radio" name="type" checked={form.type === "permanent"} onChange={() => setForm({ ...form, type: "permanent" })} /> 常駐公告</label>
              </div>
              {form.type === "temporary" && (
                <label>顯示天數：<input className="input ann-input-days" type="number" min={1} max={365} value={form.active_days} onChange={(e) => setForm({ ...form, active_days: Number(e.target.value) })} /></label>
              )}
              <label><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用</label>
            </div>
            <footer className="ann-modal-footer">
              <button type="button" className="ann-btn-dismiss" onClick={() => setEditing(null)}>取消</button>
              <button type="button" className="ann-btn-confirm" onClick={handleSave}>儲存</button>
            </footer>
          </div>
        </div>
      )}
      {dialogHost}
    </div>
  );
}

function AdminAuditLogPage() {
  const [tab, setTab] = useState("audit");
  const me = useArgusStore((s) => s.me);

  if (!me?.is_superuser) {
    return <div className="admin-error">需要超級管理員權限才能查看。</div>;
  }

  const TABS = [
    { key: "audit", label: "操作紀錄" },
    { key: "transactions", label: "交易紀錄" },
    { key: "scans", label: "掃描紀錄" },
  ];

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">操作日誌</h1>
        <p>操作/交易/掃描紀錄（僅超級管理員可見）</p>
      </header>

      <div className="admin-sub-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`admin-sub-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="admin-panel">
        {tab === "audit" && <AuditLogTab />}
        {tab === "transactions" && <AdminTransactionsPage embedded />}
        {tab === "scans" && <AdminScansPage embedded />}
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
                  <td>{new Date(log.created_at).toLocaleString("zh-Hant")}</td>
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
  AdminOverviewPage,
  AdminUsersPage,
  AdminUserDetailPage,
  AdminTransactionsPage,
  AdminReviewsPage,
  AdminScansPage,
  AdminScanDetailPage,
  AdminContentPage,
  AdminPlansPage,
  AdminSettingsPage,
  AdminAuditLogPage,
  AdminAnnouncementsPage,
};
