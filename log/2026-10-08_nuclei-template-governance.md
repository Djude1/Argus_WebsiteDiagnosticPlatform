# Nuclei 模板治理（roadmap §6 第 1 項）

**日期**：2026-10-08  
**操作者**：Claude

## 量測發現的問題（Nuclei v3.8.0 ＋ nuclei-templates v10.4.9，本機測試站）
| 模板集 | 模板數 | 對單一網址的請求數 | 2 RPS 需要 |
|---|---|---|---|
| 原 deep 模式（正式環境實際使用） | 6680 | 9535 | 約 80 分鐘 |
| 快速模式標籤改正後 | 6631 | 9508 | 約 80 分鐘 |
| CVE（重大、高） | 2724 | 3123 | 約 26 分鐘 |
| misconfig＋exposure | 1113 | 3311 | 約 27 分鐘 |
| **KEV（採用）** | **511** | **628** | **約 5 分鐘** |

- **正式環境的 Nuclei 幾乎跑不完**：
  - 全網站把每個爬到的頁面都交給 Nuclei，每秒只有 1–2 次請求、300 秒上限。
  - 逾時後回傳 0 項，覆蓋紀錄卻是「完成」。
- **快速模式標籤寫錯**：用了目錄名稱 `cves`／`misconfigurations`／`exposures`／`default-logins`，Nuclei 標籤其實是單數，只選到 3 個模板。正式流程沒用到這個模式。
- **模板版本沒有鎖定**：Dockerfile 用 `nuclei -update-templates || true`，每次 build 模板不同；下載失敗照樣 build 成功，之後每次掃描都是「0 項發現」。
- **找不到模板也不算失敗**：缺 binary、異常結束都回傳空清單並記為「完成」。

## 變更內容（使用者選擇：KEV＋只掃網站根網址）
- **Dockerfile**：
  - 模板 v10.4.9 下載到 `/opt/nuclei-templates`。
  - 先以 sha256 驗證模板庫自帶的 `templates-checksum.txt`，再逐一以 sha1 驗證每個模板內容。
  - 寫入版本檔；確認 KEV 模板數大於 100。任何一步失敗 build 就失敗。
  - `ENV ARGUS_NUCLEI_TEMPLATES_DIR`。
- **`nuclei_scanner.py`**：
  - 固定 `TEMPLATE_POLICY`（`-tags kev`、嚴重度中以上、排除 dos／fuzz 等、只用 http）。
  - `EXCLUDED_TEMPLATE_IDS` 留給有實測誤報時再加，目前為空。
  - 只掃網站根網址。
  - 每次用 `nuclei -tl` 列出實際選到的模板，記錄引擎版本、模板版本、模板數與指紋（路徑＋內容雜湊的 sha256）。
  - 移除 deep／fast 兩種模式與 `extra_urls`。
- **`process_runner`**：逾時時把已輸出的 stdout 放進 `TimeoutExpired.output`。Nuclei 邊掃邊輸出（實測第一個結果在第 0 秒），所以逾時也能保留已找到的結果。
- **`tasks.py`**：
  - 逾時記為 `partial`；`NucleiUnavailable`（沒有 binary／模板目錄／選不到模板／異常結束）記為 `failed`，原因只寫固定代碼。
  - 模板集紀錄存 `warning_summary.nuclei` 並寫進 log。
  - WAF 之後 0 項發現的說明只在完整跑完時才加。原本 Nuclei 失敗時也會加，並把「失敗」蓋成「部分」。
- **設定**：`ARGUS_NUCLEI_DEEP_TIMEOUT`（300）改為 `ARGUS_NUCLEI_TIMEOUT`（660）。全網站時 Nuclei 與 Katana 分預算只有 1 RPS，628 個請求約 630 秒。`.env.example` 與 `docker-compose.juice.yml` 已同步。
- **Agent 的 `run_nuclei` 工具**：改用同一個模板目錄。image 已沒有預設的 `~/nuclei-templates`。

## 過程中發現並修正
- `nuclei -tl` 沒加 `-no-stdin` 時會等 stdin 的目標清單：在 shell 4 秒結束，在 Python `subprocess.run` 裡卡到 120 秒逾時。
  - 已加 `-no-stdin`＋`stdin=DEVNULL`。
  - `-version` 另加 `-duc`，避免更新檢查。

## 驗證方式
- 本機以 git clone 的 v10.4.9 打包成同樣格式的 tar.gz，用 `sh` 執行 Dockerfile 的模板步驟：通過；竄改一個模板後 sha1 驗證失敗。
  - 沙箱 proxy 擋 GitHub archive 下載（403），實際 image build 要看 CI。
- 真實 `run_nuclei`（v3.8.0＋v10.4.9 KEV）掃本機測試站：
  - 輸入 `/some/page?x=1` 實際掃 `/`。
  - 511 個模板、628 個請求、沒有逾時。
  - log 列出版本與指紋。
- `tests_nuclei_scanner.py` 重寫：
  - 指令（模板目錄、KEV 政策、根網址、速率、逾時）。
  - 去重、逾時保留結果、異常結束與缺 binary 為失敗、取消不被吞掉。
  - 模板集指紋（隨內容改變）、缺目錄／選不到模板為失敗。
  - 真實 nuclei 逾時保留結果（快模板命中、慢模板逾時；沒有 binary 時略過）。
- 根目錄 `tests/test_dockerfile_contract.py` 鎖定：
  - 模板版本與 sha256 ARG、驗證步驟、不得 `|| true`。
  - Dockerfile 指令不得有 `-update-templates`。
  - 模板目錄與 settings 預設一致。
- 全套後端測試、`ruff check backend`、root `tests/`。`test_kali_k8s_contract` 需要 kubectl，沙箱沒有，改動前就失敗。

## 尚未驗證／後續
- **CI image build**：GitHub archive 下載與驗證要在 CI 確認。
- **正式叢集實際掃描**：
  - 看 `warning_summary.nuclei` 是否有版本與指紋。
  - 看 1 RPS 下是否在 660 秒內完成。
- **KEV 以外的模板**：例如 misconfig／exposure，需要更多請求預算，未納入。敏感檔案已由 `exposure_scanner` 另外探測。
