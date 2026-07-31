# Argus — 網站診斷平台領域語彙

本檔是 Argus 專案的領域詞彙表（glossary），定義團隊對特定概念的共同用法。
只放領域概念本身，不放實作細節。架構決策見 `docs/adr/`。

## Language

### 漏洞偵測能力分層

Argus 的「找漏洞」實際包含三個**獨立的能力層**，不可混為一談：

**指紋比對型偵測（Fingerprint-based Discovery）**:
從被動取得的 HTTP 指紋（Server / X-Powered-By / cookie / generator 標頭等）讀出軟體組件與版本，比對 CVE 資料庫，產生引用具體 CVE 編號的 Finding。被動、零額外連線、零風險。**這是 Nessus 的核心能力，也是 Argus 目前的主要交付目標。**
_Avoid_: 把「指紋比對」與下方「主動驗證」混用；兩者一個是發現、一個是確認。

**特徵模板型偵測（Template-signature Scanning）**:
對目標發送特定請求，比對回應是否符合已知漏洞的 pattern（Nuclei template）。覆蓋範圍等於模板庫涵蓋範圍；是發現工具但非指紋比對。屬加分項。
_Avoid_: Nessus 模擬——Nessus 靠的是指紋比對，不是模板命中。

**主動利用驗證（Active Exploitation Verification）**:
實際對疑似漏洞發動攻擊（如 SQLmap 注入）以「確認」漏洞可被利用。前提是已有候選目標；是確認工具，不是發現工具。具侵入性、需授權。對應 kali 鏈，屬加分項。
_Avoid_: 稱之為「偵測」或「掃描」——它不發現漏洞，只確認已被懷疑的漏洞。

### Finding 的價值層級

**版本洩露旗標（Version Exposure Flag）**:
只指出「目標洩露了軟體版本字串」（如 `Server: nginx/1.14.0`），屬 LOW 資訊洩露。Argus 目前對後端服務只做到這一層。
_Avoid_: 把它當成漏洞結論——它本身不構成 CVE 等級的發現。

**CVE 等級發現（CVE-level Finding）**:
進一步把偵測到的版本比對 CVE 資料庫，產生「該版本受 CVE-XXXX-XXXX 影響」的結論，附 severity、CWE 與修補建議。這是指紋比對型偵測的產出，也是 A 的驗收標準。
_Avoid_: 「驗證」一詞的歧義——此處的「可驗證」指 Finding 附帶可查證的 CVE 編號（可信度），而非主動利用確認（那是 Active Exploitation Verification）。
