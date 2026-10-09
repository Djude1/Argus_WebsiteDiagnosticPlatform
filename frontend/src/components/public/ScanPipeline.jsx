import { PipelineDiagram } from "./PipelineDiagram.jsx";
import {
  BrainIcon,
  BrowserIcon,
  DocIcon,
  ImageIcon,
  LayersIcon,
  MagnifierIcon,
  RobotIcon,
  RulesIcon,
  ScoreIcon,
  ShieldIcon,
  SparkIcon,
  TargetIcon,
} from "../../shared/LineIcons.jsx";

// 首頁掃描鏈路圖的內容，依設計稿「掃描鏈路圖.png」逐項對應，文字以現況為準。
// 主標題與徽章用中文，英文術語只留在說明小字。
// 04 覆蓋確認對應 backend/apps/scans/coverage.py（每項檢查記成功／略過／失敗／未評估）。
// 交付物：報告只出 PDF；原本的「可執行修正」已在 2026-10-06 由「頁面優化」取代。

const STAGES = [
  {
    index: "01",
    tone: "cyan",
    icon: ShieldIcon,
    title: "授權與安全閘門",
    lines: ["授權確認・網域驗證"],
    badge: "主動測試需先驗證",
  },
  {
    index: "02",
    tone: "cyan",
    icon: BrowserIcon,
    title: "真實渲染爬取",
    lines: ["Playwright 跑完 JS"],
    badge: "只走同網域頁面",
  },
  {
    index: "03",
    tone: "cyan",
    title: "三種引擎",
    group: [
      {
        tone: "cyan",
        icon: RulesIcon,
        title: "規則引擎",
        desc: "SEO · AEO · GEO · UX · 資安",
        badge: "被動＋主動",
      },
      {
        tone: "teal",
        icon: TargetIcon,
        title: "主動安全工具",
        desc: "Nuclei · Katana · 路徑探測",
        badge: "主動・需授權",
      },
      {
        tone: "violet",
        icon: RobotIcon,
        title: "Agent 行為測試",
        desc: "Hermes-Agent 模擬操作網站",
        badge: "主動・整站",
      },
    ],
  },
  {
    index: "04",
    tone: "cyan",
    icon: LayersIcon,
    title: "覆蓋確認",
    lines: ["成功・略過", "失敗・未評估"],
    badge: "確認檢查真的跑完",
  },
  {
    index: "05",
    tone: "cyan",
    icon: MagnifierIcon,
    title: "證據化問題",
    lines: ["截圖・元素位置", "OWASP / CWE 對照"],
    badge: "可定位・可追溯",
  },
  {
    index: "06",
    tone: "amber",
    icon: ScoreIcon,
    title: "評分與優先修正",
    lines: ["嚴重度與優先序"],
    badge: "最該先修的項目",
  },
];

const OUTPUTS = [
  { tone: "cyan", icon: ImageIcon, title: "互動報告", desc: "點擊問題跳到截圖位置" },
  { tone: "teal", icon: DocIcon, title: "防偽 PDF 報告", desc: "唯一編號・可公開查驗" },
  { tone: "amber", icon: SparkIcon, title: "頁面優化", desc: "修正後頁面・前後對照" },
  { tone: "violet", icon: BrainIcon, title: "AI 修復交接", desc: "帶入 ChatGPT / Claude" },
];

export function ScanPipeline() {
  return (
    <PipelineDiagram
      stages={STAGES}
      outputs={OUTPUTS}
      ariaLabel="Argus 掃描鏈路：從授權閘門到報告與頁面優化"
    />
  );
}
