import {
  BrainIcon,
  GlobeIcon,
  MagnifierIcon,
  ShieldIcon,
  TargetIcon,
} from "../../shared/LineIcons";

// 首頁「五個掃描維度」：每一維有自己的品牌維度色（--ag-cat-*），
// 報告裡的 category-pill、分數長條都用同一組色，訪客在首頁看過就認得。
// 檢查項目只列規則引擎實際有的（backend/apps/insights、apps/scans 的 scanner）。

const DIMENSIONS = [
  {
    key: "seo",
    code: "SEO",
    name: "搜尋可見度",
    Icon: MagnifierIcon,
    desc: "搜尋引擎能不能讀懂、願不願意排前面。",
    checks: ["title / meta", "H1 結構", "canonical", "圖片 alt"],
  },
  {
    key: "aeo",
    code: "AEO",
    name: "答案引擎",
    Icon: BrainIcon,
    desc: "問答型搜尋能不能直接引用你的內容。",
    checks: ["FAQ Schema", "問答結構", "llms.txt"],
  },
  {
    key: "geo",
    code: "GEO",
    name: "生成式搜尋",
    Icon: GlobeIcon,
    desc: "AI 助理能不能認出你是誰、提供什麼。",
    checks: ["JSON-LD 實體", "Open Graph", "結構化資料"],
  },
  {
    key: "security",
    code: "SEC",
    name: "資安",
    Icon: ShieldIcon,
    desc: "被動檢查傳輸與標頭；主動測試需先驗證網域。",
    checks: ["HTTPS", "CSP / HSTS", "OWASP / CWE"],
  },
  {
    key: "ux",
    code: "UX",
    name: "使用體驗",
    Icon: TargetIcon,
    desc: "Agent 像真人一樣操作，找出卡住的地方。",
    checks: ["行動版 viewport", "操作流程", "效能訊號"],
  },
];

export function DimensionGrid() {
  return (
    <ul className="dim-grid">
      {DIMENSIONS.map(({ key, code, name, Icon, desc, checks }) => (
        <li key={key} className={`dim-card cat-${key}`}>
          <div className="dim-card-head">
            <span className="dim-card-icon"><Icon /></span>
            <span className="dim-card-code">{code}</span>
          </div>
          <h3 className="dim-card-name">{name}</h3>
          <p className="dim-card-desc">{desc}</p>
          <ul className="dim-card-checks" aria-label={`${name}檢查項目`}>
            {checks.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </li>
      ))}
    </ul>
  );
}

export default DimensionGrid;
