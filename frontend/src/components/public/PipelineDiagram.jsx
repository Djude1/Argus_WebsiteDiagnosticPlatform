import { ChevronIcon, SparkIcon } from "../../shared/LineIcons";

// 鏈路圖渲染器：六階段主流程 → 匯流 → 交付物。
//
// 版面（品牌改版後）：
//   · 主流程是一排編號卡片（<ol>），卡片間的箭頭用 CSS 畫在間距裡
//   · 其中一階段可以是「群組」——外框內含數張子卡（03 多引擎交叉診斷），欄寬較寬
//   · 主流程下方一條匯流線，往下接各交付卡
// 舊版把交付物接在主流程右側，1440 寬就會把最後一個階段擠出畫面；
// 改成上下兩層後，主流程只需要在一列內排六張卡，寬度不足時改成多列／單欄。
//
// 只負責「怎麼畫」，內容由 stages／outputs 傳入。
// 強調色用 data-tone（cyan／teal／amber／violet）帶進 CSS，對映到品牌 token；
// 圖示以 currentColor 描邊，所以卡片邊框、徽章與圖示自動同色。

function Badge({ text }) {
  return <span className="pl-badge">{text}</span>;
}

/** 群組內的子卡（03 的三張）。 */
function SubCard({ item }) {
  const Icon = item.icon;
  return (
    <div className="pl-sub" data-tone={item.tone || "cyan"}>
      <span className="pl-sub-icon">{Icon && <Icon />}</span>
      <span className="pl-sub-body">
        <span className="pl-sub-title">{item.title}</span>
        {item.desc && <span className="pl-sub-desc">{item.desc}</span>}
        {item.badge && <Badge text={item.badge} />}
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
          <span className="pl-num ag-num">{stage.index}</span>
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
      <span className="pl-num ag-num">{stage.index}</span>
      <span className="pl-stage-icon">{Icon && <Icon />}</span>
      <span className="pl-stage-title">{stage.title}</span>
      {stage.lines?.map((line) => (
        <span className="pl-stage-line" key={line}>{line}</span>
      ))}
      {stage.badge && <Badge text={stage.badge} />}
    </div>
  );
}

/** 末端的交付卡。 */
function OutputCard({ item }) {
  const Icon = item.icon;
  return (
    <li className="pl-out" data-tone={item.tone || "cyan"}>
      <span className="pl-out-icon">{Icon && <Icon />}</span>
      <span className="pl-out-body">
        <span className="pl-out-title">{item.title}</span>
        {item.desc && <span className="pl-out-desc">{item.desc}</span>}
      </span>
      <span className="pl-out-chevron" aria-hidden="true"><ChevronIcon /></span>
    </li>
  );
}

export function PipelineDiagram({ title, subtitle, note, stages, outputs, ariaLabel }) {
  return (
    <div className="pl-wrap" role="group" aria-label={ariaLabel}>
      <header className="pl-head">
        <div className="pl-head-text">
          <span className="ag-eyebrow">Scan pipeline</span>
          <h2 className="pl-title">{title}</h2>
          {subtitle && <p className="pl-subtitle">{subtitle}</p>}
        </div>
        {note && (
          <span className="pl-note">
            <SparkIcon className="pl-note-icon" />
            {note}
          </span>
        )}
      </header>

      <ol className="pl-stages">
        {stages.map((stage) => (
          <li className={`pl-stage-slot ${stage.group ? "is-group" : ""}`} key={stage.title}>
            <Stage stage={stage} />
          </li>
        ))}
      </ol>

      <div className="pl-merge" aria-hidden="true">
        <span className="pl-merge-line" />
        <span className="pl-merge-label">交付</span>
        <span className="pl-merge-line" />
      </div>

      <ul className="pl-outputs" aria-label="交付物">
        {outputs.map((item) => <OutputCard key={item.title} item={item} />)}
      </ul>
    </div>
  );
}
