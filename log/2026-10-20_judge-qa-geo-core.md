# 評審問答攻略補 Q46：GEO 檢測的核心

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- `專題文件生成/評審問答攻略_2026-10-18.md` 第十二節新增 Q46：GEO 三個問題（讀得到／讀得懂／敢引用）對應十二項檢查、Princeton KDD 2024 依據、與 SEO 的差異、保守計分、誠實邊界、demo 指引與收尾句。

## 原因
使用者表示不知道怎麼向評審解釋 GEO 檢測的核心。

## 影響範圍
純文件；內容對照 `scanners.analyze_geo`、`geo_structure.py`、`geo_citability.py`、`geo_rag.py`、`geo_decay.py`、`geo_entity.py`、`ai_bots.py` 與 `docs/scan-stage-checks.md` 第 4、12 節。

## 驗證方式
- 嚴重度分布（7 資訊／4 低／1 中）與 `docs/scan-stage-checks.md` GEO 表、AI 爬蟲訊號表逐項核對。
