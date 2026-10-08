# AEO 判定回歸資料集與指標（roadmap P0-C）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/aeo/gold_dataset.py`：38 個網站、60 題人工標註（可回答 33、資訊不足 8、內容衝突 2、無答案 4、語意相近但不是答案 13；其中 17 題為保留集）。
- 新增 `backend/apps/scans/aeo/benchmark.py`：以「可回答」為正類計算 precision、recall、false positive rate、accuracy、每站耗時、混淆矩陣與各標籤正確率；門檻 `THRESHOLDS`。
- 新增 `manage.py aeo_benchmark [--holdout] [--json]`（低於門檻非零結束）與 `tests_aeo_benchmark.py`。
- 依資料集找到並修正的規則：
  - 小標題就是主題（「申請資格」底下只寫條件）時段落沒被當成候選 → `_passage_score` 標題命中權重 0.5 → 1
  - 「如需退款請聯絡客服」被當成退款規定 → 條件判斷先去掉「如需／若需」等假設語氣（`_CONDITIONAL`）
  - 網站自己的問句底下只有感謝詞卻判可回答 → 感謝詞列入 `_VAGUE`
  - 「全年無休」找不到營業時間段落 → 營業時間關鍵詞加「無休」「全天」
- 文件：`apps/scans/CLAUDE.md`、`docs/scan-upgrade-roadmap.md`、需求書 F-011 驗收方式。

## 原因
roadmap P0-C：AEO 規則需要可量測的品質基準，規則調整才知道有沒有退步；特別是「語意相近但不是答案」的誤判會讓網站主以為問題已解決。

## 影響範圍
- AEO 判定結果會因上述四項規則修正而改變（多數是由誤判「可回答」改為「資訊不足」，或由「無答案」改為正確判定）；重新掃描才會套用。
- 首次量測：全體 accuracy 0.983、precision 1.0、recall 1.0、FPR 0；保留集（規則調整後才撰寫、標註前未先跑規則）16／17，唯一不一致是內容太少時 AEO 不評估（設計行為，保留標註不改）。
- 資料集是人工撰寫的小網站，不等於真實網站分布；調整用案例的 100% 有擬合成分，保留集才是較公正的估計。
- 不需 migration。

## 驗證方式
- `manage.py aeo_benchmark`：60 題，accuracy 0.9833、precision 1.0、recall 1.0、FPR 0，平均每站 < 1 ms
- `tests_aeo_benchmark`（6 項）、`tests_aeo_answerability`（既有人工題集維持 100%）、`tests_shared_evidence`：OK
- 全套 `uv run python backend/manage.py test apps`：1547 項 OK（1 skipped）
- `ruff check backend`：通過
