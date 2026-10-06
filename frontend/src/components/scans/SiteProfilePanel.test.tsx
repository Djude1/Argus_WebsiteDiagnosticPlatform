import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteProfilePanel } from "./SiteProfilePanel";

const PROFILE = {
  infrastructure: {
    hostname: "ntubimdbirc.tw",
    addresses: [{ ip: "104.21.4.142", version: 4, rdns: "", network: "Cloudflare" }],
    cname: [],
    nameservers: ["rob.ns.cloudflare.com"],
    edge: { provider: "Cloudflare", waf_capable: true, evidence: ["回應標頭：cf-ray"] },
    scan_target: "edge",
    notice: "目前掃描目標位於 Cloudflare Edge，而非直接掃描 Origin Server，因此部分 Port、服務或主機層級資訊可能受到 CDN／Reverse Proxy 架構影響。",
  },
  strengths: [
    { key: "hsts", category: "security", title: "已啟用 HSTS", detail: "瀏覽器會在 180 天內強制使用 HTTPS。" },
  ],
};

describe("SiteProfilePanel", () => {
  it("CDN 邊緣站顯示提醒、IP 網段與做得好的地方", () => {
    render(<SiteProfilePanel profile={PROFILE} />);
    expect(screen.getByText(/目前掃描目標位於 Cloudflare Edge/)).toBeInTheDocument();
    expect(screen.getByText("Cloudflare 邊緣節點（CDN／反向代理）")).toBeInTheDocument();
    expect(screen.getByText("104.21.4.142")).toBeInTheDocument();
    expect(screen.getByText(/Cloudflare 網段/)).toBeInTheDocument();
    expect(screen.getByText("已啟用 HSTS")).toBeInTheDocument();
  });

  it("舊掃描沒有網站概況時不顯示任何東西", () => {
    const { container } = render(<SiteProfilePanel profile={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
