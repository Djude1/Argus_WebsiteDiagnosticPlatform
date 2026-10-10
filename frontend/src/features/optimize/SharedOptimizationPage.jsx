import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api";
import { ArgusLogo } from "../../components/brand/ArgusMark";
import OptimizationReport from "../../components/optimize/OptimizationReport";
import { formatDateTime } from "../../shared/formatters";

/**
 * /optimized/:token：分享出去的優化結果（唯讀）。
 *
 * 參考 Notion／Figma 的公開頁：只有精簡的頁首與成果本身，沒有 Argus 會員區的導覽、
 * 側邊欄或任何管理動作；看不到分享者的帳號、點數、專案與其他頁面。
 * 分享設定為「需登入」時，未登入的人只看到登入提示。
 */
export default function SharedOptimizationPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading"); // loading | ready | login | missing

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    api
      .get(`/share/rebuilds/${token}/`)
      .then((response) => {
        if (cancelled) return;
        setData(response.data);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setState(err?.response?.status === 401 || err?.response?.status === 403 ? "login" : "missing");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const loadHtml = useCallback(
    (variant) =>
      api
        .get(`/share/rebuilds/${token}/html/?variant=${variant}`, { responseType: "text" })
        .then((response) => response.data),
    [token],
  );

  return (
    <div className="member-legacy">
      <div className="opt-public">
        <header className="opt-public-bar">
          <Link to="/project" className="opt-public-brand" aria-label="Argus AI網站健檢平台">
            <ArgusLogo size={26} subtitle={null} />
          </Link>
          <span className="opt-public-badge">唯讀分享</span>
          <Link to="/project" className="opt-public-cta">用 Argus 檢查你的網站</Link>
        </header>

        <div className="opt-page is-public">
          {state === "loading" && <p className="opt-muted">載入中…</p>}
          {state === "missing" && (
            <section className="opt-empty">
              <h1 className="opt-title">這個分享連結無法使用</h1>
              <p className="opt-muted">連結可能輸入錯誤，或分享者已經關閉分享。請向分享給你的人確認。</p>
            </section>
          )}
          {state === "login" && (
            <section className="opt-empty">
              <h1 className="opt-title">請先登入 Argus</h1>
              <p className="opt-muted">分享者設定為「已登入 Argus 的人才能檢視」。登入後會自動回到這一頁。</p>
              <Link className="primary-button" to={`/login?next=${encodeURIComponent(`/optimized/${token}`)}`}>
                登入後檢視
              </Link>
            </section>
          )}
          {state === "ready" && data && (
            <>
              <header className="opt-head">
                <p className="opt-eyebrow">Argus 頁面優化結果</p>
                <h1 className="opt-title">{data.page_url}</h1>
                <p className="opt-meta">產生於 {formatDateTime(data.created_at)}</p>
              </header>
              <OptimizationReport data={data} loadHtml={loadHtml} />
              {data.reply && (
                <details className="opt-agent">
                  <summary>Argus 的完整說明</summary>
                  <div className="opt-agent-body">
                    <p className="opt-turn is-agent"><span>Argus</span>{data.reply}</p>
                  </div>
                </details>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
