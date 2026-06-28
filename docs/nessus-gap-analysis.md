# Nessus vs Argus 差距分析

**建立日期：** 2026-06-07
**用途：** 專題初審參考資料、後續補齊功能的優先順序依據

> 實作優先順序與完整攻擊鏈架構見 [`docs/capstone-roadmap.md`](capstone-roadmap.md)

---

## Argus 目前掃描能力全覽

| 模組 | 能力 |
|---|---|
| **Playwright 爬蟲** | BFS 多頁爬取、JS 渲染後 HTML |
| **Katana** | JS 端點挖掘、秘鑰偵測（API key/token/private key）、Tech stack 識別、Vite dev server 暴露 |
| **Nuclei** | CVE、vulnerabilities、misconfigs、exposures、default-logins（fast/deep 雙模式） |
| **Security（rule-based）** | HTTPS 檢查、HSTS/CSP 存在性/X-Frame-Options/X-Content-Type-Options、CSRF token、PII 偵測 |
| **Security（深度，`security/`）** | SSL/TLS 深度、Cookie 旗標、資訊洩露標頭、CORS、CSP 品質、SRI 缺失、DNS/郵件（SPF/DMARC/DNSSEC）、敏感檔探測、硬編碼秘鑰、OWASP/CWE 對映、Nuclei→Kali sqlmap 攻擊鏈 |
| **SEO** | meta title/description、H1、圖片 alt、canonical URL |
| **AEO** | FAQPage/HowTo Schema 偵測 |
| **GEO** | JSON-LD 結構化資料、JS 渲染差距、llms.txt、robots.txt AI 爬蟲封鎖 |
| **免費工具** | 測速、釣魚 URL 分析、釣魚郵件分析 |

---

## 與 Nessus 的差距分析

### 完全缺少（Web 層面，補起來最有價值）

| # | 功能 | Nessus 做什麼 | Argus 現況 | 補齊難度 |
|---|---|---|---|---|
| 1 | **SSL/TLS 深度分析** | 憑證到期日、自簽憑證、弱加密套件（RC4/3DES）、過期協議（TLS 1.0/1.1）、憑證鏈完整性 | ✅ 已補齊（security/ssl_scanner.py：憑證到期/弱協議/弱 cipher/自簽） | 低（Python `ssl` 模組） |
| 2 | **Cookie 安全旗標** | Secure、HttpOnly、SameSite 屬性逐一檢查 | ✅ 已補齊（security/cookie_scanner.py） | 低（Playwright 可直接讀 cookies） |
| 3 | **資訊洩露標頭** | Server 版本洩露（`Apache/2.4.x`）、`X-Powered-By`、`X-Generator`、`X-AspNet-Version` | ✅ 已補齊（security/header_scanner.py：Server/X-Powered-By） | 低（分析 response headers） |
| 4 | **SRI 缺失** | 外部 CDN `<script>/<link>` 缺少 `integrity` hash | ✅ 已補齊（security/sri_scanner.py） | 低（HTML parser 已有基礎） |
| 5 | **CORS 設定分析** | `Access-Control-Allow-Origin: *` 過寬、credentials + wildcard 錯誤組合 | ✅ 已補齊（security/header_scanner.py：wildcard / credentials 組合） | 低（分析 CORS headers） |
| 6 | **CSP 品質分析** | `unsafe-inline`、`unsafe-eval`、wildcard source 偵測 | ✅ 已補齊（security/header_scanner.py：unsafe-inline/unsafe-eval 偵測） | 中（需解析 CSP policy 字串） |
| 7 | **DNS / 郵件安全** | SPF record、DKIM 設定、DMARC 政策、DNSSEC | ✅ 已補齊 SPF/DMARC/DNSSEC（security/dns_scanner.py）；DKIM 不做（黑盒無法可靠列舉 selector） | 中（需 `dnspython`） |
| 8 | **OWASP Top 10 對映** | 每個 finding 標記對應的 OWASP 分類（A01~A10）、CWE 編號 | ✅ 已補齊（security/owasp_mapper.py：tag/backfill；前端報告詳情面板亦顯示 OWASP/CWE） | 低（報告層面加標籤） |

### 部分覆蓋（Nuclei 有幫忙，但不完整）

| # | 功能 | Nessus 做什麼 | Argus 現況 | 差距 |
|---|---|---|---|---|
| 9 | **敏感路徑暴露** | `/.git/HEAD`、`/.env`、`/phpinfo.php`、備份檔（`.bak/.old`）、目錄列舉 | ✅ 已補強客製探測（security/exposure_scanner.py）+ Nuclei `exposures` tag | 已有主動 content discovery，覆蓋度持續擴充 |
| 10 | **第三方 JS 庫漏洞** | jQuery/Bootstrap/lodash 舊版本比對 CVE | ✅ 已補齊（security/js_library_scanner.py：Retire.js 規則庫離線比對，2026-06-23） | 已補齊 |
| 11 | **預設憑證測試** | 廣泛的預設帳密嘗試清單 | Nuclei `default-logins` 模板有基本涵蓋 | 覆蓋率依模板安裝狀況而異 |

### Nessus 有但 Argus 不適合做（架構差異太大）

| # | 功能 | 說明 |
|---|---|---|
| 12 | **Port / 網路層掃描** | Nessus 用 nmap 做 TCP/UDP port scan、service fingerprinting；Argus 定位是 Web scanner，網路層超出範疇 |
| 13 | **主機 / OS 層掃描** | patch level、OS 配置審計；需要 agent 安裝或 SSH 存取，與 Argus 純 Web 架構不相容 |
| 14 | **認證掃描（Authenticated Scan）** | 提供帳密後登入再掃內部頁面；需要大幅架構改動（目前 Argus 只掃公開頁面） |
| 15 | **合規性稽核（PCI DSS / CIS / HIPAA）** | 需要整套基礎設施存取；Web-only 工具無法達到 Nessus 的合規深度 |

---

## 補齊進度（原優先順序，現多數已完成）

> 原規劃依「視覺衝擊 × 實作容易度」排序；以下為實際完成狀態（程式為準）。

### 第一優先 — ✅ 全部完成

| 功能 | 狀態 | 位置 |
|---|---|---|
| SSL/TLS 深度分析 | ✅ | `security/ssl_scanner.py` |
| Cookie 安全旗標 | ✅ | `security/cookie_scanner.py` |
| 資訊洩露標頭偵測 | ✅ | `security/header_scanner.py` |
| OWASP Top 10 對映 | ✅ | `security/owasp_mapper.py`（+ 前端報告顯示） |

### 第二優先 — ✅ 全部完成

| 功能 | 狀態 | 位置 |
|---|---|---|
| CORS 設定分析 | ✅ | `security/header_scanner.py` |
| CSP 品質分析 | ✅ | `security/header_scanner.py` |
| SRI 缺失偵測 | ✅ | `security/sri_scanner.py` |

### 第三優先

| 功能 | 狀態 | 位置 / 備註 |
|---|---|---|
| DNS/郵件安全（SPF/DMARC/DNSSEC） | ✅ | `security/dns_scanner.py`（DKIM 刻意不做） |
| 第三方 JS 庫 CVE 對比 | ✅ **已補齊** | `security/js_library_scanner.py`（vendored Retire.js 規則庫，2026-06-23） |

### 額外完成（不在原表）

| 功能 | 位置 |
|---|---|
| 敏感檔/路徑主動探測（content discovery） | `security/exposure_scanner.py` |
| 硬編碼秘鑰偵測（API key/token/private key） | `security/secret_scanner.py` |
| Nuclei→Kali sqlmap 主動驗證攻擊鏈 | `security/kali_tools.py`（三重授權鎖，待實機 demo 收尾） |

---

## 定位說明（可直接用於簡報）

> Argus 定位是「Web 應用層安全 + 內容品質」一站式掃描器；Nessus 則是「網路/主機/應用」全層次企業弱點管理平台。
>
> 兩者在 Web 應用層有重疊，但：
> - **Argus 的獨特優勢**：SEO / AEO / GEO 三個維度是 Nessus 完全沒有的；外加 Nuclei→Kali AI 攻擊鏈主動驗證
> - **Nessus 的明顯優勢**：網路層掃描、主機/OS 層稽核、合規性稽核（PCI/CIS/HIPAA）
>
> Web 應用層所有 gap 已全數補齊（SSL/Cookie/Header/CORS/CSP/SRI/DNS/OWASP 對映 + 敏感檔/秘鑰探測 + 第三方 JS 庫版本→CVE 對比），純 Web 掃描範疇已涵蓋 Nessus Web Plugin 的主要子集；**Web 層 gap 已全數補齊**。
