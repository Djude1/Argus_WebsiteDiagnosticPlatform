import { useCallback, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { api } from "../../api";
import { copyToClipboard } from "../../shared/clipboard";

// 掃描來源說明（/scanner）：給「被掃描的網站」的管理者看，說明 Argus 的流量怎麼辨識、會做什麼、
// 如何放行或封鎖（roadmap §6 第 3 項）。User-Agent、出口 IP 與速率都由後端依實際生效的設定回傳
// （/api/content/scanner-info/），不要在這裡寫死，否則說明會和行為不一致。

function CopyLine({ label, text }) {
  const [state, setState] = useState("");
  return (
    <div className="scanner-copy">
      <code>{text}</code>
      <button
        type="button"
        className="scanner-copy-button"
        onClick={async () => setState((await copyToClipboard(text)) ? "已複製" : "複製失敗，請手動選取")}
        aria-label={`複製${label}`}
      >
        {state || "複製"}
      </button>
    </div>
  );
}

function ScannerInfoPage() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    api
      .get("/content/scanner-info/")
      .then((res) => setInfo(res.data))
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="public-page legal-page">
      <section className="public-hero legal-hero">
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">SCANNER · 掃描來源說明</span>
          <h1 className="public-hero-title">Argus 掃描流量說明</h1>
          <p className="public-hero-sub">
            如果你在網站紀錄裡看到 Argus 的請求，這頁說明它是誰、會做什麼，以及如何放行或封鎖。
          </p>
        </div>
      </section>
      <article className="legal-body">
        {error && (
          <div className="scanner-error" role="alert">
            <p>暫時無法讀取掃描設定。</p>
            <button type="button" className="scanner-copy-button" onClick={load}>
              重新載入
            </button>
          </div>
        )}
        {!info && !error && <p>讀取中…</p>}
        {info && (
          <>
            <section>
              <h2>1. 如何辨識</h2>
              <h3>User-Agent</h3>
              <p>Argus 的網頁走訪、連結檢查、弱點掃描與驗證工具都使用同一個 User-Agent：</p>
              <CopyLine label="User-Agent" text={info.user_agent} />
              <h3>來源 IP</h3>
              {info.egress_ips.length > 0 ? (
                <>
                  <p>掃描流量從以下位址送出：</p>
                  <ul>
                    {info.egress_ips.map((ip) => (
                      <li key={ip}>
                        <code>{ip}</code>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p>目前沒有公布固定的出口 IP，請以 User-Agent 辨識。</p>
              )}
              <p>
                User-Agent 可以被他人冒用。若需要確認某次請求是否真的來自 Argus，請透過
                <NavLink to="/partners">聯絡我們</NavLink>提供請求時間與紀錄。
              </p>
            </section>

            <section>
              <h2>2. 什麼時候會造訪你的網站</h2>
              <p>只有在 Argus 使用者對你的網站建立檢查時才會造訪，不會自行巡航網際網路。</p>
              <h3>一般檢查（被動）</h3>
              <ul>
                <li>以瀏覽器開啟公開頁面，像一般訪客一樣讀取內容，每秒最多 {info.passive_pages_per_second} 頁。</li>
                <li>讀取 robots.txt 與 sitemap，並逐一確認頁面上的連結是否有效（連到其他網站的連結也會收到一次請求）。</li>
                <li>不嘗試任何攻擊。</li>
                <li>
                  使用者選擇「使用體驗」檢查時，AI 會像真人一樣點擊按鈕、在表單填入示意資料；只有網域擁有者驗證過的網站才會實際送出表單。
                </li>
              </ul>
              <h3>主動測試</h3>
              <ul>
                <li>
                  已知漏洞模板掃描、敏感檔案路徑探測與資料庫注入驗證，只在使用者證明擁有該網域（Google Search
                  Console、DNS、首頁標籤或驗證檔）並勾選授權後才會執行。
                </li>
                <li>
                  漏洞模板掃描與敏感檔案路徑探測合計每秒最多 {info.active_requests_per_second} 個請求，漏洞模板只使用已知被實際利用的漏洞檢查，不含阻斷服務、模糊測試或帳號密碼暴力破解類的模板。
                </li>
              </ul>
              <h3>免費快速檢查</h3>
              <ul>
                <li>任何人都可以在公開頁對單一網址做一次輕量檢查或測速：一般 HTTP 請求，不開瀏覽器、不跟隨站內連結。</li>
              </ul>
            </section>

            <section>
              <h2>3. 如何封鎖或限制</h2>
              <h3>robots.txt</h3>
              <p>在 robots.txt 加入以下規則，Argus 的網頁走訪就會略過這些路徑：</p>
              <CopyLine label="robots.txt 規則" text={`User-agent: ${info.robots_token}\nDisallow: /`} />
              <p>
                robots.txt 只影響網頁走訪；連結有效性確認，以及網域擁有者自己授權的主動測試，不受 robots.txt 限制。
              </p>
              <h3>防火牆或 WAF</h3>
              <p>
                依上方的 User-Agent{info.egress_ips.length > 0 ? " 或來源 IP" : ""}設定封鎖規則即可。被封鎖時，Argus
                的報告會標示「被阻擋」，不會把它當成網站沒有問題。
              </p>
            </section>

            <section>
              <h2>4. 網站擁有者想完整檢查自己的網站</h2>
              <p>
                如果你的網站有 WAF、機器人防護或流量限制，請暫時放行上方的 User-Agent
                {info.egress_ips.length > 0 ? " 或來源 IP" : ""}
                。沒有放行時，部分頁面或檢查可能被擋下，報告會標示為部分完成。
              </p>
            </section>

            <section>
              <h2>5. 聯絡我們</h2>
              <p>
                對 Argus 的掃描流量有任何疑問或要回報異常，請透過<NavLink to="/partners">聯絡我們</NavLink>頁面與我們聯繫。
              </p>
            </section>
          </>
        )}
      </article>
    </div>
  );
}

export { ScannerInfoPage };
