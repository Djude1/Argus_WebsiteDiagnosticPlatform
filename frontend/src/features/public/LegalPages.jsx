import { NavLink } from "react-router-dom";

// 隱私權政策（/privacy）與服務條款（/terms）：公開頁，供使用者閱讀，也是 Google OAuth 同意畫面
// （Search Console 串接）要求填寫的公開連結。內容只寫系統實際收集與處理的資料；改了資料流程
// （新增第三方、改保存期限、改登入方式）要同步更新這裡與 EFFECTIVE_DATE。

const EFFECTIVE_DATE = "2026 年 10 月 4 日";

function LegalLayout({ eyebrow, title, intro, children }) {
  return (
    <div className="public-page legal-page">
      <section className="public-hero legal-hero">
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">{eyebrow}</span>
          <h1 className="public-hero-title">{title}</h1>
          <p className="public-hero-sub">{intro}</p>
          <p className="legal-date">生效日期：{EFFECTIVE_DATE}</p>
        </div>
      </section>
      <article className="legal-body">{children}</article>
    </div>
  );
}

function PrivacyPolicyPage() {
  return (
    <LegalLayout
      eyebrow="PRIVACY · 隱私權政策"
      title="Argus 隱私權政策"
      intro="說明 Argus AI網站健檢平台（以下稱「本服務」）收集哪些資料、為什麼收集、如何保存與保護，以及你可以行使的權利。"
    >
      <section>
        <h2>1. 我們收集的資料</h2>
        <h3>帳號資料</h3>
        <ul>
          <li>註冊一律透過 Google 帳號授權：Google 提供的 Email 與姓名；我們只驗證 Google 簽發的身分憑證，不會取得你的 Google 密碼。</li>
          <li>你設定的用戶名，以及經雜湊處理的 Argus 登入密碼（我們不保存密碼原文）。</li>
          <li>你自行上傳的大頭貼（會重新壓縮並移除照片中的拍攝資訊）。</li>
        </ul>
        <h3>使用紀錄</h3>
        <ul>
          <li>登入紀錄：登入時間、方式、IP 位址與瀏覽器資訊，用於帳號安全與異常登入調查。</li>
          <li>掃描授權紀錄：建立掃描時你同意的授權聲明、時間、IP 位址與瀏覽器資訊，作為「已取得網站授權」的稽核依據。</li>
        </ul>
        <h3>掃描資料</h3>
        <ul>
          <li>你提交的網址，以及掃描時從該網站取得的公開內容：頁面原始碼、回應標頭、截圖、連結與檢測結果。</li>
          <li>檢測結果中若出現個人資料（例如網站上公開的電話或 Email），在報告與介面中會遮罩後才顯示。</li>
        </ul>
        <h3>付款與發票</h3>
        <ul>
          <li>購點與訂閱訂單、每期扣款結果、金額與發票資訊（發票類型、載具或統一編號），用於入點與開立電子發票。信用卡等付款資料由綠界科技（ECPay）處理，本服務不會取得或保存卡號。</li>
        </ul>
        <h3>Google Search Console 資料（僅在你主動連接時）</h3>
        <ul>
          <li>你在 SEO 分析頁或網域驗證頁連接 Search Console 時，我們透過 Google OAuth 申請唯讀權限（<code>webmasters.readonly</code>），讀取你可存取的網站資源清單與權限等級（用來確認網域所有權），以及你所選擇的網站資源之搜尋成效（搜尋字詞、曝光、點擊、點閱率、平均排名與對應頁面）及網址檢查結果（是否已被 Google 收錄）。</li>
          <li>我們只保存加密後的長期授權憑證（refresh token）與你選擇的資源網址；搜尋成效資料只在你查看時向 Google 讀取，短暫快取（最長 1 小時）以減少重複請求，不另行永久保存。</li>
        </ul>
        <h3>Cookie 與瀏覽器儲存</h3>
        <ul>
          <li>登入狀態使用 HttpOnly Cookie；連接 Search Console 時使用一個 10 分鐘內有效的安全 Cookie 防止授權被冒用。</li>
          <li>介面偏好（日夜主題、目前選擇的網站專案）存在你的瀏覽器中，不會傳回伺服器。</li>
          <li>本服務不使用廣告追蹤或第三方行銷 Cookie。</li>
        </ul>
      </section>

      <section>
        <h2>2. 我們如何使用資料</h2>
        <ul>
          <li>提供與維運本服務：登入、執行掃描、產生報告、顯示 SEO 分析與點數結算。</li>
          <li>帳號與系統安全：防止濫用、異常登入調查與稽核。</li>
          <li>客服與服務通知：回覆你的詢問、寄送密碼重設信。</li>
        </ul>
        <p>我們不會出售你的個人資料，也不會將資料用於廣告投放。</p>
      </section>

      <section>
        <h2>3. Google 使用者資料的特別說明</h2>
        <p>
          Argus 對於從 Google API 取得之資訊的使用與傳輸，將遵守{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer">
            Google API 服務使用者資料政策
          </a>
          ，包括其中的「有限使用」（Limited Use）規定。具體而言：
        </p>
        <ul>
          <li>Search Console 資料只用來在本服務中向你本人顯示你網站的搜尋成效與收錄狀態，以及確認你是該網站在 Search Console 的擁有者（用於網域所有權驗證，開放主動式資安測試）。</li>
          <li>不會轉移或出售給第三方，不用於廣告，也不用於訓練任何人工智慧模型。</li>
          <li>除非取得你的明確同意、為了安全調查或法律要求，工作人員不會讀取這些資料。</li>
          <li>你可以隨時在 SEO 分析頁按「中斷連線」：我們會向 Google 撤銷授權並刪除保存的憑證；你也可以在 Google 帳號的「第三方存取權」頁面移除授權。</li>
        </ul>
      </section>

      <section>
        <h2>4. 與第三方的分享</h2>
        <ul>
          <li>Google：Google 帳號登入與 Search Console 串接（依你的操作）。</li>
          <li>Cloudflare：網站傳輸與人機驗證（Turnstile），用於阻擋自動化濫用。</li>
          <li>綠界科技（ECPay）：處理購點的信用卡付款與月訂閱的信用卡定期定額扣款。</li>
          <li>AI 模型服務：在你使用 AI 相關功能（例如修正產出或 AI 行為測試）時，相關的網站公開內容會傳送給我們使用的大型語言模型服務商處理，只用於產生該次結果。</li>
          <li>依法律要求或為保護本服務與使用者安全時，向主管機關提供必要資料。</li>
        </ul>
      </section>

      <section>
        <h2>5. 保存期限</h2>
        <ul>
          <li>帳號資料：保存至你刪除帳號為止；刪除後立即清除。</li>
          <li>掃描截圖：約 90 天後自動刪除；PDF 報告檔：約 180 天後刪除（報告編號的查驗紀錄會保留，讓已交付的報告仍可查驗）。</li>
          <li>付款、點數與稽核紀錄：依會計與法令要求保存。</li>
          <li>Search Console 授權憑證：保存至你中斷連線（SEO 分析頁或網域驗證頁）、刪除專案或刪除帳號為止。</li>
        </ul>
      </section>

      <section>
        <h2>6. 資料安全</h2>
        <p>
          全站使用 HTTPS 加密傳輸；密碼以雜湊方式保存；Search Console 授權憑證加密保存且不會回傳給瀏覽器；
          API 憑證只保存雜湊值；掃描目標會檢查是否為公開網址，避免被用來存取內部網路。
        </p>
      </section>

      <section>
        <h2>7. 你的權利</h2>
        <p>
          依個人資料保護法，你可以請求查詢、閱覽、複製、補充或更正、停止處理或刪除你的個人資料。
          帳號設定頁可以直接修改姓名、大頭貼與密碼，也可以<strong>自行永久刪除帳號</strong>：網站專案、掃描、報告與截圖、
          Search Console 連線（同時向 Google 撤銷授權）、網域驗證、MCP 憑證、評論與登入紀錄會立即刪除，並登出所有裝置；
          點數交易與購點訂單依會計法令只保留不含個人資料的金額與時間。其他請求請透過
          <NavLink to="/partners">聯絡我們</NavLink>
          頁面提出，我們會在確認身分後處理。
        </p>
      </section>

      <section>
        <h2>8. 政策更新</h2>
        <p>本政策若有重大變更，會在本頁更新生效日期並於網站公告。</p>
      </section>
    </LegalLayout>
  );
}

function TermsOfServicePage() {
  return (
    <LegalLayout
      eyebrow="TERMS · 服務條款"
      title="Argus 服務條款"
      intro="使用 Argus AI網站健檢平台（以下稱「本服務」）前，請閱讀以下條款。註冊或使用本服務即表示你同意這些條款。"
    >
      <section>
        <h2>1. 服務內容</h2>
        <p>
          本服務對你提供的網站進行 SEO、AEO、GEO、資訊安全與使用體驗等面向的自動化檢測，產生分析結果、
          修正建議與 PDF 報告，並可在你授權下串接 Google Search Console 顯示搜尋成效。
        </p>
      </section>

      <section>
        <h2>2. 掃描授權（重要）</h2>
        <ul>
          <li>你只能掃描你擁有或已取得明確授權的網站。建立掃描時你必須確認授權聲明，系統會記錄確認的時間與來源。</li>
          <li>主動式資安測試只對已通過網域所有權驗證的網站開放。</li>
          <li>不得利用本服務攻擊、干擾或未經授權存取任何系統，也不得規避本服務的授權與速率限制。違反者我們得立即停止服務，並配合主管機關調查。</li>
        </ul>
      </section>

      <section>
        <h2>3. 帳號</h2>
        <ul>
          <li>註冊須透過 Google 帳號授權確認 Email，並設定用戶名與密碼；請妥善保管登入資訊與 API 憑證，以你的帳號進行的操作視為你本人所為。</li>
          <li>你可以隨時在帳號設定頁自行刪除帳號；刪除後無法復原，剩餘點數一併失效。</li>
          <li>發現帳號遭冒用時請立即變更密碼並通知我們。</li>
        </ul>
      </section>

      <section>
        <h2>4. 點數與付款</h2>
        <ul>
          <li>掃描依頁數與勾選的檢測面向扣除點數：建立掃描時預扣，完成後依實際掃描頁數退還差額；掃描失敗或取消時全額退還。</li>
          <li>購點與訂閱方案的價格與內容以方案頁面公告為準；付款由綠界科技處理，電子發票依你填寫的資料開立並寄至 Email。</li>
          <li>月訂閱以信用卡定期定額每月自動扣款：首期於訂閱時扣款並發放當月點數，之後每月同一天扣款並發放點數。你可以隨時在購點頁取消，取消後不再扣款，已付款的當期權益保留到期滿；如需退費請與我們聯絡。</li>
        </ul>
      </section>

      <section>
        <h2>5. 結果的性質與限制</h2>
        <ul>
          <li>檢測結果由自動化規則、工具與 AI 產生，僅供參考，不保證找出所有問題，也不構成搜尋排名、資訊安全或法律上的保證。</li>
          <li>「沒有發現問題」不代表網站沒有問題；重新掃描未出現不等於已修好。</li>
          <li>Search Console 的數據來自 Google，平均排名為期間統計值。</li>
        </ul>
      </section>

      <section>
        <h2>6. 智慧財產權與資料</h2>
        <ul>
          <li>本服務的軟體、介面與品牌屬於 Argus 團隊所有。</li>
          <li>你取得的報告與分析結果可自由用於你的網站改善與交付給你的客戶。</li>
          <li>個人資料與 Google 使用者資料的處理方式，請見<NavLink to="/privacy">隱私權政策</NavLink>。</li>
        </ul>
      </section>

      <section>
        <h2>7. 服務變更與終止</h2>
        <p>
          我們可能因維護、升級或不可抗力暫停部分服務，並會盡量事先公告。你可以隨時停止使用本服務並自行刪除帳號；
          你違反本條款時，我們得暫停或終止你的帳號。
        </p>
      </section>

      <section>
        <h2>8. 責任限制</h2>
        <p>
          在法律允許的範圍內，本服務對因使用或無法使用本服務所生之間接或衍生損害不負賠償責任；
          我們的賠償總額以你在事故發生前三個月內實際支付給本服務的金額為上限。
        </p>
      </section>

      <section>
        <h2>9. 準據法與聯絡方式</h2>
        <p>
          本條款以中華民國法律為準據法，因本條款所生爭議，以臺灣臺北地方法院為第一審管轄法院。
          若有任何問題，請透過<NavLink to="/partners">聯絡我們</NavLink>頁面與我們聯繫。
        </p>
      </section>
    </LegalLayout>
  );
}

export { PrivacyPolicyPage, TermsOfServicePage };
