# 評審問答攻略補 Q47：AEO 檢測的核心

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- `專題文件生成/評審問答攻略_2026-10-18.md` 第十二節新增 Q47：AEO 一句話定義、題目來源（規則式、非 AI）、四層判定表、分數與不計分規則、可信度與引用可得性、回歸資料集門檻、與 SEO／GEO 差異、誠實邊界、demo 指引。

## 原因
使用者要求比照 Q46 整理 AEO 核心。

## 影響範圍
純文件；內容對照 `backend/apps/scans/aeo/`（questions／answers／evaluate／benchmark）與 `apps/scans/CLAUDE.md`「AEO 問答檢測」節。

## 驗證方式
- 門檻數字（正文 100 字、3 題、權重、得分比例、benchmark ≥ 0.95／FPR ≤ 0.05）與 CLAUDE.md、`docs/scan-stage-checks.md` 第 7 節逐項核對。
