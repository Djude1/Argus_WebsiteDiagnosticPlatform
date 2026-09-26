# 知識庫迭代循環（#40-#44）——search_knowledge 落地與差集驅動補強

**日期**：2026-09-27
**操作者**：ZCode（GLM-5.3）

## 迭代機制（使用者 goal：push→知識庫→測→依回應補→30/112）
每輪：scoreboard_diff mark → 掃描 → diff 差集 → 依差集補知識/提示詞 →
rebuild → 下一輪。知識庫 = `search_knowledge` 工具（第 24，全域）＋
`backend/apps/agent/knowledge/*.md`（15 檔 61 段：v1 自著 11 檔＋v2 蒸餾
zhaoxuya520/reverse-skill 四檔——graphql/websocket/rate-limit/llm-chatbot）。

## 各輪結果與回饋補強
| 輪 | findings | 單輪解鎖 | cumulative | 差集回饋→補強 |
|---|---|---|---|---|
| #40 | 23 | 9 種 | 22 | XSS 打回 API URL（M3 波動）→提示詞硬話；提權後沒走前端管理頁→auth 第 6 點 |
| #41 | 23 | 7 種 | 23（+scoreBoard） | chatbot 0 觸碰（知識在庫無角色承接）→injection 角色補 LLM 注入面＋when |
| #42 | 20 | 9 種 | 23 | 差集腳本名稱空間 bug（log key vs API name）→key 對映＋星級前綴剝除 |
| #43 | 24 | 9 種 | 24（**+resetPasswordJimChallenge 3★**） | reset-chain 首解＝知識庫方法論→agent 執行→帳號接管全鏈打通 |
| #44 | 15 | 7 種（重解，含 4★ UNION SQLi） | **24 定格** | 收斂輪——新種邊際 ~0.4/輪，M3 波動＋剩餘簇深鏈未穿 |

## 知識庫機制驗證
- **agent 自主使用**：#40 查 reset-password 方法論（auth specialist）、
  #41 查 XSS sanitizer 兩次——system prompt 一行引導即觸發
- **方法論→新能力直接因果**：reset-chain 劇本（WSTG-ATHN-09）＋答案
  來源推理寫進知識庫後，#43 agent 查庫→枚舉安全問題→推答案→重置
  Jim→登入——resetPasswordJimChallenge 首解
- reverse-skill 評估：方法論內容蒸餾可用；自進化跨 case 記憶不採用
  （黑箱鐵律＋2609.10780 記憶無效實證）

## 30/112 評估（最終）
**結果：24/112，未達 30**（+2 種：scoreBoard、resetPasswordJim；差距 6）。
五輪每輪重解 7-9 種（爆發力提升）但新種邊際 ~0.4/輪——M3 波動下，
已解 24 種是「穩定重現集」；剩餘 6 種需要：chatbot 打穿（3 觸碰未成鏈）、
reset 剩 4 個（Jim 已通；Bender/Bjoern 答案推理更深）、XSS 挑戰偵測
（findings 連中但 Juice Shop bacon 偵測未觸發——payload 事件面差一步）、
Admin Section（提權前端驗證入 image 但波動未中）。誠實結論：機制
（知識庫→自主查用→方法論落地）已驗證閉環；30 需更多輪次累積或
上述簇的專門深鏈（下波迭代標靶）。

## 影響範圍
- 知識檔為靜態資產隨 image 打包；search_knowledge 全域（passive 也可用）
- 全部內容錨定 WSTG/OWASP/PortSwigger/jwt_tool 通用方法論——零目標特定

## 驗證方式
- scoreboard_diff cumulative/this-run 與 docker logs `Solved` 事件 comm 比對
- 檢索品質：10 查詢（reset/jwt/優惠碼/upload/csp/ssrf/graphql/ws/429/chatbot）全中
- apps.agent 64 tests OK（每 commit 前）
