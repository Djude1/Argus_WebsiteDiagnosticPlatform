import { useCallback, useEffect, useId, useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../../api";
import { ArgusMark } from "../../components/brand/ArgusMark";
import { IrisScore } from "../../components/brand/IrisScore";
import { PublicHero } from "../../components/public/PublicHero";
import { apiErrorMessage } from "../../shared/AppShared";
import { formatDateTime } from "../../shared/formatters";
import { DocIcon, LockIcon, ScoreIcon } from "../../shared/LineIcons";

const PROOFS = [
  { Icon: DocIcon, title: "編號存在", desc: "代表 Argus 確實為這個網站產生過報告。" },
  { Icon: ScoreIcon, title: "目標與時間", desc: "核對報告封面寫的網址與掃描時間是否被改過。" },
  { Icon: LockIcon, title: "內容指紋", desc: "比對 SHA-256 可確認整份檔案一個字都沒被動過。" },
];

export function VerifyReportPage() {
  // 讀者可能是「收到 .docx 的第三方」而不是 Argus 使用者：網址帶編號就直接查，
  // 沒帶就給輸入框讓他照著報告封面上的編號輸入。
  const { reportNumber: routeNumber } = useParams();
  const [input, setInput] = useState(routeNumber || "");
  const [state, setState] = useState({ loading: false, data: null, error: "" });
  const fieldId = useId();

  const lookup = useCallback(async (number) => {
    const trimmed = (number || "").trim().toUpperCase();
    if (!trimmed) return;
    setState({ loading: true, data: null, error: "" });
    try {
      const res = await api.get(`/verify/${encodeURIComponent(trimmed)}/`);
      setState({ loading: false, data: res.data, error: "" });
    } catch (err) {
      setState({
        loading: false,
        data: null,
        error: apiErrorMessage(err, "查驗失敗，請稍後再試。"),
      });
    }
  }, []);

  useEffect(() => {
    if (routeNumber) lookup(routeNumber);
  }, [routeNumber, lookup]);

  const data = state.data;

  return (
    <div className="public-page">
      <PublicHero
        eyebrow="Verify · 報告查驗"
        title={<>核對<em>報告真偽</em></>}
      >
        <p>
          收到一份 Argus 網站健檢報告？輸入封面上的報告編號，即可核對它確實由 Argus
          出具，以及當初掃描的目標與時間。查驗不需要登入。
        </p>
      </PublicHero>

      <section className="public-section">
        <div className="verify-layout">
          <div className="verify-main">
            <form
              className="insight-tool-card verify-form"
              onSubmit={(e) => {
                e.preventDefault();
                lookup(input);
              }}
            >
              <h2 className="insight-card-title">輸入報告編號</h2>
              <div className="insight-field">
                <label htmlFor={fieldId}>報告編號（在報告封面與每頁頁尾）</label>
                <div className="verify-input-row">
                  <input
                    id={fieldId}
                    className="input verify-input"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="ARGUS-28-20260831-A1B2"
                    autoComplete="off"
                    spellCheck={false}
                    required
                  />
                  <button type="submit" className="public-cta public-cta-primary" disabled={state.loading}>
                    {state.loading ? "查驗中…" : "查驗報告"}
                  </button>
                </div>
              </div>
            </form>

            <div aria-live="polite">
              {state.loading && (
                <div className="verify-result verify-result-loading" role="status">
                  <ArgusMark size={36} scanning />
                  <span>正在比對報告編號…</span>
                </div>
              )}

              {state.error && (
                <div className="verify-result verify-result-fail">
                  <div className="verify-result-head">
                    <span className="verify-result-icon" aria-hidden="true">!</span>
                    查無此編號
                  </div>
                  <p>{state.error}</p>
                  <p className="verify-result-note">
                    這份報告可能不是由 Argus 出具，或編號輸入有誤。請對照報告封面重新輸入。
                  </p>
                </div>
              )}

              {data && (
                <div className="verify-result verify-result-pass ag-viewfinder">
                  <div className="verify-result-top">
                    <div className="verify-result-head">
                      <ArgusMark size={28} />
                      <span>
                        <strong>這是一份由 Argus 出具的報告</strong>
                        <span className="verify-result-number">{data.report_number}</span>
                      </span>
                    </div>
                    <IrisScore
                      score={data.overall_score === null ? null : Number(data.overall_score)}
                      size={84}
                      caption={data.overall_score === null ? "尚未產生" : "整體"}
                    />
                  </div>
                  <dl className="verify-facts">
                    <div><dt>掃描目標</dt><dd className="verify-mono">{data.scan_target}</dd></div>
                    <div><dt>掃描完成</dt><dd>{formatDateTime(data.scanned_at)}</dd></div>
                    <div><dt>報告產生</dt><dd>{formatDateTime(data.generated_at)}</dd></div>
                    <div>
                      <dt>整體分數</dt>
                      <dd>{data.overall_score === null ? "尚未產生" : `${data.overall_score} / 100`}</dd>
                    </div>
                  </dl>
                  <p className="verify-result-note">
                    請核對上列資訊與你手上的報告是否一致。若要進一步確認檔案未被竄改，
                    可自行計算該 .docx 的 SHA-256 並與下方指紋比對。
                  </p>
                  <div className="verify-fingerprint">
                    <span className="verify-fingerprint-label">SHA-256</span>
                    <code>{data.content_sha256}</code>
                  </div>
                </div>
              )}
            </div>
          </div>

          <aside className="verify-aside">
            <h2 className="insight-card-title">查驗能證明什麼</h2>
            <ul className="verify-aside-list">
              {PROOFS.map(({ Icon, title, desc }) => (
                <li key={title}>
                  <span className="verify-aside-icon"><Icon /></span>
                  <span>
                    <strong>{title}</strong>
                    <span>{desc}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="verify-aside-note">查驗結果不會顯示是誰執行的掃描。</p>
          </aside>
        </div>
      </section>
    </div>
  );
}

export default VerifyReportPage;
