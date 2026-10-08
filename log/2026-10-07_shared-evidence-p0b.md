# 共用聯絡資訊證據（roadmap P0-B MVP）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/evidence/contacts.py`：Email／手機／電話格式、`normalize_email`／`normalize_phone`（+886→0、去分機）、`mailto_addresses`／`tel_numbers`、`collect_contacts`（每筆帶來源網址、取得方式、位置 content／comment／link、視窗、登入狀態）。
- 資安：`scanners.detect_pii_in_text`、`_classify_pii`、`_collect_pii` 改用共用格式與 mailto／tel 解析；`security/redaction.py` 改從共用模組取 Email／手機格式。
- AEO：`aeo/answers.py` 的電話／Email 格式改用共用模組；`aeo/evaluate.py` 新增 `reconcile_contact`——共用證據的值出現在任何可讀段落（含短標題）就判可回答，只在導覽列／頁首／隱藏區塊／註解時保留判定並在理由說明位置與「情境不同、不矛盾」；`aeo_report.shared_contacts` 只記筆數。
- 測試 `tests_shared_evidence.py`（8 項）。
- 文件：`apps/scans/CLAUDE.md`、`docs/scan-upgrade-roadmap.md`、需求書 F-011 驗收方式。

## 原因
roadmap P0-B：資安與 AEO 各自解析 Email／電話，曾出現「資安說頁面公開 Email、AEO 說找不到 Email」的矛盾（2026-10-06 h3 案例只修了一種形態）。改成同一份擷取結果，並在情境不同時說明而非互相矛盾。

## 影響範圍
- AEO 聯絡題判定可能由「無可用答案／資訊不足」變成「可回答」（Email 寫在短標題、電話寫法與 tel 連結不同時），AEO 分數可能上升；既有掃描不受影響，重新掃描才會套用。
- 資安個資分級規則不變（只換成共用格式；tel 連結比對改用正規化，+886 寫法也能對上）。
- 不需 migration。

## 驗證方式
- `tests_shared_evidence`、`tests_aeo_answerability`（人工校驗題集維持 100%）、`tests_accuracy_review`、`apps.scans.tests`：156 項 OK
- 全套 `uv run python backend/manage.py test apps`：1541 項 OK（1 skipped）
- `ruff check backend`：通過
