import { useState } from "react";

// 常見問題手風琴：一次只展開一題（開新題時舊題收起），預設展開第一題。
// 用原生 <details>，鍵盤與輔助技術不必另外處理。

export function PublicFaq({ items, defaultOpen = 0 }) {
  const [openIndex, setOpenIndex] = useState(defaultOpen);
  return (
    <div className="public-faq">
      {items.map((item, idx) => (
        <details
          key={item.q}
          open={openIndex === idx}
          onToggle={(e) => {
            if (e.currentTarget.open) setOpenIndex(idx);
            else if (openIndex === idx) setOpenIndex(-1);
          }}
          className="public-faq-item"
        >
          <summary>
            <span className="public-faq-index ag-num" aria-hidden="true">{String(idx + 1).padStart(2, "0")}</span>
            <span className="public-faq-q">{item.q}</span>
            <span className="public-faq-chevron" aria-hidden="true" />
          </summary>
          <p>{item.a}</p>
        </details>
      ))}
    </div>
  );
}

export default PublicFaq;
