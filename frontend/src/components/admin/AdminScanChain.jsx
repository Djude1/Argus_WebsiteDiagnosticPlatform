// 掃描鏈路圖。
//
// 取代原本的四項檢查清單：清單只告訴你「哪一項壞了」，鏈路圖還告訴你
// 「壞在哪一段、後面還有什麼因此跑不動」。節點順序就是掃描實際流經的環節
// （建立寫 DB → 派工進 Redis → worker 取件 → 佇列消化 → 實際執行）。
//
// 連接線的流動動畫只在「前後兩端都正常」時播放；一旦某節異常，它之後的線
// 全部停止流動並轉為靜態。這讓「斷在哪裡」用動態本身就看得出來，而不是
// 要人去比對一排顏色。
//
// 尊重 prefers-reduced-motion：關閉動態時改以虛線與箭頭表示方向。

const SYMBOL = { ok: "✓", warn: "!", bad: "✕", unknown: "?" };
const STATE_LABEL = { ok: "正常", warn: "注意", bad: "異常", unknown: "無法判定" };

export function AdminScanChain({ chain }) {
  if (!chain || chain.length === 0) return null;

  // 第一個異常節點之後（含）的連接線一律不流動
  const brokenAt = chain.findIndex((node) => node.status === "bad");

  return (
    <div className="admin-chain" role="list" aria-label="掃描鏈路狀態">
      {chain.map((node, index) => {
        const flowing = brokenAt === -1 || index < brokenAt;
        return (
          <div className="admin-chain-seg" key={node.key}>
            <div
              className={`admin-chain-node tone-${node.status}`}
              role="listitem"
              title={node.detail}
            >
              <span className="admin-chain-dot" aria-hidden="true">
                {SYMBOL[node.status]}
              </span>
              <span className="admin-chain-label">{node.label}</span>
              {/* 狀態文字與符號並存，不讓判讀只靠顏色 */}
              <span className="admin-chain-state">{STATE_LABEL[node.status]}</span>
            </div>
            {index < chain.length - 1 && (
              <div
                className={`admin-chain-link ${flowing ? "is-flowing" : "is-stalled"}`}
                aria-hidden="true"
              >
                <span className="admin-chain-link-track" />
                <span className="admin-chain-arrow">›</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
