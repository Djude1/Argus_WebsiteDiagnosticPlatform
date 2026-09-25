import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../api";
import { AdminAlertIcon } from "../../components/admin/AdminIcons.jsx";
import { AdminScanChain } from "../../components/admin/AdminScanChain.jsx";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates.jsx";
import { AdminSystemStats } from "../../components/admin/AdminSystemStats.jsx";
import { formatDateTime } from "../../shared/formatters.js";

// 系統健康：把 docs/environment-preflight.md 的人工檢查變成畫面。
//
// 兩個區塊：
//   1. 掃描鏈路圖——看「斷在哪一段」，而不只是「哪一項壞了」
//   2. 系統資源——CPU／記憶體／磁碟／網路／運行時間
//
// 設計原則是「綠燈要可信」：每項檢查都顯示判定依據，樣本不足時顯示
// 「無法判定」而非綠燈。沒有資料不等於沒有問題。
//
// 這是即時探測，不是歷史監控。它回答「現在通不通」，不回答「過去壞過幾次」。

const TONE_LABEL = { ok: "正常", warn: "注意", bad: "異常", unknown: "無法判定" };
const TONE_SYMBOL = { ok: "✓", warn: "!", bad: "✕", unknown: "?" };
const AUTO_REFRESH_MS = 15000;

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
  // 網路速率要靠兩次取樣的差分；保留上一次的累計值與時間戳
  const previousNet = useRef(null);
  const [netRate, setNetRate] = useState(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/health/");
      const next = response.data;
      const net = next.system?.network;
      const prev = previousNet.current;
      if (net?.available && prev) {
        const seconds = (Date.now() - prev.at) / 1000;
        if (seconds > 0.5) {
          setNetRate({
            rx: Math.max(0, (net.rx_bytes - prev.rx) / seconds),
            tx: Math.max(0, (net.tx_bytes - prev.tx) / seconds),
          });
        }
      }
      if (net?.available) {
        previousNet.current = { rx: net.rx_bytes, tx: net.tx_bytes, at: Date.now() };
      }
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
          <p>掃描鏈路與系統資源的即時探測；這是「現在通不通」，不是歷史監控</p>
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

          {/* ---- 系統資源 ---- */}
          <section className="admin-panel">
            <div className="admin-panel-head-row">
              <h3>系統資源</h3>
              <span className="admin-cell-secondary">
                CPU 為瞬時取樣（0.15 秒），數字會有抖動
              </span>
            </div>
            <AdminSystemStats system={data.system} netRate={netRate} />
          </section>

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

          <p className="admin-page-note">
            探測逾時設為 1.5 秒，偶發的網路抖動可能造成誤報；連續兩次異常才值得追查。
            完整的環境排查順序見 <code>docs/environment-preflight.md</code>。
          </p>
        </>
      )}
    </div>
  );
}
