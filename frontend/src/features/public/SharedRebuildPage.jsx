import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api";
import { formatDateTime } from "../../shared/formatters";

const VIEWS = [
  { key: "compare", label: "並排比較" },
  { key: "optimized", label: "優化後" },
  { key: "original", label: "原樣" },
];

// 分享頁載入的 HTML 來自第三方網站：iframe 一律 sandbox（不給任何權限＝不執行 script、
// 不能送表單、不能導覽上層），後端回應另有 CSP sandbox 與只能被本站內嵌的限制。
function PagePreview({ token, variant, label }) {
  return (
    <figure className="share-preview">
      <figcaption>{label}</figcaption>
      <iframe
        title={label}
        src={`/api/share/rebuilds/${token}/html/?variant=${variant}`}
        sandbox=""
        referrerPolicy="no-referrer"
        loading="lazy"
      />
    </figure>
  );
}

/**
 * /share/rebuilds/:token：網站主分享給 UI/UX 工程師的唯讀檢視（不需登入）。
 * 只有受測網址、原樣與優化後的頁面、修改清單與說明；不含帳號、點數或掃描資料。
 */
export default function SharedRebuildPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [view, setView] = useState("compare");

  useEffect(() => {
    let cancelled = false;
    api
      .get(`/share/rebuilds/${token}/`)
      .then((response) => !cancelled && setData(response.data))
      .catch(() => !cancelled && setError("這個分享連結不存在、已過期或已停止分享。"));
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (error) {
    return (
      <section className="share-page">
        <h1 className="share-title">網頁優化預覽</h1>
        <p className="share-error">{error}</p>
        <Link className="share-link" to="/project">認識 Argus 網站健檢</Link>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="share-page">
        <p className="share-meta">載入中…</p>
      </section>
    );
  }

  const views = VIEWS.filter(
    (item) =>
      (item.key !== "optimized" || data.has_optimized) &&
      (item.key !== "original" || data.has_original) &&
      (item.key !== "compare" || (data.has_optimized && data.has_original)),
  );
  const current = views.some((item) => item.key === view) ? view : views[0]?.key;
  const applied = data.edits.filter((edit) => edit.applied > 0);
  const skipped = data.edits.length - applied.length;

  return (
    <section className="share-page">
      <header className="share-head">
        <p className="share-eyebrow">Argus 網頁優化預覽</p>
        <h1 className="share-title">{data.page_url}</h1>
        <p className="share-meta">
          產生於 {formatDateTime(data.created_at)}・分享連結 {formatDateTime(data.expires_at)} 到期
        </p>
        <p className="share-notice">
          預覽畫面不執行網站的程式（JavaScript），選單、輪播等互動功能可能無法操作；版面、文字與標記的修改都看得到。
        </p>
      </header>

      {views.length > 1 && (
        <div className="share-tabs" role="tablist" aria-label="檢視方式">
          {views.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={current === item.key}
              className={`share-tab ${current === item.key ? "is-active" : ""}`}
              onClick={() => setView(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      <div className={`share-previews ${current === "compare" ? "is-compare" : ""}`}>
        {(current === "compare" || current === "original") && data.has_original && (
          <PagePreview token={token} variant="original" label="原樣" />
        )}
        {(current === "compare" || current === "optimized") && data.has_optimized && (
          <PagePreview token={token} variant="optimized" label="優化後" />
        )}
      </div>

      {data.edits.length > 0 && (
        <section className="share-section">
          <h2 className="share-section-title">
            修改了什麼（{applied.length} 項{skipped ? `，另 ${skipped} 項未套用` : ""}）
          </h2>
          <ol className="share-edits">
            {data.edits.map((edit, index) => (
              <li key={index} className={edit.applied ? "" : "is-skipped"}>
                {edit.why || "（未說明）"}
                {edit.applied > 1 && <span className="share-edit-count">共 {edit.applied} 處</span>}
                {!edit.applied && (
                  <span className="share-edit-count">
                    {edit.rejected ? `未套用：${edit.rejected}` : "未套用：原文對不上"}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {data.reply && (
        <section className="share-section">
          <h2 className="share-section-title">說明與未處理的項目</h2>
          <p className="share-reply">{data.reply}</p>
        </section>
      )}
    </section>
  );
}
