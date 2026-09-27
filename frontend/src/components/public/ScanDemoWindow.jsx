import { IrisScore } from "../brand/IrisScore";
import { LockIcon } from "../../shared/LineIcons";
import { ArgusMark } from "../brand/ArgusMark";

// 首頁的產品預覽視窗：模擬一次掃描進行中的畫面＋報告摘要。
//
// 這是示意畫面不是真實掃描，所以標題列標了「示意」——首頁放一個看起來像
// 真實資料的東西卻不說明，等於誤導。
//
// 四筆 finding 對應真實規則：HTTPS（security）、JSON-LD（geo）、
// alt 屬性（seo）、llms.txt（aeo），嚴重度也照實際的評分權重排。
// 嚴重度一律附文字標籤，不只靠顏色。

const DEMO_FINDINGS = [
  { sev: "high", label: "高", cat: "security", catLabel: "資安", title: "頁面未使用 HTTPS", meta: "影響 3 個頁面" },
  { sev: "medium", label: "中", cat: "geo", catLabel: "GEO", title: "缺少 JSON-LD 結構化資料", meta: "AI 無法辨識實體" },
  { sev: "low", label: "低", cat: "seo", catLabel: "SEO", title: "圖片缺 alt 屬性", meta: "3 張圖片" },
  { sev: "info", label: "提示", cat: "aeo", catLabel: "AEO", title: "建議加 llms.txt 給 AI 爬蟲", meta: "尚未建立" },
];

const DEMO_DIMENSIONS = [
  { key: "seo", label: "SEO", score: 84 },
  { key: "aeo", label: "AEO", score: 71 },
  { key: "geo", label: "GEO", score: 66 },
  { key: "security", label: "資安", score: 58 },
  { key: "ux", label: "UX", score: 90 },
];

export function ScanDemoWindow() {
  return (
    <div className="demo-win" aria-label="掃描畫面示意">
      <div className="demo-bar">
        <span className="demo-dots" aria-hidden="true"><i /><i /><i /></span>
        <span className="demo-url">
          <LockIcon className="demo-url-icon" />
          argus.example.com
        </span>
        <span className="demo-tag">示意</span>
      </div>

      <div className="demo-body">
        <div className="demo-main">
          <div className="demo-phase">
            <ArgusMark size={30} scanning />
            <span className="demo-phase-text">
              <strong>爬取與診斷中</strong>
              <span className="demo-phase-sub ag-num">12 / 50 頁 · 已用 00:42</span>
            </span>
            <span className="demo-live"><span className="demo-live-dot" />即時</span>
          </div>
          <div className="demo-progress" aria-hidden="true">
            <span className="demo-progress-fill" />
          </div>
          <ul className="demo-findings">
            {DEMO_FINDINGS.map((f, i) => (
              <li
                className={`demo-finding sev-${f.sev}`}
                key={f.title}
                style={{ animationDelay: `${0.4 + i * 0.35}s` }}
              >
                <span className={`severity ${f.sev}`}>{f.label}</span>
                <span className="demo-finding-main">
                  <span className="demo-finding-title">{f.title}</span>
                  <span className="demo-finding-meta">{f.meta}</span>
                </span>
                <span className={`category-pill cat-${f.cat}`}>{f.catLabel}</span>
              </li>
            ))}
          </ul>
        </div>

        <aside className="demo-summary" aria-label="範例報告摘要">
          <IrisScore score={72} size={112} caption="整體" />
          <ul className="demo-dims">
            {DEMO_DIMENSIONS.map((d) => (
              <li key={d.key} className={`demo-dim cat-${d.key}`}>
                <span className="demo-dim-label">{d.label}</span>
                <span className="demo-dim-track" aria-hidden="true">
                  <span className="demo-dim-fill" style={{ width: `${d.score}%` }} />
                </span>
                <span className="demo-dim-score ag-num">{d.score}</span>
              </li>
            ))}
          </ul>
          <p className="demo-summary-note">
            <strong>Top Action</strong>
            先把全站導向 HTTPS：一次修好 3 個頁面的高風險問題。
          </p>
        </aside>
      </div>
    </div>
  );
}

export default ScanDemoWindow;
