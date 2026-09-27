// 介面動作用的小型描邊圖示（主題切換、選單、顯示密碼、登出…）。
//
// 與 shared/LineIcons 同一套線條語言（24 格、currentColor、線寬 1.7），
// 但這組是「操作」而非「概念」圖示，尺寸由使用處 CSS 控制。
// 登入頁（features/auth）與會員區（features/account）共用，故放 shared/。

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  focusable: "false",
};

export function SunIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.8v2.1M12 19.1v2.1M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M2.8 12h2.1M19.1 12h2.1M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5" />
    </svg>
  );
}

export function MoonIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M20.2 14.6A8.4 8.4 0 019.4 3.8a8.4 8.4 0 1010.8 10.8z" />
    </svg>
  );
}

export function MenuIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 7h16M4 12h16M4 17h10" />
    </svg>
  );
}

export function CloseIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function PlusIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function ArrowRightIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export function ArrowLeftIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M19 12H5M11 6l-6 6 6 6" />
    </svg>
  );
}

export function CheckIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M5 12.5l4.2 4.2L19 7" />
    </svg>
  );
}

export function LogoutIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M14 4h4.2a1.8 1.8 0 011.8 1.8v12.4a1.8 1.8 0 01-1.8 1.8H14" />
      <path d="M10 16l-4-4 4-4M6 12h9.5" />
    </svg>
  );
}

export function EyeOpenIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function EyeOffIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 4l16 16" />
      <path d="M9.9 5.8A9.6 9.6 0 0112 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 01-2.9 3.7M6.6 7.4A16.5 16.5 0 002.5 12s3.5 6.5 9.5 6.5a9 9 0 004.1-1" />
      <path d="M9.9 9.9a3 3 0 004.2 4.2" />
    </svg>
  );
}

export function DownloadIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 4v11M7 10.5l5 5 5-5M5 20h14" />
    </svg>
  );
}

export function ShieldAdminIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3l7.5 3v5.6c0 4.4-3.1 8.2-7.5 9.4-4.4-1.2-7.5-5-7.5-9.4V6z" />
      <path d="M9 12l2.1 2.1L15.2 10" />
    </svg>
  );
}

export function AlertIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3.5l9.5 16.5h-19z" />
      <path d="M12 10v4.2M12 17.2v.1" />
    </svg>
  );
}

export function RefreshIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M20 12a8 8 0 11-2.3-5.6M20 4.5v4.2h-4.2" />
    </svg>
  );
}
