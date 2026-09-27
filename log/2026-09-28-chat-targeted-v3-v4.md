# chat 定向輪 v3/v4（900k 盒）——chat 領域 report 首次落地、挑戰判定未穿

**日期**：2026-09-28
**操作者**：ZCode（GLM-5.3）

## 執行
| 輪 | 設計 | 結果 |
|---|---|---|
| v3 | INJECT prompt＋chat 四環，**token 盒 900k**（依使用者「token 不用省」既有裁定；v1/v2 皆於注入遞進完成前爆 500k） | **completed**（44 步）＋**chat 領域首件 report**：「AI Chat endpoint leaks internal infrastructure via verbose error messages」——全鏈（面板→send_message→真端點→replay→report）首次單 session 走通 |
| v4 | 雙軌（工具濫用查他人資料＋注入遞進） | 60 步盒切；M3 走偏（翻站內挑戰清單 API）——findings 0 |

## 判定
- chat 領域能力**已實證**：v3 證明 500k 盒是唯一結構卡點，拉高後 M3 能完整
  走完四環＋report
- Chatbot 挑戰 3 分**未穿**：注入遞進/工具濫用等 OWASP LLM 通用面全試過，
  Juice Shop 挑戰判定條件（特定語句/行為觸發）超出通用方法論覆蓋——
  深入＝需目標特定知識＝黑箱禁區，停止
- 26/112 維持（v4 僅 weakPassword 重解）

## 建議（供使用者決策的完整選項）
1. GLM 主力輪（成本授權待回覆）——模型層差異（對話紀律/推理深度）
2. 26/112 收官——chat 領域 finding 已入庫（泛化資產），挑戰分數屬
   Juice Shop 特定判定非能力訊號
3. （已做完）900k 盒經驗寫入後續 chat 場景參考

## 影響範圍
- 調試性質 session 掛 #52；無程式異動

## 驗證方式
- AgentSession（v3 completed/44 步/1 finding；v4 60 步切）＋diff
