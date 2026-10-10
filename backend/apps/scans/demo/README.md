# 示範專案資料

新帳號（Email 註冊、第一次 Google 登入）會自動得到一個示範網站專案「晨光咖啡烘焙所」（`SiteProject.is_demo=True`）。
這樣使用者一進來就看得到 Argus 的完整分析結果，不會面對空白頁面。

| 檔案 | 內容 |
|---|---|
| `dataset.json.gz` | 三次掃描的 `ScanJob`（含 `aeo_report`、`seo_report`）、`Page`、`Finding` 欄位，以及最新一次的 `FixOutput`；約 100 KB |
| `screenshots/` | 每頁截圖，128 色 PNG，約 1.5 MB。`Page.screenshot_path` 指向這裡（相對 `BASE_DIR`），所有示範專案共用，不複製到 media |
| `seed.py` | `create_demo_project(user)`：複製成使用者自己的資料，並把三次掃描的時間平移到 29 天前、15 天前、1 天前 |

## 資料怎麼來的

資料**不是手寫的**，而是對虛構網站 `scripts/demo_site/server.py`（`www.morninglight-coffee.example`）跑三次真實的全網站主動掃描。三次分別對應網站的 v1、v2、v3，網站逐步改善。

- 分數：建立時以目前公式重算（`seed.rescore_with_current_formula`），2026-10-10 衰減常數改為 100 後是 67 → 70 → 71（匯出時的舊公式是 57 → 60 → 61）。三次掃描建立時寫入同一組評分版本（`versions.py` 的目前值），總覽才會顯示分數變化，而不是「評分規則已更新，無法直接比較」；2026-10-09 前建立的示範專案由 migration `0032_demo_scan_versions` 補上。
- 問題分析有「新增／持續／本次未出現」，總覽有趨勢。
- 網站刻意埋了五個維度的常見問題：
  - 缺 alt、重複 H1、缺 meta description
  - 結構化資料語法錯誤、AEO 資訊不足
  - 行動版溢出、觸控目標過小、JS 錯誤
  - `.env` 外洩、舊版 jQuery、Apache／PHP 版本與 CVE、缺 CSP／HSTS、Cookie 旗標、個資
  - 404 頁、慢頁面
  - 連結（SEO 分析頁）：站內 404（v1 秋季活動、v1–v2 去年菜單）、站內 301（/shop）、站外 404（v1–v2 引用已刪除的維基頁面）、
    沒有文字的圖片連結（v1–v2 LINE 圖示缺 alt）、「點此」（v1）、子網域商店、Instagram（對方限制檢查）、
    裸網域重複內容（v1；v2 起 301 到 www）
- 修正產出：以 `fixgen.engine.build_artifacts` 依爬取事實產生。LLM 回覆是手寫的，但仍經過事實驗證。網站沒有的電話與地址會變成【請填寫】佔位符。

網站內容、電話、Email、金鑰全部是虛構的。

## 重新產生（改了掃描規則、資料欄位或想換內容時）

需要 DEBUG 本機環境，並且能跑 Playwright。

```bash
# 1. 讓虛構網域指到本機（www、裸網域、shop 子網域），啟動 v1（需要 80 port）
printf "127.0.0.1 www.morninglight-coffee.example\n127.0.0.1 morninglight-coffee.example\n127.0.0.1 shop.morninglight-coffee.example\n" | sudo tee -a /etc/hosts
python scripts/demo_site/server.py --version 1 --port 80

#    有出網代理的環境，runserver 要設 NO_PROXY=morninglight-coffee.example,.morninglight-coffee.example，
#    否則 SEO 連結檢查會把虛構網域送到代理（站外連結仍經代理檢查）
# 2. 以 DEBUG＋ARGUS_ALLOW_PRIVATE_TARGETS 啟動 runserver，用 staff 帳號
#    （主動模式的網域驗證旁路）新增專案 http://www.morninglight-coffee.example/
#    並建立「整個網站＋主動測試＋五個維度」的掃描，等它完成。
# 3. 停掉網站，改用 --version 2 重啟，對同一個專案再掃一次；--version 3 再掃一次
# 4. （選用）為最新一次掃描產生 FixOutput
# 5. 匯出（會覆蓋 dataset.json.gz 與 screenshots/）
uv run python backend/manage.py export_demo_dataset <專案 id>
```

匯出時會移除只反映開發機的掃描紀錄（例如「Nuclei binary 未安裝」）。
匯出後執行 `manage.py test apps.scans.tests_demo_project`，確認資料完整。

## 既有帳號

示範專案只在建立帳號時自動產生。要補給既有帳號：

```bash
manage.py seed_demo_project --without-projects --dry-run   # 先看會建立幾個
manage.py seed_demo_project --without-projects             # 還沒有任何網站專案（含已封存）的帳號
manage.py seed_demo_project --email someone@example.com
```

封存過示範專案的帳號不會被補回來。
