# 評審問答攻略補 demo 畫面題（GEO 頁、信任輪廓、搜尋關鍵字）

**日期**：2026-10-19  
**操作者**：Claude

## 變更內容
- `專題文件生成/評審問答攻略_2026-10-18.md` 新增「十二、現場 demo 畫面會被問的題」（Q39–Q43）：
  為什麼沒有單獨 GEO 頁、信任輪廓五層的定義／扣分表／總分算法與解讀、Search Console 搜尋詞表各欄
  意義與典型型態、可做的優化（落差分析四種建議）、「有曝光但還不是目標的搜尋詞」與設為目標的實際效果。

## 原因
使用者整理評審可能追問的題目（附正式站「架構與信任」與「搜尋關鍵字」畫面），要求補進攻略。

## 影響範圍
- 純文件；答案依 `backend/apps/scans/trust_stack.py`（五層扣分與平均）、`security/observatory.py`
  （技術層來源）、`seo/gsc.py`（期間、延遲 2 天、對應頁面取法）、`seo/keywords.py`（目標關鍵字比對位置、
  上限 20×60 字）、`frontend/src/features/projects/seoKeywordGap.ts`（排名分段、落地頁不一致、
  untargetedQueries 條件）寫成，程式未改。
- 使用者提供的搜尋詞樣本含人名，攻略只以型態描述、不收錄任何人名。

## 驗證方式
- `grep` 核對五層扣分權重、等第門檻、`DATA_LAG_DAYS=2`、`MAX_KEYWORDS=20`／`MAX_KEYWORD_CHARS=60`、
  untargeted 條件（曝光 >0、字面不含且不被含、前 10）與程式一致；題號接續既有 Q38。
