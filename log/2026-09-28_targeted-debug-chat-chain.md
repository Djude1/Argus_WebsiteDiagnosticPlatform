# 定向調試輪——chat 鏈前三環打通、第四環卡 token 盒（26/112 維持）

**日期**：2026-09-28
**操作者**：ZCode（GLM-5.3）

## 執行（Django shell 直派，繞 orchestrator 派工波動）
| 輪 | prompt | 結果 |
|---|---|---|
| 定向 v1 | INJECT_AGENT_PROMPT＋chat 四環重點 | **打通前三環**：真端點 `/rest/chat`（POST×11 全 200，對話 11 輪）；45 步爆 token（519k>500k）未 report |
| 定向 v2 | 極簡三步（12 步預算＋3 發固定注入） | `/rest/chat` 7 發 200；同樣爆 token（506k）——「12 步」指示被 M3 無視 |

## 判定
- **四環中三環已穿**：開面板→send_message→真端點 replay（#51 起工具鏈完整）；
  唯一未穿＝注入觸發挑戰判定
- **結構性 token 問題**：chat 場景每輪回應全文進 context，M3 對話深挖行為
  （指示性步數預算無效——兩輪實證）500k 盒撐不過完整注入遞進＋report
- 26/112 維持；Chatbot Prompt Injection 簇判定＝**模型行為層**限制，
  非工具/知識/派工缺口

## 下一步（需使用者決策）
**GLM 主力輪**：將 demo 環境 MiniMax-M3 換 GLM（providers.py 鏈第二位）
跑 1-2 輪 chat 定向＋全掃——驗證模型層差異（對話紀律/指令遵循）。
成本影響：GLM 計費與 MiniMax 不同（token 單價較高），需授權後執行。

## 影響範圍
- 無程式異動（調試性質，session 掛 #52）

## 驗證方式
- AgentSession 220/221（failed: token_budget_exceeded）＋httpx log
  （/rest/chat 200×18）＋diff cumulative 26
