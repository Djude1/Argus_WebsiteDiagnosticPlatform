import { useCallback, useEffect, useState } from "react";

import { api } from "../../api";
import { AdminAlertIcon } from "../../components/admin/AdminIcons.jsx";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates.jsx";
import { formatDateTime } from "../../shared/formatters.js";

// 系統健康：把 docs/environment-preflight.md 的人工檢查變成畫面。
//
// 設計原則是「綠燈要可信」——每一項都必須顯示判定依據，否則一排綠燈只會
// 給人虛假的安心感。樣本不足時顯示「無法判定」而非綠燈，這是刻意的：
// 沒有資料不等於沒有問題。
//
// 這是即時探測，不是歷史監控。它回答「現在通不通」，不回答「過去壞過幾次」。

const TONE_LABEL = {
  ok: "正常",
  warn: "注意",
  bad: "異常",
  unknown: "無法判定",
};

const TONE_SYMBOL = {
  ok: "✓",
  warn: "!",
  bad: "✕",
  unknown: "?",
};

function HealthRow({ check }) {
  return (
    <li className={`admin-health-row tone-${check.status}`}>
      {/* 狀態同時用色、符號與文字三重編碼，不讓判讀只靠顏色 */}
      <span className="admin-health-badge" aria-hidden="true">
        {TONE_SYMBOL[check.status]}
      </span>
      <div className="admin-health-body">
        <div className="admin-health-label">
          {check.label}
          <span className="admin-health-state">{TONE_LABEL[check.status]}</span>
        </div>
        <div className="admin-health-detail">{check.detail}</div>
        {/* 判定依據：讓綠燈可以被追查，而不是要人盲信 */}
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/health/");
      setData(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "無法取得健康狀態");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <div>
          <h1>系統健康</h1>
          <p>掃描鏈路的即時探測；這是「現在通不通」，不是歷史監控</p>
        </div>
        <button type="button" className="admin-btn" onClick={load} disabled={loading}>
          {loading ? "檢查中…" : "重新檢查"}
        </button>
      </header>

      {error && <AdminErrorState message="無法取得健康狀態" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="detail" rows={2} label="探測中" />}

      {!error && !loading && data && (
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
              </div>
            </div>
          </div>

          <section className="admin-panel">
            <ul className="admin-health-list">
              {data.checks.map((check) => (
                <HealthRow key={check.key} check={check} />
              ))}
            </ul>
          </section>

          <p className="admin-page-note">
            探測逾時設為 1.5 秒，因此偶發的網路抖動可能造成誤報；連續兩次異常才值得追查。
            完整的環境排查順序見 <code>docs/environment-preflight.md</code>。
          </p>
        </>
      )}
    </div>
  );
}
