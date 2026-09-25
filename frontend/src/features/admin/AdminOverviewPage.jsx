import { useCallback, useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { api } from "../../api";
import {
  AdminAlertIcon,
  AdminOrdersIcon,
  AdminReviewsIcon,
  AdminScansIcon,
  AdminTokensIcon,
  AdminTransactionsIcon,
  AdminTrendIcon,
  AdminUsersIcon,
} from "../../components/admin/AdminIcons.jsx";
import { AdminMiniChart } from "../../components/admin/AdminMiniChart.jsx";
import { AdminSparkline, AdminStatCard } from "../../components/admin/AdminStatCard.jsx";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates.jsx";
import { STATUS_LABELS, StatusDoneGlyph } from "../../shared/AppShared.jsx";
import { formatDateTime, formatNtd, formatNumber, formatRelative } from "../../shared/formatters.js";

// 後台首頁：待辦中心。
//
// 改建原因（見 2026-09-25 重構規劃 §4-1）：原本的「概覽」是六張總量統計卡 ＋
// 趨勢圖 ＋ 用量分佈，全部是「已經發生的事」，沒有任何元素回答「現在該處理什麼」。
// 待回覆評論與待審檢舉有數字卻點不進去，卡住的掃描則完全看不到。
//
// 現在的資訊順序是：① 待辦 ② 今日脈搏 ③ 趨勢 ④ 成本與明細。
// 每張待辦卡片都是帶著篩選參數的連結，點下去直接落在已篩好的列表。

function TriageCard({ icon, label, count, hint, to, tone, navigate }) {
  const active = count > 0;
  return (
    <button
      type="button"
      className={`admin-triage-card tone-${active ? tone : "idle"}`}
      onClick={() => navigate(to)}
      aria-label={`${label}：${count} 筆，點擊查看`}
    >
      <span className="admin-triage-icon" aria-hidden="true">{icon}</span>
      <span className="admin-triage-count">{formatNumber(count, "0")}</span>
      <span className="admin-triage-label">{label}</span>
      {/* 只有筆數看不出嚴重程度，補上「最久的已等多久」這類脈絡 */}
      <span className="admin-triage-hint">{active ? hint : "沒有待處理"}</span>
    </button>
  );
}

export function AdminOverviewPage() {
  const [data, setData] = useState(null);
  const [dash, setDash] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [overview, dashboard] = await Promise.all([
        api.get("/admin/overview/"),
        api.get("/admin/dashboard/"),
      ]);
      setData(overview.data);
      setDash(dashboard.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "無法載入概覽");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error) {
    return (
      <div className="admin-page">
        <AdminErrorState message="無法載入後台首頁" detail={error} onRetry={load} />
      </div>
    );
  }
  if (loading || !data || !dash) {
    return (
      <div className="admin-page">
        <AdminSkeleton variant="card" rows={4} label="載入待辦中" />
        <AdminSkeleton variant="detail" rows={2} />
      </div>
    );
  }

  const t = data.totals;
  const triage = data.triage || {};
  const providerMaxTokens = Math.max(
    ...(dash.provider_breakdown || []).map((r) => r.tokens), 1,
  );

  const cards = [
    {
      key: "stuck",
      icon: <AdminAlertIcon />,
      label: "排隊逾時",
      count: triage.scans_stuck || 0,
      hint: triage.scans_stuck_oldest_at
        ? `最久一筆已等 ${formatRelative(triage.scans_stuck_oldest_at).replace("前", "")}`
        : `超過 ${triage.scans_stuck_threshold_min} 分鐘未開始`,
      to: "/admin/scans?status=queued",
      tone: "bad",
    },
    {
      key: "failed",
      icon: <AdminScansIcon />,
      label: "今日失敗掃描",
      count: triage.scans_failed_today || 0,
      hint: "點擊查看失敗原因",
      to: "/admin/scans?status=failed",
      tone: "bad",
    },
    {
      key: "reports",
      icon: <AdminAlertIcon />,
      label: "待審檢舉",
      count: triage.reports_pending || 0,
      hint: "使用者檢舉待處理",
      to: "/admin/reviews?filter=reported",
      tone: "warn",
    },
    {
      key: "replies",
      icon: <AdminReviewsIcon />,
      label: "待回覆評論",
      count: triage.reviews_pending || 0,
      hint: "尚無官方回覆",
      to: "/admin/reviews?filter=pending",
      tone: "warn",
    },
  ];
  const allClear = cards.every((card) => card.count === 0);

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <div>
          <h1>待辦中心</h1>
          <p>需要處理的事項，以及系統整體狀態</p>
        </div>
        <button type="button" className="admin-btn ghost" onClick={load}>
          重新整理
        </button>
      </header>

      {/* ---- ① 待辦：第一屏只放「要做的事」 ---- */}
      <section className="admin-triage-grid" aria-label="待處理事項">
        {cards.map((card) => (
          <TriageCard key={card.key} {...card} navigate={navigate} />
        ))}
      </section>

      {allClear && (
        <div className="admin-empty-state tone-good">
          <span className="admin-empty-state-icon" aria-hidden="true"><StatusDoneGlyph /></span>
          <p className="admin-empty-state-title">目前沒有待處理事項</p>
          <p className="admin-empty-state-desc">
            沒有卡住或失敗的掃描，評論也都已回覆與審核完畢。
          </p>
        </div>
      )}

      {/* ---- ② 今日脈搏：正在發生的事 ---- */}
      <section className="admin-panel">
        <div className="admin-panel-head-row">
          <h3><span className="admin-panel-icon-chip"><AdminTrendIcon /></span>今日</h3>
          <NavLink to="/admin/scans" className="admin-panel-more">掃描任務 →</NavLink>
        </div>
        <div className="admin-pulse-row">
          <div className="admin-pulse">
            <div className="admin-pulse-value">{formatNumber(triage.scans_today, "0")}</div>
            <div className="admin-pulse-label">今日掃描</div>
          </div>
          <div className="admin-pulse">
            <div className="admin-pulse-value">{formatNumber(triage.scans_in_progress, "0")}</div>
            <div className="admin-pulse-label">進行中</div>
          </div>
          <div className="admin-pulse">
            <div className="admin-pulse-value">{formatNumber(t.orders_this_month)}</div>
            <div className="admin-pulse-label">本月訂單</div>
          </div>
          <div className="admin-pulse">
            <div className="admin-pulse-value">{formatNumber(t.scans_this_month)}</div>
            <div className="admin-pulse-label">本月掃描</div>
          </div>
        </div>
      </section>

      {/* ---- ③ 趨勢 ---- */}
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

      {/* ---- ④ 總量統計：降到趨勢之後，它們不是每日決策依據 ---- */}
      <div className="admin-stat-grid">
        <AdminStatCard
          label="累計營收"
          value={formatNtd(t.revenue_ntd)}
          hint={`流通 coin ${formatNumber(t.coin_balance_total)}`}
          tone="cyan"
          icon={AdminTransactionsIcon}
          spark={<AdminSparkline series={dash.series} dataKey="revenue_ntd" color="#0ea5e9" />}
        />
        <AdminStatCard
          label="使用者總數"
          value={formatNumber(t.users)}
          hint={`錢包 ${formatNumber(t.wallets)} 個`}
          tone="cyan"
          icon={AdminUsersIcon}
        />
        <AdminStatCard
          label="訂單"
          value={formatNumber(t.orders)}
          hint={`已付 ${formatNumber(t.orders_paid)}`}
          tone="good"
          icon={AdminOrdersIcon}
        />
        <AdminStatCard
          label="AI Token 用量"
          value={formatNumber(t.ai_tokens_total)}
          hint={`本月 ${formatNumber(t.ai_tokens_this_month)}`}
          tone="cyan"
          icon={AdminTokensIcon}
        />
      </div>

      {/* ---- ⑤ 成本與明細 ---- */}
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
                    <span className="admin-provider-tokens">{formatNumber(row.tokens)}</span>
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
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          navigate(`/admin/users/${u.id}`);
                        }
                      }}
                    >
                      <td>
                        <div className="admin-cell-primary">{u.username}</div>
                        <div className="admin-cell-secondary">{u.email}</div>
                      </td>
                      <td className="num"><span className="admin-coin">{formatNumber(u.ai_tokens)}</span></td>
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
          <div className="admin-panel-head-row">
            <h3><span className="admin-panel-icon-chip"><AdminOrdersIcon /></span>最近購買</h3>
            <NavLink to="/admin/orders" className="admin-panel-more">查看訂單 →</NavLink>
          </div>
          {data.recent_purchases.length === 0 ? (
            <p className="admin-empty">尚無購買紀錄</p>
          ) : (
            <div className="admin-table-scroll">
              <table className="admin-table compact">
                <thead><tr><th>時間</th><th>方案</th><th className="num">金額</th></tr></thead>
                <tbody>
                  {data.recent_purchases.map((tx) => (
                    <tr key={tx.id}>
                      <td>{formatDateTime(tx.created_at)}</td>
                      <td>{tx.plan_name || "—"}</td>
                      <td className="num">+{formatNumber(tx.amount)} coin</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="admin-panel">
          <div className="admin-panel-head-row">
            <h3><span className="admin-panel-icon-chip"><AdminScansIcon /></span>最近掃描</h3>
            <NavLink to="/admin/scans" className="admin-panel-more">查看全部 →</NavLink>
          </div>
          {(data.recent_scans || []).length === 0 ? (
            <p className="admin-empty">尚無掃描紀錄</p>
          ) : (
            <div className="admin-table-scroll">
              <table className="admin-table compact">
                <thead><tr><th>時間</th><th>網址</th><th>狀態</th></tr></thead>
                <tbody>
                  {data.recent_scans.map((scan) => (
                    <tr
                      key={scan.id}
                      className="clickable"
                      role="link"
                      tabIndex={0}
                      onClick={() => navigate(`/admin/scans/${scan.id}`)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          navigate(`/admin/scans/${scan.id}`);
                        }
                      }}
                    >
                      <td>{formatDateTime(scan.created_at)}</td>
                      <td className="truncate" title={scan.origin}>{scan.origin}</td>
                      <td>
                        <span className={`admin-status ${scan.status}`}>
                          {STATUS_LABELS[scan.status]?.label || scan.status}
                        </span>
                      </td>
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
