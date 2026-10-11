import { useEffect, useRef, useState } from "react";
import { copyToClipboard } from "../../shared/clipboard";

const FEEDBACK_MS = 2000;

// 複製按鈕：按下有縮放回饋，複製後 2 秒顯示「已複製」或「複製失敗」（2026-10-11）
type CopyButtonProps = {
  text: string | null | undefined;
  label: string;
  className?: string;
  title?: string;
};

export function CopyButton({ text, label, className = "", title }: CopyButtonProps) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy() {
    const ok = await copyToClipboard(text || "");
    setState(ok ? "copied" : "failed");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), FEEDBACK_MS);
  }

  const shown = state === "copied" ? "已複製" : state === "failed" ? "複製失敗" : label;
  return (
    <button
      className={`secondary-button copy-feedback-button ${className}`.trim()}
      type="button"
      data-state={state}
      onClick={copy}
      title={title}
    >
      <span aria-live="polite">{shown}</span>
    </button>
  );
}
