/**
 * 首頁動態的共用基礎（2026-10-09）：捲入畫面時淡入＋去模糊＋位移的 Reveal、
 * 滑鼠跟隨的卡片邊框光暈 useCardGlow、偏好減少動態的偵測。
 * 參考 TradingGoose 首頁的做法自行實作（不引入動畫套件）：每個元素只播一次，
 * 同一段落內以 delay 依序出現；偏好減少動態時直接顯示、不位移不模糊。
 * 樣式在 styles/73-public-refine.css 的 .hx-*。
 */
import { useEffect, useRef, useState } from "react";

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!media) return undefined;
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return reduced;
}

/** 元素第一次進入畫面時回傳 true（之後不再變回 false）。 */
export function useInViewOnce(ref, rootMargin = "0px 0px -10% 0px") {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || seen) return undefined;
    if (typeof IntersectionObserver === "undefined") {
      setSeen(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref, rootMargin, seen]);
  return seen;
}

/** 元素目前是否在畫面內（用來在看不到時暫停輪播與即時表格）。 */
export function useInView(ref) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver((entries) => {
      setVisible(entries.some((entry) => entry.isIntersecting));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);
  return visible;
}

const SLIDE = { up: [0, 50], down: [0, -50], left: [48, 0], right: [-48, 0], none: [0, 0] };

/**
 * 捲入畫面時出現：淡入、blur(10px)→0、位移 slide 方向的距離。
 * slide 是元素「從哪裡來」：down＝從上往下落、left＝從右往左滑入、right＝從左往右滑入。
 */
export function Reveal({ as: Tag = "div", delay = 0, slide = "down", duration = 0.5, className = "", children, ...rest }) {
  const ref = useRef(null);
  const shown = useInViewOnce(ref);
  const [x, y] = SLIDE[slide] || SLIDE.down;
  return (
    <Tag
      ref={ref}
      className={`hx-reveal${shown ? " is-shown" : ""}${className ? ` ${className}` : ""}`}
      style={{ "--rv-delay": `${delay}s`, "--rv-x": `${x}px`, "--rv-y": `${y}px`, "--rv-dur": `${duration}s` }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/**
 * 卡片邊框光暈：在 root 內所有 .hx-card 上寫入滑鼠相對位置。
 * --gx/--gy（px）給 1px 外框的光暈、--sx/--sy（%）給滑過時的內部光點；
 * 用 requestAnimationFrame 合併同一幀的多次移動。觸控裝置沒有 mousemove，自然不啟用。
 */
export function useCardGlow(rootRef) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    let frame = 0;
    let last = null;
    const paint = () => {
      frame = 0;
      if (!last) return;
      root.querySelectorAll(".hx-card").forEach((card) => {
        const rect = card.getBoundingClientRect();
        const gx = last.clientX - rect.left;
        const gy = last.clientY - rect.top;
        card.style.setProperty("--gx", `${gx}px`);
        card.style.setProperty("--gy", `${gy}px`);
        card.style.setProperty("--sx", `${(gx / rect.width) * 100}%`);
        card.style.setProperty("--sy", `${(gy / rect.height) * 100}%`);
      });
    };
    const onMove = (event) => {
      last = event;
      if (!frame) frame = requestAnimationFrame(paint);
    };
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [rootRef]);
}

/** 1px 光暈外框＋內容卡。className 加在內容卡上。 */
export function GlowCard({ className = "", children, as: Tag = "div", ...rest }) {
  return (
    <Tag className="hx-card" {...rest}>
      <div className={`hx-card-body${className ? ` ${className}` : ""}`}>{children}</div>
    </Tag>
  );
}
