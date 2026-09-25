import { PipelineDiagram } from "./PipelineDiagram.jsx";
import {
  BrainIcon,
  BrowserIcon,
  CodeIcon,
  DocIcon,
  ImageIcon,
  LayersIcon,
  MagnifierIcon,
  RobotIcon,
  RulesIcon,
  ScoreIcon,
  ShieldIcon,
  TargetIcon,
} from "../../shared/LineIcons.jsx";

// 首頁掃描鏈路圖的內容，依設計稿「掃描鏈路圖.png」逐項對應。
//
// ⚠ 04 Coverage + Evidence 目前是**設計稿有、程式尚未實作**的階段。
//    設計稿寫「Success · Skipped · Failed · Not Evaluated ／ 先確認檢測是否
//    真的成功執行」——那正是 2026-09-25 稽核報告列為 P0-1 的缺口：目前多數
//    子掃描器失敗時回傳空陣列，畫面無法區分「檢查過沒問題」與「工具沒跑成功」。
//    其餘五個階段與四項交付物都對應實際程式。

const STAGES = [
  {
    index: "01",
    tone: "cyan",
    icon: ShieldIcon,
    title: "授權與安全閘門",
    lines: ["授權確認 · 網域所有權驗證"],
    badge: "主動測試需先驗證網站",
  },
  {
    index: "02",
    tone: "cyan",
    icon: BrowserIcon,
    title: "真實渲染爬取",
    lines: ["Playwright 跑完 JS"],
    badge: "Same-Origin BFS",
  },
  {
    index: "03",
    tone: "cyan",
    title: "多引擎交叉診斷",
    group: [
      {
        tone: "cyan",
        icon: RulesIcon,
        title: "規則引擎",
        desc: "SEO · AEO · GEO · UX · 資安",
        badge: "PASSIVE + ACTIVE",
      },
      {
        tone: "teal",
        icon: TargetIcon,
        title: "主動安全工具",
        desc: "Nuclei · Katana · 路徑探測",
        badge: "ACTIVE",
      },
      {
        tone: "violet",
        icon: RobotIcon,
        title: "Agent 行為測試",
        desc: "Hermes-Agent 模擬操作網站",
        badge: "ACTIVE FULL-SITE",
      },
    ],
  },
  {
    index: "04",
    tone: "cyan",
    icon: LayersIcon,
    title: "Coverage + Evidence",
    lines: ["Success · Skipped", "Failed · Not Evaluated"],
    badge: "先確認檢測是否真的成功執行",
  },
  {
    index: "05",
    tone: "cyan",
    icon: MagnifierIcon,
    title: "證據化 Findings",
    lines: ["Screenshot · Selector", "Evidence · OWASP / CWE"],
    badge: "可定位、可解釋、可追溯",
  },
  {
    index: "06",
    tone: "amber",
    icon: ScoreIcon,
    title: "評分與 Top Actions",
    lines: ["Severity · Priority · Score"],
    badge: "找出最重要的修正行動",
  },
];

const OUTPUTS = [
  { tone: "cyan", icon: ImageIcon, title: "互動報告", desc: "點擊問題跳到截圖位置" },
  { tone: "teal", icon: DocIcon, title: "可驗證報告", desc: "DOCX · SHA-256 防偽" },
  { tone: "amber", icon: CodeIcon, title: "可執行修正", desc: "JSON-LD · llms.txt · FAQ" },
  { tone: "violet", icon: BrainIcon, title: "AI 修復交接", desc: "可直接帶入 ChatGPT / Claude" },
];

export function ScanPipeline() {
  return (
    <PipelineDiagram
      title="三種引擎交叉診斷"
      subtitle="從網站掃描到可執行修正，一站式完整解決方案"
      note="不只指出問題，還提供可執行的修正方案"
      stages={STAGES}
      outputs={OUTPUTS}
      ariaLabel="Argus 掃描鏈路：從授權閘門到可執行修正"
    />
  );
}
