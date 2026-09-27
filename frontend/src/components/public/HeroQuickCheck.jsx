import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { GlobeIcon } from "../../shared/LineIcons";

// 首頁 hero 的主要動作：輸入網址 → 帶到 /free-tools 的單頁檢查並預填網址。
// 不在這裡直接呼叫 API：快速檢查需要使用者勾選授權聲明，那一步留在工具頁完成。

export function HeroQuickCheck() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const submit = (event) => {
    event.preventDefault();
    const trimmed = url.trim();
    navigate(trimmed ? `/free-tools?url=${encodeURIComponent(trimmed)}` : "/free-tools");
  };
  return (
    <div className="home-quick">
      <form className="home-quick-form" onSubmit={submit} role="search" aria-label="快速檢查網站">
        <label className="home-quick-field">
          <span className="sr-only">要檢查的網址</span>
          <GlobeIcon className="home-quick-icon" />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://your-site.com"
            inputMode="url"
            autoComplete="url"
            spellCheck={false}
          />
        </label>
        <button type="submit" className="public-cta public-cta-primary home-quick-submit">
          免費快速檢查
        </button>
      </form>
      <ul className="home-quick-notes">
        <li>免登入</li>
        <li>不扣點數</li>
        <li>即時出結果</li>
      </ul>
    </div>
  );
}

export default HeroQuickCheck;
