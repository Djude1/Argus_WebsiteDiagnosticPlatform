import { CheckCircleIcon, GlobeIcon } from "../../shared/LineIcons";

const CATEGORY_LABELS = { seo: "SEO", aeo: "AEO", geo: "GEO", ux: "UX", security: "資安" };

// 掃描結果的「網站概況」：基礎架構（網域 → IP → 反解 → CDN 邊緣）與網站做得好的地方。
// 資料來自後端 ScanJob.site_profile（apps/scans/site_profile.py）；舊掃描沒有這個欄位就不顯示。
function SiteProfilePanel({ profile }) {
  const infra = profile?.infrastructure;
  const strengths = profile?.strengths || [];
  if (!infra && !strengths.length) return null;
  const edge = infra?.edge;
  const target = edge
    ? `${edge.provider} 邊緣節點（CDN／反向代理）`
    : infra?.scan_target === "origin"
      ? "網站主機（未偵測到 CDN／反向代理）"
      : "無法判斷";

  return (
    <div className="site-profile">
      {infra?.hostname && (
        <section className="panel site-profile-block">
          <h2 className="site-profile-title">
            <GlobeIcon aria-hidden="true" /> 網站架構
          </h2>
          {infra.notice && <p className="site-profile-notice">{infra.notice}</p>}
          <dl className="site-profile-facts">
            <div>
              <dt>網域</dt>
              <dd>{infra.hostname}</dd>
            </div>
            <div>
              <dt>實際掃描到</dt>
              <dd>{target}</dd>
            </div>
            {infra.addresses?.length > 0 && (
              <div>
                <dt>IP 與反解</dt>
                <dd>
                  <ul className="site-profile-ips">
                    {infra.addresses.map((address) => (
                      <li key={address.ip}>
                        <code>{address.ip}</code>
                        <span className="site-profile-sub">
                          {[address.network && `${address.network} 網段`, address.rdns || "無反解"]
                            .filter(Boolean)
                            .join("・")}
                        </span>
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
            {infra.cname?.length > 0 && (
              <div>
                <dt>CNAME</dt>
                <dd>{infra.cname.join("、")}</dd>
              </div>
            )}
            {infra.nameservers?.length > 0 && (
              <div>
                <dt>DNS 代管</dt>
                <dd>{infra.nameservers.join("、")}</dd>
              </div>
            )}
          </dl>
          {edge?.evidence?.length > 0 && (
            <p className="site-profile-evidence">判斷依據：{edge.evidence.join("；")}</p>
          )}
        </section>
      )}
      {strengths.length > 0 && (
        <section className="panel site-profile-block">
          <h2 className="site-profile-title">
            <CheckCircleIcon aria-hidden="true" /> 做得好的地方
          </h2>
          <ul className="site-strengths">
            {strengths.map((item) => (
              <li key={item.key}>
                <span className="site-strength-name">{item.title}</span>
                <span className={`category-pill cat-${item.category}`}>
                  {CATEGORY_LABELS[item.category] || item.category}
                </span>
                <p className="site-strength-detail">{item.detail}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default SiteProfilePanel;
export { SiteProfilePanel };
