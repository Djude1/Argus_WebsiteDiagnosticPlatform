/**
 * 首頁 hero 與技術棧之間的段落（2026-10-09 依使用者要求改版）。
 * 參考 TradingGoose 首頁的動態做法自行實作：捲入畫面依序淡入（Reveal）、
 * 堆疊卡片輪播、即時更新的掃描表格、掃描鏈路圖（流動連線）、左右交錯的功能列與可操作的預覽、
 * 滑鼠跟隨的卡片光暈。
 * 最上面的品牌 hero 與「技術棧」以下（FAQ、結尾 CTA）不在這裡，維持原樣。
 * 內容都以現有程式核對；原本讀 CMS 的「核心功能」與其他段落重複且內容過時，2026-10-09 移除。
 */
import { useRef } from "react";

import {
  BrowserIcon,
  ChatIcon,
  DocIcon,
  EyeIcon,
  GlobeIcon,
  LayersIcon,
  LockIcon,
  MagnifierIcon,
  PhoneIcon,
  ScoreIcon,
  ShieldIcon,
  SparkIcon,
  TargetIcon,
} from "../../../shared/LineIcons.jsx";
import { ScanPipeline } from "../ScanPipeline.jsx";
import CompareSlider from "./CompareSlider.jsx";
import CoverageTabs from "./CoverageTabs.jsx";
import { GlowCard, Reveal, useCardGlow } from "./HomeMotion.jsx";
import LiveScanTable from "./LiveScanTable.jsx";
import ProcessStack from "./ProcessStack.jsx";
import ReportPreview from "./ReportPreview.jsx";
import VerifyPreview from "./VerifyPreview.jsx";

const STEPS = [
  {
    Icon: LockIcon, short: "授權", title: "授權與網域驗證",
    desc: "送出即聲明你有權檢查這個網站；主動式資安測試必須先驗證網域所有權。",
  },
  {
    Icon: BrowserIcon, short: "走訪", title: "真實瀏覽器走訪",
    desc: "以 Playwright 渲染每一頁並截圖，同網域最多 50 頁，遵守 robots.txt。",
  },
  {
    Icon: LayersIcon, short: "診斷", title: "多引擎交叉診斷",
    desc: "規則引擎檢查五個面向，搭配 axe-core、PageSpeed Insights 等業界工具。",
  },
  {
    Icon: ScoreIcon, short: "排序", title: "證據與優先順序",
    desc: "每個問題附位置與證據，依嚴重度排出先修哪個；沒跑完的檢查會明講。",
  },
];

const COVERAGE = [
  {
    key: "seo", code: "SEO", name: "搜尋可見度", Icon: MagnifierIcon,
    desc: "搜尋引擎能不能正確收錄、看懂你的頁面。",
    checks: [
      "Title、description 的長度與重複",
      "H1 與標題結構、圖片替代文字",
      "canonical、noindex 與 sitemap 是否互相矛盾",
      "失效連結與跳轉鏈",
    ],
  },
  {
    key: "aeo", code: "AEO", name: "AI 問答", Icon: ChatIcon,
    desc: "AI 助理回答關於你的問題時，能不能在網站上找到答案。",
    checks: [
      "從網站內容出題，檢查能否找到明確答案",
      "答案是否附原文、能否被引用",
      "價格、營業時間等資訊在不同頁面是否矛盾",
    ],
  },
  {
    key: "geo", code: "GEO", name: "生成式搜尋", Icon: SparkIcon,
    desc: "生成式搜尋引擎能不能辨認你是誰、引用你的內容。",
    checks: [
      "JSON-LD 組織實體與 sameAs",
      "文章的作者與發布、更新日期",
      "段落結構與可引用的內容區塊",
      "llms.txt 與 AI 爬蟲政策",
    ],
  },
  {
    key: "security", code: "資安", name: "被動資安", Icon: ShieldIcon,
    desc: "不發動攻擊，只讀公開回應就能看出的資安設定。",
    checks: [
      "HTTPS 與憑證、CSP／HSTS 等安全標頭",
      "Cookie 旗標、SPF／DMARC 寄件驗證",
      "含已知漏洞的軟體版本（OSV＋EPSS 排序）",
      "敏感檔案與個資外洩",
    ],
  },
  {
    key: "ux", code: "UX", name: "使用體驗", Icon: PhoneIcon,
    desc: "實際用手機與電腦視窗打開，看使用者會卡在哪。",
    checks: [
      "axe-core WCAG 2.2 無障礙檢查",
      "手機觸控目標、表單標籤與破版",
      "版面位移（CLS）與載入速度",
    ],
  },
];

const FEATURES = [
  {
    Icon: TargetIcon, badge: "互動報告", title: "截圖上直接框出問題",
    desc: "點一個問題，就跳到頁面上的實際位置，並列出觸發它的原始證據。",
    points: ["每個問題附位置、證據與觸發規則", "同一處設定造成的問題合併成「改一處一起解決」", "分數說明逐項列出扣分來源"],
    Preview: ReportPreview, side: "left",
  },
  {
    Icon: DocIcon, badge: "PDF 報告", title: "可交付、可查驗",
    desc: "一鍵匯出 PDF，開頭先列最該處理的三件事；收件者能公開核對內容沒被改過。",
    points: ["每項附修好後如何確認", "唯一報告編號，查驗不需登入", "適合直接交給主管或外包廠商"],
    Preview: VerifyPreview, side: "right",
  },
  {
    Icon: SparkIcon, badge: "頁面優化", title: "直接產出修正後的頁面",
    desc: "針對單一頁面產出優化版，前後對照並列出每一處修改與原因。",
    points: ["桌面與手機前後對照", "修改依視覺、SEO、無障礙、效能分組", "可分享連結或下載優化版 HTML"],
    Preview: CompareSlider, side: "left",
  },
];

// 安全邊界：每一項都對應實際程式
const SAFETY = [
  { Icon: LockIcon, title: "授權紀錄", desc: "每次送出都記錄時間、IP、User-Agent 與授權聲明全文。" },
  { Icon: GlobeIcon, title: "同網域範圍", desc: "爬蟲與證據只限授權網站的同網域頁面，不跨域追蹤。" },
  { Icon: ShieldIcon, title: "SSRF 防護", desc: "入口、轉址、子資源與 WebSocket 都檢查是否為公開位址。" },
  { Icon: EyeIcon, title: "被動為預設", desc: "預設不做主動測試；主動模式要另外同意並通過網域驗證。" },
];

// 核心功能的內容來自 CMS，管理員在後台填的是 emoji，這裡對映成描邊圖示
function SectionHead({ eyebrow, title, desc, center = false, id }) {
  return (
    <header className={`hx-head${center ? " is-center" : ""}`}>
      <Reveal as="p" className="hx-eyebrow">{eyebrow}</Reveal>
      <Reveal as="h2" className="hx-title" delay={0.15} id={id}>{title}</Reveal>
      {desc && <Reveal as="p" className="hx-desc" delay={0.3}>{desc}</Reveal>}
    </header>
  );
}

function Dashes({ items, delay = 0.45, slide = "down" }) {
  return (
    <ul className="hx-dashes">
      {items.map((text, i) => (
        <Reveal as="li" key={text} delay={delay + i * 0.1} slide={slide}>
          <span className="hx-dash" aria-hidden="true" />
          {text}
        </Reveal>
      ))}
    </ul>
  );
}

export function HomeSections() {
  const rootRef = useRef(null);
  useCardGlow(rootRef);

  return (
    <div ref={rootRef} className="hx">
      {/* 運作方式：左文右堆疊卡片輪播 */}
      <section className="public-section hx-section" aria-labelledby="hx-how-title">
        <div className="hx-split">
          <SectionHead
            id="hx-how-title"
            eyebrow="運作方式"
            title="從網址到修正清單"
            desc="輸入網址後，Argus 在背景用真實瀏覽器走訪、交叉檢查，再整理成有證據、有順序的修正清單。"
          />
          <Reveal slide="none" duration={0.7}>
            <ProcessStack steps={STEPS} />
          </Reveal>
        </div>
      </section>

      {/* 即時進度：左邊即時表格、右邊說明 */}
      <section className="public-section hx-section" aria-labelledby="hx-live-title">
        <div className="hx-split is-reverse">
          <Reveal slide="none" duration={0.7} className="hx-split-visual">
            <LiveScanTable />
          </Reveal>
          <div>
            <SectionHead
              id="hx-live-title"
              eyebrow="即時進度"
              title="掃描還在跑，就看得到結果"
              desc="掃描在背景執行，不必守在畫面前；走訪、各面向檢查與效能量測的進度即時更新。"
            />
            <Dashes items={["每個問題標明嚴重度與所屬面向", "檢查沒跑完會明講，不當成沒問題", "失敗或取消，預扣點數全額退回"]} />
          </div>
        </div>
      </section>

      {/* 檢測面向：五個分頁 */}
      <section className="public-section hx-section" aria-labelledby="hx-cov-title">
        <SectionHead
          id="hx-cov-title"
          center
          eyebrow="檢測面向"
          title="一次掃描，五個面向"
          desc="每個問題都標明屬於哪一個面向，只勾需要的面向就好。"
        />
        <Reveal slide="up" delay={0.2} className="hx-cov-wrap">
          <CoverageTabs items={COVERAGE} />
        </Reveal>
      </section>

      {/* 掃描鏈路圖：沿用原本的「三種引擎交叉診斷」圖，已拿掉螢光外框與發光圖示 */}
      <section className="public-section hx-section" aria-labelledby="hx-pipe-title">
        <SectionHead
          id="hx-pipe-title"
          center
          eyebrow="掃描鏈路"
          title="三種引擎交叉診斷"
          desc="從授權、爬取到交叉診斷，每一步都留下證據，最後交付報告與修正後的頁面。"
        />
        <Reveal slide="none" duration={0.8} delay={0.2} className="hx-pipe-wrap">
          <ScanPipeline />
        </Reveal>
      </section>

      {/* 你會拿到什麼：左右交錯的功能列，預覽可以操作 */}
      <section className="public-section hx-section hx-features" aria-labelledby="hx-feat-title">
        <span className="hx-grid-bg" aria-hidden="true" />
        <SectionHead
          id="hx-feat-title"
          center
          eyebrow="你會拿到什麼"
          title="不只是一份問題清單"
          desc="每個問題都能追溯、能排序、能修。"
        />
        <div className="hx-feature-rows">
          {FEATURES.map(({ Icon, badge, title, desc, points, Preview, side }, index) => {
            const previewLeft = side === "left";
            const textFrom = previewLeft ? "left" : "right";
            const previewFrom = previewLeft ? "right" : "left";
            return (
              <div className={`hx-feature${previewLeft ? " is-preview-left" : ""}`} key={badge}>
                <Reveal slide={textFrom} delay={index * 0.05} duration={0.6} className="hx-feature-text">
                  <GlowCard className="hx-feature-card">
                    <p className="hx-feature-head">
                      <span className="hx-icon-box"><Icon /></span>
                      <span className="hx-eyebrow">{badge}</span>
                    </p>
                    <h3 className="hx-h3">{title}</h3>
                    <p className="hx-desc is-small">{desc}</p>
                    <Dashes items={points} delay={0.25} slide={textFrom} />
                  </GlowCard>
                </Reveal>
                <Reveal slide={previewFrom} delay={0.15} duration={0.75} className="hx-feature-preview">
                  <Preview />
                </Reveal>
              </div>
            );
          })}
        </div>
      </section>

      {/* 安全邊界 */}
      <section className="public-section hx-section" aria-labelledby="hx-safe-title">
        <SectionHead id="hx-safe-title" center eyebrow="安全邊界" title="只檢查你有權限的網站" desc="每一項都對應實際程式碼，不是文宣。" />
        <div className="hx-card-grid is-four">
          {SAFETY.map(({ Icon, title, desc }, i) => (
            <Reveal key={title} slide="up" delay={i * 0.1}>
              <GlowCard className="hx-mini-card">
                <span className="hx-icon-box"><Icon /></span>
                <h3 className="hx-mini-title">{title}</h3>
                <p className="hx-mini-desc">{desc}</p>
              </GlowCard>
            </Reveal>
          ))}
        </div>
      </section>
    </div>
  );
}
