import { useEffect, useRef, useState } from "react";
import {
  Navigate,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import brandLogo from "../../assets/brand-logo.webp";
import { StatusDoneGlyph, useConfirmDialogs } from "../../shared/AppShared.jsx";
import { AdminModal } from "../../components/admin/AdminModal";
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
  AdminOrdersIcon,
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

// ============================================================
// 首次進站粒子過場動畫（移植自 過場動畫和網站設計範本/index.html）
// 階段：STORM → ASSEMBLE → DISPLAY → EXPLODE → WARP，結束呼叫 onComplete。
// 尊重 prefers-reduced-motion：偏好減少動態時直接略過。
// ============================================================

export {
  RequireAdmin,
  AdminLayout,
  AdminContentPage,
  AdminSettingsPage,
};
