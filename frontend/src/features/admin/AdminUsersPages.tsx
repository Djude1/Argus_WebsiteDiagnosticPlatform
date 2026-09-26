import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";

import {
  adminAdjustCoin,
  adminUserSubscriptionAction,
  fetchAdminSubscriptionPlans,
  fetchAdminUserDetail,
  fetchAdminUsers,
  fetchUserLoginEvents,
  fetchUserSubscription,
} from "../../api";
import { activateAdminRow } from "../../components/admin/activateAdminRow";
import {
  AdminOrdersIcon,
  AdminPlansIcon,
  AdminScansIcon,
  AdminSettingsIcon,
  AdminTokensIcon,
  AdminTransactionsIcon,
  AdminUsersIcon,
} from "../../components/admin/AdminIcons.jsx";
import { AdminPagination } from "../../components/admin/AdminPagination";
import { AdminSortableTh } from "../../components/admin/AdminSortableTh";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { useConfirmDialogs } from "../../shared/AppShared.jsx";
import type {
  AdminLoginEvent,
  AdminSubscriptionPlan,
  AdminUserDetailResponse,
  AdminUserListParams,
  AdminUserListResponse,
  AdminUserSubscription,
} from "../../shared/apiContracts";
import { formatDateTime, formatNtd, formatNumber } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery";
import { errorDetail, statusLabel, toAllowed, toPositiveInt } from "./adminHelpers";

// 後台使用者列表與使用者詳情。
//
// 從 AdminPages.jsx 拆出並轉成 TypeScript。使用者詳情一次串五個端點（詳情、
// 調整點數、登入事件、訂閱現況／開通／取消、方案清單），是後台欄位最多、
// 最容易接錯的頁面；五個端點的回傳現在都由產生的型別描述，並由後端
// AdminResponseMatchesSchemaTests 確認實際回傳與型別一致。

type UserOrdering = NonNullable<AdminUserListParams["ordering"]>;

const USER_ORDERINGS = [
  "date_joined", "-date_joined",
  "last_login", "-last_login",
  "username", "-username",
  "balance", "-balance",
  "total_purchased_ntd", "-total_purchased_ntd",
  "total_scans_used", "-total_scans_used",
] as const satisfies readonly UserOrdering[];

const USERS_QUERY_DEFAULTS = { page: 1, q: "", ordering: "-date_joined" };

export function AdminUsersPage() {
  const navigate = useNavigate();
  const { params, setParam, setParams, resetFilters, hasFilters } = useListQuery(USERS_QUERY_DEFAULTS);
  const { page, q, ordering } = params;
  const [data, setData] = useState<AdminUserListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchDraft, setSearchDraft] = useState(q);

  useEffect(() => { setSearchDraft(q); }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAdminUsers({
        q: q || undefined,
        page,
        ordering: toAllowed(ordering, USER_ORDERINGS),
      }));
    } catch (err) {
      setError(errorDetail(err, "無法載入使用者"));
    } finally {
      setLoading(false);
    }
  }, [q, page, ordering]);

  useEffect(() => { load(); }, [load]);

  function handleSearchSubmit(e: FormEvent) {
    e.preventDefault();
    // 只改網址，由 load 的 useCallback 依賴觸發重載；
    // 原本 setPage(1) + load() 會因 page 閉包是舊值而連送兩次請求
    setParams({ q: searchDraft.trim() });
  }

  const setOrdering = (o: string) => setParam("ordering", o);

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
                <AdminSortableTh field="username" ordering={ordering} onChange={setOrdering}>使用者</AdminSortableTh>
                <th>email</th>
                <AdminSortableTh field="balance" ordering={ordering} onChange={setOrdering} numeric>餘額</AdminSortableTh>
                <AdminSortableTh field="total_purchased_ntd" ordering={ordering} onChange={setOrdering} numeric>累積購買</AdminSortableTh>
                <AdminSortableTh field="total_scans_used" ordering={ordering} onChange={setOrdering} numeric>掃描數</AdminSortableTh>
                <AdminSortableTh field="last_login" ordering={ordering} onChange={setOrdering}>最近登入</AdminSortableTh>
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
                <tr><td colSpan={6} className="admin-empty">
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

type Feedback = { tone: "good" | "bad"; message: string };

export function AdminUserDetailPage() {
  const { userId: userIdParam = "" } = useParams();
  const userId = toPositiveInt(userIdParam);
  const navigate = useNavigate();
  const [user, setUser] = useState<AdminUserDetailResponse | null>(null);
  const [error, setError] = useState("");
  const [delta, setDelta] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  // 登入記錄（最近 50 筆；null = 載入中）
  const [loginEvents, setLoginEvents] = useState<AdminLoginEvent[] | null>(null);
  // 訂閱管理：進入頁面載入現況（GET），開通／取消動作後以回應即時更新
  const [subscription, setSubscription] = useState<AdminUserSubscription | null>(null);
  const [plans, setPlans] = useState<AdminSubscriptionPlan[]>([]);
  const [subPlanCode, setSubPlanCode] = useState("");
  const [subPeriods, setSubPeriods] = useState(1);
  const [subBusy, setSubBusy] = useState(false);
  const [subFeedback, setSubFeedback] = useState<Feedback | null>(null);
  const { confirmDialog, dialogHost } = useConfirmDialogs();

  const load = useCallback(async () => {
    if (!userId) {
      setError("找不到此使用者");
      return;
    }
    try {
      setUser(await fetchAdminUserDetail(userId));
    } catch {
      setError("找不到此使用者");
    }
  }, [userId]);
  useEffect(() => { load(); }, [load]);

  // 登入事件、訂閱方案清單與訂閱現況隨使用者切換載入（失敗不擋頁面）；
  // 各狀態也一併重置，避免切到別位使用者時殘留上一位的資料
  useEffect(() => {
    setLoginEvents(null);
    setSubscription(null);
    setSubFeedback(null);
    if (!userId) return;
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

  async function handleGrantSubscription(e: FormEvent) {
    e.preventDefault();
    if (!userId) return;
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
        message: `已開通 ${data.subscription?.plan_name}（${data.subscription?.periods_remaining} 期），並立即結算本月贈點。`,
      });
      await load();
    } catch (err) {
      setSubFeedback({ tone: "bad", message: errorDetail(err, "開通失敗，請確認方案與期數。") });
    } finally {
      setSubBusy(false);
    }
  }

  async function handleCancelSubscription() {
    if (!userId) return;
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
      setSubFeedback({ tone: "bad", message: errorDetail(err, "取消失敗。") });
    } finally {
      setSubBusy(false);
    }
  }

  async function handleAdjust(e: FormEvent) {
    e.preventDefault();
    if (!userId) return;
    const value = parseInt(delta, 10);
    if (!value) {
      setFeedback({ tone: "bad", message: "請輸入非 0 的整數" });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const result = await adminAdjustCoin(userId, value, note || "管理員手動調整");
      setFeedback({
        tone: "good",
        message: `已${value > 0 ? "補" : "扣"} ${Math.abs(result.transaction.amount)} coin，當前餘額 ${result.wallet_balance}`,
      });
      setDelta("");
      setNote("");
      await load();
    } catch (err) {
      setFeedback({ tone: "bad", message: errorDetail(err, "調整失敗") });
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
                <dt>最近月贈點</dt><dd>{w.last_bonus_year ? `${w.last_bonus_year}-${String(w.last_bonus_month).padStart(2, "0")}` : "—"}</dd>
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
              aria-label="變動金額"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
            />
            <input
              className="admin-input wide"
              placeholder="備註（將寫入交易紀錄）"
              aria-label="備註"
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
        {user.recent_scans.length === 0 ? (
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
                        {statusLabel(scan.status)}
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
              <tr><td colSpan={5} className="admin-empty">尚無交易紀錄</td></tr>
            )}
          </tbody>
          </table>
        </div>
      </section>
      {dialogHost}
    </div>
  );
}
