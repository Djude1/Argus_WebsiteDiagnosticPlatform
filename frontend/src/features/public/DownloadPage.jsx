import { useEffect, useState } from "react";

import { api } from "../../api";
import { ArgusMark } from "../../components/brand/ArgusMark";
import { PublicHero, PublicSection } from "../../components/public/PublicHero";
import { useInstallPrompt } from "../../shared/AppShared";
import { formatDate } from "../../shared/formatters";

// 本頁專用的裝置圖示（LineIcons 沒有裝置類）；風格比照 LineIcons：
// currentColor 描邊 1.7、主體半透明填色。
const iconBase = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

function MonitorIcon() {
  return (
    <svg {...iconBase}>
      <rect className="ln-fill" x="3" y="4.5" width="18" height="12" rx="2" />
      <path d="M8.5 20h7M12 16.5V20" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg {...iconBase}>
      <rect className="ln-fill" x="6.5" y="2.8" width="11" height="18.4" rx="2.4" />
      <path d="M10.5 18h3" />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg {...iconBase}>
      <path className="ln-fill" d="M6 10.5h-.5A1.5 1.5 0 0 0 4 12v7a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 19v-7a1.5 1.5 0 0 0-1.5-1.5H18" />
      <path d="M12 14V3.5M8.5 7 12 3.5 15.5 7" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg {...iconBase} className="public-cta-icon">
      <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14" />
    </svg>
  );
}

const INSTALL_GUIDES = [
  {
    key: "desktop",
    Icon: MonitorIcon,
    title: "桌面",
    browser: "Chrome / Edge",
    steps: ["網址列右側點選「安裝」圖示", "點「安裝」即出現桌面捷徑"],
  },
  {
    key: "android",
    Icon: PhoneIcon,
    title: "Android",
    browser: "Chrome",
    steps: ["右上 ⋮ 選單 →「加到主畫面」", "確認後出現在主畫面"],
  },
  {
    key: "ios",
    Icon: ShareIcon,
    title: "iOS",
    browser: "Safari",
    steps: ["下方分享按鈕 →「加入主畫面」", "確認後出現在主畫面"],
  },
];

export function DownloadPage() {
  const [releases, setReleases] = useState([]);
  const { canInstall, installed, trigger } = useInstallPrompt();
  useEffect(() => {
    api.get("/content/releases/").then((r) => setReleases(r.data.releases || [])).catch(() => {});
  }, []);
  const latest = releases.find((r) => r.is_latest) || releases[0];
  const history = releases.filter((r) => r !== latest);

  return (
    <div className="public-page">
      <PublicHero
        eyebrow="Download · 下載安裝"
        title={<><em>隨身</em>使用 Argus</>}
        actions={(
          <>
            {installed ? (
              <span className="download-installed" role="status">
                <ArgusMark size={20} />
                已安裝，請從主畫面開啟
              </span>
            ) : (
              <button
                type="button"
                className="public-cta public-cta-primary"
                onClick={async () => {
                  if (canInstall) {
                    await trigger();
                  } else {
                    // 瀏覽器尚未提供安裝（如 iOS Safari 不支援程式化安裝，或事件未就緒）
                    // → 帶到各平台安裝步驟
                    document
                      .getElementById("install-guide")
                      ?.scrollIntoView({ behavior: "smooth" });
                  }
                }}
              >
                <DownloadIcon />
                點擊下載
              </button>
            )}
            {!installed && latest?.download_url && (
              <a className="public-cta public-cta-ghost" href={latest.download_url}>
                取得 {latest.platform_label} 版 →
              </a>
            )}
          </>
        )}
      >
        <p>
          Argus 是 PWA（漸進式網頁應用），無需透過 App Store——直接從瀏覽器加到主畫面，像 App 一樣開啟，支援離線瀏覽既有報告。
        </p>
      </PublicHero>

      <PublicSection id="install-guide" eyebrow="Install" title="安裝步驟" description="三大平台，兩步完成。">
        <ul className="install-grid">
          {INSTALL_GUIDES.map(({ key, Icon, title, browser, steps }) => (
            <li className="install-card" key={key}>
              <div className="install-card-head">
                <span className="install-card-icon"><Icon /></span>
                <span>
                  <h3 className="install-card-title">{title}</h3>
                  <span className="install-card-browser">{browser}</span>
                </span>
              </div>
              <ol className="install-steps">
                {steps.map((step) => <li key={step}>{step}</li>)}
              </ol>
            </li>
          ))}
        </ul>
      </PublicSection>

      {latest && (
        <PublicSection
          eyebrow="Release"
          title="版本資訊"
          description={`最新版 ${latest.version}（${latest.platform_label}）`}
        >
          <article className="release-card">
            <div className="release-card-head">
              <span className="release-badge">最新</span>
              <h3 className="release-version ag-num">v{latest.version}</h3>
              <time className="release-date" dateTime={latest.released_at}>{formatDate(latest.released_at)}</time>
            </div>
            <p className="release-notes">{latest.release_notes}</p>
            {latest.download_url && (
              <a className="public-cta public-cta-primary" href={latest.download_url}>
                <DownloadIcon />
                取得 {latest.platform_label}
              </a>
            )}
          </article>

          {history.length > 0 && (
            <details className="release-history">
              <summary>查看歷史版本（{history.length}）</summary>
              <ul>
                {history.map((r) => (
                  <li key={r.id}>
                    <strong className="ag-num">v{r.version}</strong>
                    <time dateTime={r.released_at}>{formatDate(r.released_at)}</time>
                    <span>{r.release_notes}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </PublicSection>
      )}
    </div>
  );
}

export default DownloadPage;
