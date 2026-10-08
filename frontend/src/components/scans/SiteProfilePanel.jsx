import { CheckCircleIcon, GlobeIcon } from "../../shared/LineIcons";

const CATEGORY_LABELS = { seo: "SEO", aeo: "AEO", geo: "GEO", ux: "UX", security: "資安" };

// 掃描結果的「網站概況」（後端 ScanJob.site_profile，apps/scans/site_profile.py）。
// 2026-10-06 起拆成掃描頁上方導覽的兩個分頁：「網站優勢」與「網站架構」；
// 報告分頁只留一行 CDN／反向代理提醒。舊掃描沒有這個欄位就不顯示。

function edgeSummary(infra) {
  const edge = infra?.edge;
  if (edge) return `流量先經過 ${edge.provider}（CDN／反向代理），掃描到的是它的邊緣節點`;
  if (infra?.scan_target === "origin") return "直接連到網站主機，未偵測到 CDN／反向代理";
  return "無法判斷是否經過 CDN／反向代理";
}

function addressSummary(addresses) {
  if (!addresses?.length) return "";
  const networks = [...new Set(addresses.map((a) => a.network).filter(Boolean))];
  if (networks.length === 1 && addresses.every((a) => a.network)) {
    return `${addresses.length} 個 IP，皆屬 ${networks[0]} 網段`;
  }
  return `${addresses.length} 個 IP`;
}

/** 報告分頁頂端的一行提醒：位於 CDN 之後時，Port／主機層級資訊反映的是邊緣節點。 */
function EdgeNotice({ profile }) {
  const notice = profile?.infrastructure?.notice;
  return notice ? <p className="site-profile-notice">{notice}</p> : null;
}

/** 「網站優勢」分頁：每一項附量到的依據；由間接訊號推論的標「推論」。 */
function SiteStrengths({ profile }) {
  const strengths = profile?.strengths || [];
  if (!strengths.length) {
    return (
      <section className="panel">
        <p className="hint-text">
          這次掃描沒有可列為優勢的項目，或這是較早的掃描（重新掃描後會顯示）。
        </p>
      </section>
    );
  }
  return (
    <section className="panel site-profile-block">
      <h2 className="site-profile-title">
        <CheckCircleIcon aria-hidden="true" /> 網站優勢
        <span className="site-profile-count">{strengths.length} 項</span>
      </h2>
      <p className="site-profile-lead">本次掃描量到、已經設定正確的項目。每一項都附上判斷依據，可自行核對。</p>
      <ul className="site-strengths">
        {strengths.map((item) => (
          <li key={item.key}>
            <span className="site-strength-name">{item.title}</span>
            <span className={`category-pill cat-${item.category}`}>
              {CATEGORY_LABELS[item.category] || item.category}
            </span>
            {item.confidence === "likely" && (
              <span className="site-strength-likely" title="由間接訊號推論，不是直接量到的設定">
                推論
              </span>
            )}
            <p className="site-strength-detail">{item.detail}</p>
            {item.evidence && <p className="site-strength-evidence">依據：{item.evidence}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** 「網站架構」分頁上半部：一句話說明流量路徑、使用的技術；IP 等細節收在「詳細資料」。 */
function gradeTone(grade) {
  if (grade.startsWith("A")) return "good";
  if (grade.startsWith("B") || grade.startsWith("C")) return "warn";
  return "bad";
}

function formatModifier(value) {
  if (value > 0) return `+${value}`;
  return value === 0 ? "0" : String(value);
}

// 安全標頭參考等第（後端 security/observatory.py）：依 Mozilla HTTP Observatory 公開規則離線計算，
// 非官方結果、不計入 Argus 分數
function ObservatoryGrade({ observatory }) {
  if (!observatory?.grade) return null;
  return (
    <div className="site-observatory">
      <h3 className="site-tech-title">安全標頭等第</h3>
      <p className="site-observatory-summary">
        <span className={`site-observatory-grade is-${gradeTone(observatory.grade)}`}>{observatory.grade}</span>
        <span>{observatory.score} 分（滿分 100，部分項目可加分）</span>
      </p>
      <table className="site-observatory-tests">
        <thead>
          <tr>
            <th scope="col">項目</th>
            <th scope="col">結果</th>
            <th scope="col">加減分</th>
          </tr>
        </thead>
        <tbody>
          {observatory.tests.map((test) => (
            <tr key={test.key}>
              <td>{test.label}</td>
              <td>{test.evaluated ? test.result : `未評估：${test.result}`}</td>
              <td>{test.evaluated ? formatModifier(test.modifier) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="site-strength-evidence">
        依 Mozilla HTTP Observatory 公開的評分規則，用這次掃描取得的首頁回應計算；不是 Observatory 官方結果，
        也不計入 Argus 分數。加分項目只在扣分後仍有 90 分以上時計入。
      </p>
    </div>
  );
}

const AI_PURPOSES = [
  ["search", "AI 搜尋與回答", "封鎖後，這些服務的回答比較不會引用、連結你的網站。"],
  ["user", "使用者觸發讀取", "使用者在對話中要求讀取網頁時才發出；依廠商說明不一定遵守 robots.txt。"],
  ["training", "模型訓練", "封鎖是正當的商業選擇，不影響這些公司的搜尋與 AI 回答引用。"],
];
const AI_STATUS = {
  allowed: ["允許", "good"],
  partial: ["部分限制", "warn"],
  blocked: ["封鎖", "bad"],
};

// AI 爬蟲的 robots.txt 政策（後端 ai_bots.py）：依用途分組，讓網站主看清楚封鎖的取捨
function AiBotPolicy({ policy }) {
  if (!policy?.bots?.length) return null;
  return (
    <div className="site-observatory">
      <h3 className="site-tech-title">AI 爬蟲政策</h3>
      {!policy.robots_found && (
        <p className="site-strength-evidence">網站沒有 robots.txt，所有 AI 爬蟲都可以抓取。</p>
      )}
      {AI_PURPOSES.map(([purpose, label, hint]) => {
        const bots = policy.bots.filter((bot) => bot.purpose === purpose);
        if (!bots.length) return null;
        return (
          <div key={purpose} className="site-ai-group">
            <h4 className="site-ai-group-title">{label}</h4>
            <p className="site-strength-evidence">{hint}</p>
            <ul className="site-ai-bots">
              {bots.map((bot) => {
                const [statusLabel, tone] = AI_STATUS[bot.status] || ["—", "none"];
                return (
                  <li key={bot.agent}>
                    <span className="site-ai-name">
                      {bot.agent}
                      <span className="site-profile-sub">{bot.vendor}{bot.note ? `・${bot.note}` : ""}</span>
                    </span>
                    <span className={`site-ai-status is-${tone}`}>{statusLabel}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function SiteArchitecture({ profile }) {
  const infra = profile?.infrastructure;
  const technologies = profile?.technologies || [];
  if (!infra?.hostname && !technologies.length) {
    return (
      <section className="panel">
        <p className="hint-text">這是較早的掃描，沒有網站架構資料；重新掃描後會顯示。</p>
      </section>
    );
  }
  const byCategory = technologies.reduce((groups, tech) => {
    (groups[tech.category] = groups[tech.category] || []).push(tech);
    return groups;
  }, {});

  return (
    <section className="panel site-profile-block">
      <h2 className="site-profile-title">
        <GlobeIcon aria-hidden="true" /> 網站架構
      </h2>
      {infra?.hostname && (
        <>
          <p className="site-profile-lead">
            <strong>{infra.hostname}</strong>：{edgeSummary(infra)}
            {infra.addresses?.length > 0 && `（${addressSummary(infra.addresses)}）`}。
          </p>
          {infra.notice && <p className="site-profile-notice">{infra.notice}</p>}
        </>
      )}
      {technologies.length > 0 && (
        <div className="site-tech">
          <h3 className="site-tech-title">使用的技術</h3>
          <dl className="site-tech-groups">
            {Object.entries(byCategory).map(([category, items]) => (
              <div key={category}>
                <dt>{category}</dt>
                <dd>
                  {items.map((tech) => (
                    <span key={tech.name} className="site-tech-chip" title={`依據：${tech.evidence}`}>
                      {tech.name}
                    </span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
          <p className="site-strength-evidence">只依首頁 HTML 與回應標頭判斷，滑過名稱可看依據；看不出來的不列。</p>
        </div>
      )}
      <ObservatoryGrade observatory={profile?.observatory} />
      <AiBotPolicy policy={profile?.ai_bots} />
      {infra?.hostname && (
        <details className="site-profile-details">
          <summary>詳細資料（IP、反解、DNS）</summary>
          <dl className="site-profile-facts">
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
          {infra.edge?.evidence?.length > 0 && (
            <p className="site-strength-evidence">判斷依據：{infra.edge.evidence.join("；")}</p>
          )}
        </details>
      )}
    </section>
  );
}

export { EdgeNotice, ObservatoryGrade, SiteArchitecture, SiteStrengths };
