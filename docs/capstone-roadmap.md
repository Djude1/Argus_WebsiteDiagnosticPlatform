# Argus 專題衝刺計畫

**建立日期：** 2026-06-07
**用途：** 整合所有架構決策與實作優先順序，供專題初審後執行參考
**最後更新：** 2026-06-12（初審後衝刺）

---

## 進度快照（2026-06-23）

| Phase | 狀態 | 說明 |
|---|---|---|
| Phase 4 — Nessus 差距補齊 | ✅ **已完成** | `ssl_scanner` / `cookie_scanner` / `header_scanner` / `owasp_mapper` 全建好並串進 `tasks.py`；Finding 加 `owasp_category` / `cwe_id`（migration 0009）；38 項測試綠燈 |
| Phase 2 — `kali_tools.py` | ✅ **已接進掃描流程** | `run_sqlmap` / `run_metasploit` + 編排層 `validate_findings_with_kali`；`tasks.py` 在 nuclei 後（deep_mode）呼叫，sqlmap 確認注入才寫 `kali-sqlmap-sqli`（A03/CWE-89）critical Finding。18 項單元測試綠燈 |
| Phase 1 — docker-compose kali | ✅ **完成** | kali 服務（`--profile attack` 隔離）+ worker docker CLI（Dockerfile）+ docker.sock 掛載（`docker-compose.attack.yml` override，不污染生產） |
| Phase 1 — 靶機 | ✅ 已就緒 | CTF 靶機 `https://htb.xn--gst.tw/`（「宇宙錯誤知識管理局」）運行中，Kali 已驗證可連通 |
| Phase 3 — CVE 實機展示 | ⏳ **待 worker rebuild 後實跑** | 程式鏈路全通；需 `--build` 重建 worker 並跑一次 active+authorized 掃描驗證端到端（實際攻擊動作需在場授權） |
| Phase 4 次要 gap — SRI + DNS/郵件安全 | ✅ **已完成** | `security/sri_scanner.py`（SRI 缺失偵測，stdlib HTMLParser）/ `security/dns_scanner.py`（SPF/DMARC/DNSSEC，dnspython）已建並接入 `tasks.py` deep_security_findings；`owasp_mapper` 加 6 個 rule_id（含首用 A08）；新增相依 dnspython |
| Phase 4 次要 gap — 第三方 JS 庫版本→CVE（gap C） | ✅ **已完成** | `security/js_library_scanner.py`（被動，vendored Retire.js 規則庫離線比對，zero-HTTP，零新套件）；`owasp_mapper` 加 `js-lib-known-vuln`→A06/CWE-1104；接入 `tasks.py` deep_security_findings；**Web 層 gap 全數補齊** |

> ⚠ 下方各 Phase 的「第 N 天」原始規劃與「尚未開始」字樣為 2026-06-07 初版內容，實際進度以本快照為準。

---

## 決策摘要

| 決策項目 | 結論 |
|---|---|
| 攻擊平台 | **Kali Linux Docker container**（加入現有 docker-compose） |
| 靶機 | **Mint 機**上架 DVWA 或 Metasploitable 2（Docker 部署） |
| 攻擊執行方式 | **Hermes-Agent** 作為 AI 決策層，呼叫 Kali container 執行工具 |
| 導師加分目標 | AI 自主完成「偵測 → 決策 → 入侵 → 回報」完整攻擊鏈 |
| Obsidian | 不引入為專案工具；個人可指向專案資料夾作唯讀 graph viewer |

---

## 整體架構圖

```
┌──────────────────────────────────────────┐
│              docker-compose              │
│                                          │
│  ┌────────┐  ┌────────┐  ┌───────────┐  │
│  │  web   │  │ worker │  │   kali    │  │
│  │(Django)│  │(Celery)│  │(攻擊平台) │  │
│  └────────┘  └───┬────┘  └─────▲─────┘  │
│                  │             │         │
│           Nuclei 偵測到       docker    │
│           高風險 CVE    exec 呼叫工具    │
│                  │             │         │
│            ┌─────▼─────────────┤         │
│            │  Hermes-Agent     │         │
│            │  (AI 決策層)      │         │
│            └───────────────────┘         │
│                  │ redis                 │
└──────────────────┼───────────────────────┘
                   │ 攻擊流量（內網）
          ┌────────▼──────────┐
          │    Mint 機         │
          │  DVWA / Metasploit│
          │  2（靶機）         │
          └───────────────────┘
```

---

## 重新評估後的優先順序

### Phase 1 — 環境架設（第 1-2 天）

**目標：讓攻擊鏈的基礎設施跑起來**

#### 1-A Kali Docker Container

在 `docker-compose.yml` 新增：

```yaml
kali:
  image: kalilinux/kali-rolling
  container_name: argus-kali-1
  networks:
    - internal
  command: >
    bash -c "apt-get update -q &&
             apt-get install -y -q sqlmap metasploit-framework nmap &&
             sleep infinity"
  restart: unless-stopped
```

#### 1-B 靶機（Mint 機上）

```bash
# Mint 機上執行
docker run -d -p 80:80 -p 443:443 --name dvwa vulnerables/web-dvwa
# 或
docker run -d -p 80:80 --name metasploitable tleemcjr/metasploitable2
```

確認 Kali container 能 ping 到 Mint 機 IP。

---

### Phase 2 — Hermes-Agent 工具整合（第 2-4 天）

**目標：讓 AI Agent 能呼叫 Kali 執行攻擊工具**

目前 `backend/apps/agent/` 已有 provider chain + tool calling loop，`ARGUS_AGENT_ENABLED=false`。

需要新增的 Agent 工具：

```python
# backend/apps/agent/tools/kali_tools.py（新增）

def run_sqlmap(target_url: str, scan_job_id: int) -> dict:
    """呼叫 Kali container 的 sqlmap 驗證 SQLi"""
    result = subprocess.run(
        ["docker", "exec", "argus-kali-1",
         "sqlmap", "-u", target_url, "--batch", "--output-dir=/tmp/sqlmap"],
        capture_output=True, text=True, timeout=120
    )
    return {"stdout": result.stdout[:3000], "returncode": result.returncode}

def run_metasploit_module(module: str, options: dict, scan_job_id: int) -> dict:
    """呼叫 Kali container 的 msfconsole 執行指定 module"""
    ...
```

Agent 觸發條件：Nuclei 偵測到 severity=critical/high 的 CVE 時自動啟動。

---

### Phase 3 — CVE 展示（第 4-6 天）

**目標：完整跑通一條攻擊鏈，準備簡報素材**

#### 推薦 CVE 選擇

| 優先 | CVE | 類型 | 為何選 |
|---|---|---|---|
| ⭐⭐⭐ | **CVE-2021-44228 Log4Shell** | Java Log4j RCE | 知名度最高，Nuclei 模板完整，有 JNDI 反彈 shell demo |
| ⭐⭐ | **CVE-2017-5638 Apache Struts** | RCE | Equifax 駭客使用，Metasploit 有現成 module |
| ⭐⭐ | **DVWA SQLi** | SQL Injection | 最容易展示，sqlmap 一行出結果 |
| ⭐ | **CVE-2014-6271 Shellshock** | CGI Bash RCE | 老但容易理解，Metasploitable 內建 |

#### 預期展示流程

```
1. 啟動 Argus 掃描靶機（Mint 機 IP）
2. Nuclei 偵測到目標 CVE → 報告列出 finding
3. Hermes-Agent 自動判斷：這個 CVE 值得驗證
4. Agent 呼叫 Kali：執行對應 exploit
5. Exploit 成功 → Agent 把結果（截圖/輸出）寫回 Finding
6. 報告呈現：「此漏洞已驗證可利用，建議優先修補」
```

---

### Phase 4 — Nessus 差距補齊（第 6-10 天）

**目標：讓 Argus 的偵測廣度更接近 Nessus，補強簡報說服力**

按照 [`docs/nessus-gap-analysis.md`](nessus-gap-analysis.md) 的優先順序執行：

| 順序 | 功能 | 預估工時 | 說明 |
|---|---|---|---|
| 1 | **SSL/TLS 深度分析** | 1-2 天 | 憑證到期、弱 cipher、過期協議；Python `ssl` 模組 |
| 2 | **Cookie 安全旗標** | 半天 | Secure/HttpOnly/SameSite；Playwright cookies API |
| 3 | **資訊洩露標頭** | 半天 | Server version、X-Powered-By；response header 分析 |
| 4 | **OWASP Top 10 對映** | 1 天 | Finding 加 `owasp_category`、`cwe_id` 欄位，強化報告說服力 |
| 5 | **CORS 設定分析** | 1 天 | Access-Control-* headers + OPTIONS 探測 |
| 6 | **CSP 品質分析** | 1-2 天 | unsafe-inline/eval 偵測 |

---

## 簡報敘事建議

```
「Nessus 是業界標準，我們來看 Argus 與它的差距在哪裡：

  Argus 獨有（Nessus 沒有）：
  → SEO / AEO / GEO 三個維度

  Argus 已補齊（Phase 4 完成後）：
  → SSL/TLS 深度分析、Cookie 旗標、CORS、OWASP 對映

  Argus 的特色亮點：
  → AI Agent 自主完成攻擊鏈驗證
     Nuclei 找到漏洞 → Agent 決策 → Kali 入侵 → 報告回寫
     [Demo: 對靶機執行，現場展示]」
```

---

## 相關文件

| 文件 | 內容 |
|---|---|
| [`docs/nessus-gap-analysis.md`](nessus-gap-analysis.md) | 完整 Nessus vs Argus 差距表，含各功能補齊難度 |
| [`backend/apps/agent/`](../backend/apps/agent/) | Hermes-Agent 現有架構（Phase 2 的修改基礎） |
| [`backend/apps/scans/CLAUDE.md`](../backend/apps/scans/CLAUDE.md) | 掃描引擎規則，修改 scanner 時必讀 |
