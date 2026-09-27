import { ChevronIcon, SparkIcon } from "../../shared/LineIcons.jsx";

// 鏈路圖渲染器：六階段主流程 → 末端扇出交付物。
//
// 版面依使用者提供的設計稿（掃描鏈路圖.png）實作：
//   · 主流程是一排編號卡片，箭頭相連
//   · 其中一階段可以是「群組」——外框內含數張子卡（設計稿的 03 多引擎交叉診斷）
//   · 末端從一個匯流點扇出數張交付卡，各有自己的強調色
//
// 只負責「怎麼畫」，內容由 stages／outputs 傳入，換一組資料就是另一張圖。
//
// 強調色用 data-tone 帶進 CSS（cyan／teal／amber／violet），圖示以 currentColor
// 描邊，所以卡片邊框、徽章與圖示自動同色，不必每處各寫一次顏色。
//
// 扇出線的端點與交付卡的垂直位置都用同一組百分比算出，因此線一定接在卡片上
// ——先前版本兩者各算各的，線就指向了空白處。

function Badge({ text, tone }) {
  return <span className={`pl-badge tone-${tone || "cyan"}`}>{text}</span>;
}

/** 群組內的子卡（設計稿 03 的三張）。 */
function SubCard({ item }) {
  const Icon = item.icon;
  return (
    <div className="pl-sub" data-tone={item.tone || "cyan"}>
      <span className="pl-sub-icon">{Icon && <Icon />}</span>
      <span className="pl-sub-body">
        <span className="pl-sub-title">{item.title}</span>
        {item.desc && <span className="pl-sub-desc">{item.desc}</span>}
        {item.badge && <Badge text={item.badge} tone={item.tone} />}
      </span>
    </div>
  );
}

/** 主流程的一個階段：一般卡片，或含子卡的群組。 */
function Stage({ stage }) {
  const Icon = stage.icon;

  if (stage.group) {
    return (
      <div className="pl-stage pl-stage-group" data-tone={stage.tone || "cyan"}>
        <div className="pl-group-head">
          <span className="pl-num">{stage.index}</span>
          <span className="pl-group-title">{stage.title}</span>
        </div>
        <div className="pl-group-body">
          {stage.group.map((item) => <SubCard key={item.title} item={item} />)}
        </div>
      </div>
    );
  }

  return (
    <div className="pl-stage" data-tone={stage.tone || "cyan"}>
      <span className="pl-num">{stage.index}</span>
      <span className="pl-stage-icon">{Icon && <Icon />}</span>
      <span className="pl-stage-title">{stage.title}</span>
      {stage.lines?.map((line) => (
        <span className="pl-stage-line" key={line}>{line}</span>
      ))}
      {stage.badge && <Badge text={stage.badge} tone={stage.tone} />}
    </div>
  );
}

/** 階段之間的連接箭頭。 */
function Arrow() {
  return (
    <span className="pl-arrow" aria-hidden="true">
      <span className="pl-arrow-line" />
      <span className="pl-arrow-head" />
    </span>
  );
}

/** 末端扇出的交付卡。 */
function OutputCard({ item }) {
  const Icon = item.icon;
  return (
    <div className="pl-out" data-tone={item.tone || "cyan"}>
      <span className="pl-out-icon">{Icon && <Icon />}</span>
      <span className="pl-out-body">
        <span className="pl-out-title">{item.title}</span>
        {item.desc && <span className="pl-out-desc">{item.desc}</span>}
      </span>
      <span className="pl-out-chevron" aria-hidden="true"><ChevronIcon /></span>
    </div>
  );
}

export function PipelineDiagram({ title, subtitle, note, stages, outputs, ariaLabel }) {
  // 扇出線端點與交付卡共用同一組百分比，線一定接得上
  const fanY = outputs.map((_, i) => (100 / (outputs.length + 1)) * (i + 1));

  return (
    <div className="pl-wrap" aria-label={ariaLabel}>
      <header className="pl-head">
        <div className="pl-head-text">
          <h3 className="pl-title">{title}</h3>
          {subtitle && <p className="pl-subtitle">{subtitle}</p>}
        </div>
        {note && (
          <span className="pl-note">
            <SparkIcon className="pl-note-icon" />
            {note}
          </span>
        )}
      </header>

      <div className="pl-flow">
        <div className="pl-stages">
          {stages.map((stage, i) => (
            <div className="pl-stage-slot" key={stage.title}>
              <Stage stage={stage} />
              {i < stages.length - 1 && <Arrow />}
            </div>
          ))}
        </div>

        {/* 匯流點 ＋ 扇出線 */}
        <div className="pl-fan">
          <span className="pl-hub" aria-hidden="true" />
          <svg className="pl-fan-wires" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {fanY.map((y, i) => (
              <g key={y}>
                <path className="pl-wire-base" d={`M0,50 C55,50 45,${y} 100,${y}`} pathLength="100" />
                <path
                  className="pl-wire-pulse"
                  d={`M0,50 C55,50 45,${y} 100,${y}`}
                  pathLength="100"
                  style={{ animationDelay: `${i * 0.5}s` }}
                />
              </g>
            ))}
          </svg>
        </div>

        <div className="pl-outputs">
          {outputs.map((item) => <OutputCard key={item.title} item={item} />)}
        </div>
      </div>
    </div>
  );
}
