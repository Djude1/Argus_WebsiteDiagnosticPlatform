# docs/scan-stage-checks.md 與系統手冊附錄三依近期程式變更同步

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- `docs/scan-stage-checks.md`：總覽表（Nuclei 上限自適應與 CDN 後略過、ZAP 列改為主動掃描）、爬取（主動工具 6 RPS、其他語言版延後、HAR 用途）、UX 觸控目標新門檻、深度資安 X-Powered-By 不重複、主動探測 RPS 與 CDN 略過、敏感檔探測覆蓋狀態、連結檢查額度對半與 WAF 說明、AI Agent（同攔截頁合併、出口 IP 核對、觀察不計分）、彙整評分（Agent 不計分、優先清單排序）、信任輪廓技術層等第。
- `專題文件生成/系統手冊_附錄三_掃描階段與檢測項目.md`：同步上述各點的精簡版。

## 原因
使用者要求把這幾天的掃描行為變更（2026-10-17～10-20 的 commits）反映到各階段檢測說明；原文件停在 2026-10-10／10-12 的狀態。

## 影響範圍
純文件。每項敘述都對照 `tasks.py`、`crawler.py`、`exposure_scanner.py`、`seo/collect.py`、`seo/link_trend.py`、`agent/findings.py`、`agent/tools.py`、`scanners.py` 與 `config/settings.py` 現行值。

## 驗證方式
- `grep` 核對：`ARGUS_ACTIVE_MAX_RPS=6`、`ARGUS_NUCLEI_MAX_TIMEOUT=1800`、ZAP spider 120／active 600、`_WCAG_AA_TAP_TARGET_PX=24`、`_LANGUAGE_QUERY_KEYS`、`_exposure_probe_status`、`unconfirmed_caveat` 門檻、`same_issue` 證據相似度。
