import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EdgeNotice, SiteArchitecture, SiteStrengths } from "./SiteProfilePanel";

const NOTICE =
  "目前掃描目標位於 Cloudflare Edge，而非直接掃描 Origin Server，因此部分 Port、服務或主機層級資訊可能受到 CDN／Reverse Proxy 架構影響。";

const PROFILE = {
  infrastructure: {
    hostname: "ntubimdbirc.tw",
    addresses: [
      { ip: "104.21.4.142", version: 4, rdns: "", network: "Cloudflare" },
      { ip: "172.67.154.32", version: 4, rdns: "", network: "Cloudflare" },
    ],
    cname: [],
    nameservers: ["rob.ns.cloudflare.com"],
    edge: { provider: "Cloudflare", waf_capable: true, evidence: ["回應標頭：cf-ray"] },
    scan_target: "edge",
    notice: NOTICE,
  },
  strengths: [
    {
      key: "hsts",
      category: "security",
      title: "已啟用 HSTS",
      detail: "瀏覽器會在 180 天內強制使用 HTTPS。",
      evidence: "Strict-Transport-Security: max-age=15552000",
      confidence: "confirmed",
    },
    {
      key: "speed",
      category: "ux",
      title: "載入時間在合理範圍",
      detail: "實驗室量測。",
      evidence: "實驗室量測中位數 2400 ms",
      confidence: "likely",
    },
  ],
  technologies: [
    { name: "Next.js", category: "網站框架", evidence: "頁面含 /_next/static/" },
    { name: "Cloudflare", category: "伺服器與託管", evidence: "回應標頭 Server" },
  ],
};

describe("SiteProfilePanel", () => {
  it("報告分頁只留一行 CDN 提醒", () => {
    render(<EdgeNotice profile={PROFILE} />);
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
  });

  it("網站優勢附依據，推論項目另外標示", () => {
    render(<SiteStrengths profile={PROFILE} />);
    expect(screen.getByText("已啟用 HSTS")).toBeInTheDocument();
    expect(screen.getByText("依據：Strict-Transport-Security: max-age=15552000")).toBeInTheDocument();
    expect(screen.getAllByText("推論")).toHaveLength(1);
  });

  it("網站架構一句話說明流量路徑，列出使用的技術，IP 細節收在詳細資料", () => {
    render(<SiteArchitecture profile={PROFILE} />);
    expect(screen.getByText(/流量先經過 Cloudflare/)).toBeInTheDocument();
    expect(screen.getByText(/2 個 IP，皆屬 Cloudflare 網段/)).toBeInTheDocument();
    expect(screen.getByText("Next.js")).toBeInTheDocument();
    expect(screen.getByText("詳細資料（IP、反解、DNS）")).toBeInTheDocument();
  });

  it("安全標頭等第附分數、逐項加減分，未評估的項目不顯示分數，並註明非官方", () => {
    const observatory = {
      grade: "C-",
      score: 45,
      tests: [
        { key: "csp", label: "Content Security Policy", modifier: -25, result: "沒有設定 CSP", evaluated: true },
        { key: "redirection", label: "HTTP 轉址到 HTTPS", modifier: 0, result: "這次沒有檢查", evaluated: false },
      ],
    };
    render(<SiteArchitecture profile={{ ...PROFILE, observatory }} />);
    expect(screen.getByText("C-")).toBeInTheDocument();
    expect(screen.getByText(/45 分/)).toBeInTheDocument();
    expect(screen.getByText("-25")).toBeInTheDocument();
    expect(screen.getByText("未評估：這次沒有檢查")).toBeInTheDocument();
    expect(screen.getByText(/不是 Observatory 官方結果/)).toBeInTheDocument();
  });

  it("AI 爬蟲政策依用途分組，狀態附文字並說明訓練封鎖不影響搜尋", () => {
    const ai_bots = {
      robots_found: true,
      bots: [
        { agent: "GPTBot", vendor: "OpenAI", purpose: "training", note: "", status: "blocked", explicit: true },
        { agent: "OAI-SearchBot", vendor: "OpenAI", purpose: "search", note: "ChatGPT 搜尋", status: "allowed", explicit: false },
      ],
    };
    render(<SiteArchitecture profile={{ ...PROFILE, ai_bots }} />);
    expect(screen.getByText("AI 爬蟲政策")).toBeInTheDocument();
    expect(screen.getByText("模型訓練")).toBeInTheDocument();
    expect(screen.getByText("封鎖")).toBeInTheDocument();
    expect(screen.getByText("允許")).toBeInTheDocument();
    expect(screen.getByText(/不影響這些公司的搜尋與 AI 回答引用/)).toBeInTheDocument();
  });

  it("舊掃描沒有網站概況時給說明而不是空白", () => {
    render(<SiteStrengths profile={{}} />);
    expect(screen.getByText(/較早的掃描/)).toBeInTheDocument();
    const { container } = render(<EdgeNotice profile={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
