import { useCallback, useEffect, useState } from "react";

import { api } from "../../api";
import { AdminAlertIcon } from "../../components/admin/AdminIcons.jsx";
import { AdminScanChain } from "../../components/admin/AdminScanChain.jsx";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { AdminClusterNodes, formatBytes } from "../../components/admin/AdminClusterNodes.jsx";
import { AdminWorkloads } from "../../components/admin/AdminWorkloads.jsx";
import { formatDateTime } from "../../shared/formatters.js";

// 系統健康：把 docs/environment-preflight.md 的人工檢查變成畫面。
//
// 區塊（2026-10-19 改為 Kubernetes 叢集視角）：
//   1. 掃描鏈路圖——看「斷在哪一段」，而不只是「哪一項壞了」
//   2. 叢集節點——1 master + N worker 各一張卡：Ready、壓力、CPU／記憶體（有 metrics-server 用實際用量，
//      否則用 requests 佔比並明講）
//   3. Argus 工作負載——各元件的 pod 數、就緒數、落在哪個節點、重啟次數
//   4. 檢查明細——每項判定依據
//   原本量「回應這個請求的 web pod 容器」的四張資源卡縮成頁尾一行附註；本機不在叢集內時
//   叢集區塊顯示原因而不是空白。
//
// 設計原則是「綠燈要可信」：每項檢查都顯示判定依據，樣本不足時顯示
// 「無法判定」而非綠燈。沒有資料不等於沒有問題。
//
// 這是即時探測，不是歷史監控。它回答「現在通不通」，不回答「過去壞過幾次」。

const TONE_LABEL = { ok: "正常", warn: "注意", bad: "異常", unknown: "無法判定" };
const TONE_SYMBOL = { ok: "✓", warn: "!", bad: "✕", unknown: "?" };
const AUTO_REFRESH_MS = 15000;

function formatUptime(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d} 天 ${h} 小時`;
  if (h > 0) return `${h} 小時 ${m} 分`;
  return `${m} 分`;
}

function HealthRow({ check }) {
  return (
    <li className={`admin-health-row tone-${check.status}`}>
      <span className="admin-health-badge" aria-hidden="true">
        {TONE_SYMBOL[check.status]}
      </span>
      <div className="admin-health-body">
        <div className="admin-health-label">
          {check.label}
          <span className="admin-health-state">{TONE_LABEL[check.status]}</span>
        </div>
        <div className="admin-health-detail">{check.detail}</div>
        <div className="admin-health-basis">依據：{check.basis}</div>
        {check.extra?.workers?.length > 0 && (
          <div className="admin-health-basis">
            worker：{check.extra.workers.join("、")}
          </div>
        )}
      </div>
    </li>
  );
}

export function AdminHealthPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [auto, setAuto] = useState(true);
  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/health/");
      const next = response.data;
      setData(next);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "無法取得健康狀態");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // 自動更新：探測本身約 2 秒，15 秒一次是「有即時感」與「不增加無謂負載」的折衷
  useEffect(() => {
    if (!auto) return undefined;
    const timer = setInterval(() => load({ silent: true }), AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [auto, load]);

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <div>
          <h1>系統健康</h1>
          <p>掃描鏈路、Kubernetes 節點與 Argus 工作負載的即時探測；這是「現在通不通」，不是歷史監控</p>
        </div>
        <div className="admin-page-head-links">
          <label className="admin-auto-toggle">
            <input
              type="checkbox"
              checked={auto}
              onChange={(event) => setAuto(event.target.checked)}
            />
            每 15 秒自動更新
          </label>
          <button type="button" className="admin-btn" onClick={() => load()} disabled={loading}>
            {loading ? "檢查中…" : "重新檢查"}
          </button>
        </div>
      </header>

      {error && <AdminErrorState message="無法取得健康狀態" detail={error} onRetry={load} />}
      {!error && loading && !data && <AdminSkeleton variant="detail" rows={2} label="探測中" />}

      {!error && data && (
        <>
          <div className={`admin-health-summary tone-${data.overall}`}>
            <span className="admin-health-summary-icon" aria-hidden="true">
              <AdminAlertIcon />
            </span>
            <div>
              <div className="admin-health-summary-title">
                整體狀態：{TONE_LABEL[data.overall]}
              </div>
              <div className="admin-health-summary-time">
                檢查於 {formatDateTime(data.checked_at)}
                {loading && " · 更新中…"}
              </div>
            </div>
          </div>

          {/* ---- 掃描鏈路 ---- */}
          <section className="admin-panel">
            <div className="admin-panel-head-row">
              <h3>掃描鏈路</h3>
              <span className="admin-cell-secondary">
                依掃描實際流經的順序；斷點之後的環節會停止流動
              </span>
            </div>
            <AdminScanChain chain={data.chain} />
          </section>

          {/* ---- 叢集節點 ---- */}
          <section className="admin-panel">
            <div className="admin-panel-head-row">
              <h3>
                叢集節點
                {data.cluster?.available && (
                  <span className="admin-panel-hint">
                    {" "}{data.cluster.totals.nodes_ready} / {data.cluster.totals.nodes} Ready · 共 {data.cluster.totals.pods} 個 pod
                  </span>
                )}
              </h3>
              <span className="admin-cell-secondary">
                {data.cluster?.available
                  ? data.cluster.metrics?.available
                    ? "CPU／記憶體為 metrics-server 的實際用量"
                    : `CPU／記憶體為 pod requests 佔可分配量的比例（${data.cluster.metrics?.reason || "沒有 metrics-server"}）`
                  : "需要在 Kubernetes 內執行"}
              </span>
            </div>
            {data.cluster?.available ? (
              <AdminClusterNodes cluster={data.cluster} />
            ) : (
              <p className="admin-empty">{data.cluster?.reason || "無法取得叢集狀態"}</p>
            )}
          </section>

          {/* ---- Argus 工作負載 ---- */}
          {data.cluster?.available && (
            <section className="admin-panel">
              <div className="admin-panel-head-row">
                <h3>
                  Argus 工作負載
                  <span className="admin-panel-hint"> {data.cluster.totals.argus_pods} 個 pod</span>
                </h3>
                <span className="admin-cell-secondary">argus／argus-zap／argus-kali 三個 namespace，依元件分組</span>
              </div>
              <AdminWorkloads cluster={data.cluster} />
            </section>
          )}

          {/* ---- 逐項判定依據 ---- */}
          <section className="admin-panel">
            <div className="admin-panel-head-row">
              <h3>檢查明細</h3>
            </div>
            <ul className="admin-health-list">
              {data.checks.map((check) => (
                <HealthRow key={check.key} check={check} />
              ))}
            </ul>
          </section>

          {/* 回應這個請求的 web pod 自己的數字：縮成一行，剛重啟時仍提醒 */}
          {data.system && (
            <p className="admin-page-note">
              回應這次請求的 web pod（{data.system.hostname || "—"}）：
              記憶體 {data.system.memory?.available
                ? `${formatBytes(data.system.memory.used_bytes)} / ${formatBytes(data.system.memory.total_bytes)}（${data.system.memory.percent}%）`
                : "無法取得"}
              、程序運行 {formatUptime(data.system.uptime?.process_seconds)}
              {data.system.uptime?.process_seconds !== undefined && data.system.uptime.process_seconds < 600 && "——啟動未滿 10 分鐘，若非剛部署，可能是 pod 近期重啟過"}
              。探測逾時 1.5 秒，偶發抖動可能誤報，連續兩次異常才值得追查；
              排查順序見 <code>docs/environment-preflight.md</code>。
            </p>
          )}
        </>
      )}
    </div>
  );
}
