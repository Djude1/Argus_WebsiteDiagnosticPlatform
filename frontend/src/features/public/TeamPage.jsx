import { useEffect, useState } from "react";

import { api } from "../../api";
import { PublicHero, PublicSection } from "../../components/public/PublicHero";
import { CodeIcon, FlagIcon, LayersIcon } from "../../shared/LineIcons";
import { PROJECT_PLATFORM_STATS } from "./platformStats";

// 頭像：CMS 的 avatar_emoji 在各作業系統長相不一，改用姓名首字的字標，
// 色彩依成員順序輪替五個維度色，讓每張卡有辨識度又不脫離品牌色盤。
const AVATAR_TONES = ["geo", "seo", "ux", "aeo", "security"];

function statValue(label) {
  return PROJECT_PLATFORM_STATS.find((s) => s.label === label)?.value ?? "—";
}

function GitHubIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.4-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  );
}

function TeamMemberCard({ member, index }) {
  const m = member;
  const initial = (m.name || "?").trim().charAt(0);
  return (
    <article className={`team-card cat-${AVATAR_TONES[index % AVATAR_TONES.length]}`}>
      <header className="team-card-head">
        <span className="team-avatar" aria-hidden="true">{initial}</span>
        <div className="team-card-meta">
          <h3 className="team-name">{m.name}</h3>
          <div className="team-role">{m.role}</div>
        </div>
      </header>
      {m.bio && <p className="team-bio">{m.bio}</p>}

      {Array.isArray(m.skill_levels) && m.skill_levels.length > 0 && (
        <div className="team-block">
          <div className="team-block-label"><LayersIcon />技能熟練度</div>
          <ul className="team-skill-bars">
            {m.skill_levels.map((s) => {
              const level = Math.max(0, Math.min(100, s.level));
              return (
                <li key={s.name} className="team-skill-row">
                  <div className="team-skill-row-head">
                    <span>{s.name}</span>
                    <span className="team-skill-pct ag-num">{s.level}%</span>
                  </div>
                  <div className="team-skill-track" aria-hidden="true">
                    <div className="team-skill-fill" style={{ width: `${level}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {Array.isArray(m.contributions) && m.contributions.length > 0 && (
        <div className="team-block">
          <div className="team-block-label"><FlagIcon />負責項目</div>
          <ul className="team-contrib-list">
            {m.contributions.map((c, i) => (
              <li key={i}>
                <div className="team-contrib-title">{c.title}</div>
                {c.desc && <div className="team-contrib-desc">{c.desc}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {Array.isArray(m.skills) && m.skills.length > 0 && (
        <div className="team-block">
          <div className="team-block-label"><CodeIcon />技術棧</div>
          <div className="team-chips">
            {m.skills.map((s) => (
              <span key={s} className="team-chip">{s}</span>
            ))}
          </div>
        </div>
      )}

      {m.github_url && (
        <a className="team-github" href={m.github_url} target="_blank" rel="noopener noreferrer">
          <GitHubIcon />
          GitHub
          <span className="sr-only">（{m.name}，另開新視窗）</span>
        </a>
      )}
    </article>
  );
}

export function TeamPage() {
  const [members, setMembers] = useState([]);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    api.get("/content/team/")
      .then((r) => setMembers(r.data.members || []))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const stats = [
    { value: loaded ? String(members.length) : "—", label: "核心成員" },
    { value: statValue("Django Apps"), label: "Django apps" },
    { value: statValue("自動化測試"), label: "自動化測試" },
  ];

  return (
    <div className="public-page">
      <PublicHero
        eyebrow="Team · 團隊"
        title={<>打造 Argus 的<em>團隊</em></>}
        aside={(
          <dl className="hero-stats">
            {stats.map((s) => (
              <div key={s.label} className="hero-stat">
                <dt className="hero-stat-label">{s.label}</dt>
                <dd className="hero-stat-value ag-num">{s.value}</dd>
              </div>
            ))}
          </dl>
        )}
      >
        <p>
          跨領域協作，從 Playwright 爬蟲、LLM Agent 到 UI 與 Docker／Kubernetes 部署，一手包辦。
        </p>
      </PublicHero>

      <PublicSection eyebrow="Members" title="成員與分工" description="每個人負責的模組與主要技術。">
        {!loaded ? (
          <div className="team-grid" aria-busy="true">
            {[0, 1].map((i) => <div key={i} className="team-card is-skeleton" />)}
          </div>
        ) : members.length > 0 ? (
          <div className="team-grid">
            {members.map((m, i) => (
              <TeamMemberCard key={m.id} member={m} index={i} />
            ))}
          </div>
        ) : (
          <p className="public-empty">尚未設定團隊成員。</p>
        )}
      </PublicSection>
    </div>
  );
}

export default TeamPage;
