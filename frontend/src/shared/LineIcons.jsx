// 全站共用的雙色調圖示。
//
// 不是純單線：主體形狀帶 .ln-fill（currentColor 半透明填色），描邊維持亮色，
// 外層再由使用處加 drop-shadow 光暈。純 1.6px 單線在放大時顯得單薄，
// 這個做法保留線性風格但給了深度——與設計稿的圖示語言一致。
//
// 全部用 currentColor 描邊，顏色由外層的強調色決定——每個節點有自己的色系
// （cyan／teal／amber／violet），圖示不該各自寫死顏色。
// 線寬統一 1.6，視覺重量一致；尺寸由 CSS 控制，這裡不寫死 width/height。
//
// 沿革：最初只服務首頁鏈路圖（PipelineIcons）→ 安全邊界與核心功能也改用
// （PublicIcons）→ 登入後導覽列也改用，已跨 public 與 account 兩個 domain，
// 依分層規則移入 shared/。
//
// 全站不再使用 emoji 當圖示：emoji 在不同作業系統長相不一（Windows 的 🏠
// 與 macOS 差很多），大小與基線也對不齊，與描邊風格並置更顯廉價。

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

export function ShieldIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M12 3l7 3v5.5c0 4.2-2.9 7.9-7 9.5-4.1-1.6-7-5.3-7-9.5V6l7-3z" />
      <path d="M8.8 12.2l2.2 2.2 4.2-4.4" />
    </svg>
  );
}

export function BrowserIcon(props) {
  return (
    <svg {...base} {...props}>
      <rect className="ln-fill" x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M3 8.5h18" />
      <path d="M10.4 12.4L8.6 14.2l1.8 1.8M13.6 12.4l1.8 1.8-1.8 1.8" />
    </svg>
  );
}

export function RulesIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M7 3h7l4 4v14a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z" />
      <path d="M14 3v4h4" />
      <path d="M9 12h6M9 15.5h6M9 19h3.5" />
    </svg>
  );
}

export function TargetIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle className="ln-fill" cx="12" cy="12" r="8.2" />
      <circle cx="12" cy="12" r="3.6" />
      <path d="M12 1.6v3.2M12 19.2v3.2M1.6 12h3.2M19.2 12h3.2" />
    </svg>
  );
}

export function RobotIcon(props) {
  return (
    <svg {...base} {...props}>
      <rect className="ln-fill" x="4" y="8" width="16" height="11" rx="3" />
      <path d="M12 4.2V8M9.5 13h.01M14.5 13h.01" />
      <circle cx="12" cy="3.4" r="1.2" />
      <path d="M2.6 12.5v2.6M21.4 12.5v2.6" />
    </svg>
  );
}

export function LayersIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M12 3.2l8.4 4.2-8.4 4.2-8.4-4.2 8.4-4.2z" />
      <path d="M3.6 12l8.4 4.2 8.4-4.2" />
      <path d="M3.6 16.4l8.4 4.2 8.4-4.2" />
    </svg>
  );
}

export function MagnifierIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle className="ln-fill" cx="10.8" cy="10.8" r="6.8" />
      <path d="M15.8 15.8L21 21" />
      <path d="M8.2 10h5.2M8.2 12.6h3.4" />
    </svg>
  );
}

export function ScoreIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M6.5 3h11a1 1 0 011 1v16a1 1 0 01-1 1h-11a1 1 0 01-1-1V4a1 1 0 011-1z" />
      <path d="M8.8 7.6h6.4M8.8 11h4.2" />
      <path d="M13.6 14.2l1.1 2.2 2.4.35-1.75 1.7.42 2.4-2.17-1.14-2.17 1.14.42-2.4-1.75-1.7 2.4-.35 1.1-2.2z" />
    </svg>
  );
}

export function ImageIcon(props) {
  return (
    <svg {...base} {...props}>
      <rect className="ln-fill" x="3" y="4.5" width="18" height="15" rx="2.5" />
      <circle cx="8.6" cy="9.8" r="1.6" />
      <path d="M3.6 16.6l4.8-4.2 3.4 3 3-2.4 5.6 4.6" />
    </svg>
  );
}

export function DocIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M7 3h7l4 4v14a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z" />
      <path d="M14 3v4h4" />
      <path d="M9 13h6M9 16.5h4" />
    </svg>
  );
}

export function CodeIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M9 7.5L4.2 12 9 16.5M15 7.5L19.8 12 15 16.5" />
      <path d="M13.2 4.6l-2.4 14.8" />
    </svg>
  );
}

export function BrainIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M12 5.2a3 3 0 00-5.6 1.1 2.8 2.8 0 00-1.2 4.6A3 3 0 006.6 16a3 3 0 005.4 1.6z" />
      <path className="ln-fill" d="M12 5.2a3 3 0 015.6 1.1 2.8 2.8 0 011.2 4.6A3 3 0 0117.4 16a3 3 0 01-5.4 1.6z" />
      <path d="M12 5.2v12.4" />
    </svg>
  );
}

export function SparkIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M12 3.4l1.9 4.9 4.9 1.9-4.9 1.9L12 17l-1.9-4.9L5.2 10.2l4.9-1.9L12 3.4z" />
    </svg>
  );
}

export function ChevronIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M9.5 5.5L16 12l-6.5 6.5" />
    </svg>
  );
}


export function GlobeIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle className="ln-fill" cx="12" cy="12" r="8.6" />
      <path d="M3.4 12h17.2" />
      <path d="M12 3.4c2.2 2.4 3.3 5.4 3.3 8.6S14.2 18.2 12 20.6c-2.2-2.4-3.3-5.4-3.3-8.6S9.8 5.8 12 3.4z" />
    </svg>
  );
}

export function EyeIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M2.4 12s3.6-6.2 9.6-6.2S21.6 12 21.6 12s-3.6 6.2-9.6 6.2S2.4 12 2.4 12z" />
      <circle cx="12" cy="12" r="2.9" />
    </svg>
  );
}

export function LockIcon(props) {
  return (
    <svg {...base} {...props}>
      <rect className="ln-fill" x="4.6" y="10.4" width="14.8" height="10" rx="2.4" />
      <path d="M8.2 10.4V7.6a3.8 3.8 0 017.6 0v2.8" />
      <path d="M12 14.2v2.4" />
    </svg>
  );
}

export function SpiderIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle className="ln-fill" cx="12" cy="12" r="3.2" />
      <path d="M8.9 10.2L5.4 8M8.9 13.8L5.4 16M15.1 10.2L18.6 8M15.1 13.8L18.6 16" />
      <path d="M5.4 8V5M5.4 16v3M18.6 8V5M18.6 16v3" />
      <path d="M12 8.8V5.2M12 15.2v3.6" />
    </svg>
  );
}

export function ChartIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 19.4h16" />
      <path className="ln-fill" d="M5.6 13.2h2.4v6.2H5.6zM9.8 7.6h2.4v11.8H9.8zM14 10.8h2.4v8.6H14zM18.2 4.6h2.4v14.8h-2.4z" />
    </svg>
  );
}

export function CoinIcon(props) {
  return (
    <svg {...base} {...props}>
      <ellipse className="ln-fill" cx="12" cy="7.2" rx="7.4" ry="3.2" />
      <path d="M4.6 7.2v9.6c0 1.8 3.3 3.2 7.4 3.2s7.4-1.4 7.4-3.2V7.2" />
      <path d="M4.6 12c0 1.8 3.3 3.2 7.4 3.2s7.4-1.4 7.4-3.2" />
    </svg>
  );
}

export function FlagIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M6 20.4V4.2" />
      <path className="ln-fill" d="M6 5.2h10.4l-1.8 3.4 1.8 3.4H6z" />
    </svg>
  );
}


export function HomeIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M3.6 10.6L12 3.8l8.4 6.8" />
      <path d="M5.8 9.2v10.2a.8.8 0 00.8.8h10.8a.8.8 0 00.8-.8V9.2" />
      <path d="M9.8 20.2v-5.4h4.4v5.4" />
    </svg>
  );
}

export function ClockIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle className="ln-fill" cx="12" cy="12" r="8.4" />
      <path d="M12 7.2V12l3.2 1.9" />
    </svg>
  );
}

export function StarIcon(props) {
  return (
    <svg {...base} {...props}>
      <path className="ln-fill" d="M12 3.6l2.6 5.3 5.8.85-4.2 4.1 1 5.8L12 16.9l-5.2 2.75 1-5.8-4.2-4.1 5.8-.85L12 3.6z" />
    </svg>
  );
}

export function GearIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle className="ln-fill" cx="12" cy="12" r="3.1" />
      <path d="M19.1 14.4a1.6 1.6 0 00.32 1.76l.06.06a1.9 1.9 0 11-2.7 2.7l-.06-.06a1.6 1.6 0 00-1.76-.32 1.6 1.6 0 00-.97 1.46v.17a1.9 1.9 0 11-3.8 0v-.09a1.6 1.6 0 00-1.05-1.46 1.6 1.6 0 00-1.76.32l-.06.06a1.9 1.9 0 11-2.7-2.7l.06-.06a1.6 1.6 0 00.32-1.76 1.6 1.6 0 00-1.46-.97H3.3a1.9 1.9 0 110-3.8h.09a1.6 1.6 0 001.46-1.05 1.6 1.6 0 00-.32-1.76l-.06-.06a1.9 1.9 0 112.7-2.7l.06.06a1.6 1.6 0 001.76.32h.08a1.6 1.6 0 00.97-1.46V3.3a1.9 1.9 0 113.8 0v.09a1.6 1.6 0 00.97 1.46 1.6 1.6 0 001.76-.32l.06-.06a1.9 1.9 0 112.7 2.7l-.06.06a1.6 1.6 0 00-.32 1.76v.08a1.6 1.6 0 001.46.97h.17a1.9 1.9 0 110 3.8h-.09a1.6 1.6 0 00-1.46.97z" />
    </svg>
  );
}
