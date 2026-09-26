# Agent 能力缺口分析（內部提升循環起點）

**日期**：2026-09-26
**操作者**：ZCode（GLM-5.3）

## 變更內容
- 純分析任務，無程式異動。產出 `log_assets_juice/gap_analysis_2026-09-26.md`（未追蹤的工作檔）：
  - Juice Shop v20 112 挑戰 vs #30/31/33/34 四輪 findings 聯集覆蓋對照（約 12-14 項等效覆蓋）
  - AgentStep 725 步行為統計（XSS specialist 0 report、SecurityQuestion 觸碰 77 次未打穿、ssti/xxe 0 觸碰）
  - 外部研究：CAI（generic_linux_command＋breadth-first＋Decision Log）、Excalibur（arXiv:2602.17622，難度感知規劃，91% CTF）、arXiv:2609.10780（記憶假說否定，瓶頸=規劃）、XBOW（攻擊鏈＋獨立驗證）、PentestGPT、CTF-ABACUS
  - P0/P1/P2 提升方向與不投資清單

## 原因
使用者指示：競賽對抗結束，轉入內部提升循環——查網路案例了解 AI pentest agent 應具備條件，評估更多角色/插件能否加強。

## 影響範圍
- 後續 agent 改良（runner.py/loop.py/tools.py）依本分析 P0→P2 順序投資
- 主要結論：瓶頸排序＝XSS 執行閉環（工具錯配）＞攻擊假設生成/換道紀律（規劃層）＞payload 光譜＞角色擴充。更多角色/插件只解 Type A 缺口，規劃層投資報酬更高。

## 驗證方式
- 覆蓋對照：demo DB Finding 聯集 vs `GET /api/challenges`（容器重啟後 solved=0，聯集取自 DB）
- 行為統計：AgentSession/AgentStep 查詢（#33 374 步、#34 351 步）
- 外部文獻：arXiv 摘要頁＋GitHub API 抓 CAI repo 實文（web-research 管道故障改 WebFetch/gh；WebSearch 配額 09-28 重置）
