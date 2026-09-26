# 四瓶頸補強迭代（#45-#48）——26/112 收斂

**日期**：2026-09-28
**操作者**：ZCode（GLM-5.3）

## 補強→驗收鏈（ad8239b 入 image 後）
| 輪 | findings | sessions | 新種 | 判讀 |
|---|---|---|---|---|
| #45 | 6 | 0 | — | **報廢**：靶機 restart 未就緒（sleep 12s 不夠）→爬蟲 navigation:Error/no_pages_crawled→agent 跳過。流程修正：restart 後輪詢 version 200 才建掃描 |
| #46 | 21 | 10 | **+2**：localXssChallenge（DOM XSS 1★）＋freeDeluxeChallenge（3★） | 雙載體紀律生效（agent 以 iframe javascript: 觸發偵測——35+ 輪全滅項解鎖）；商業邏輯知識落地（deluxe 詐取） |
| #47 | 29 | 10 | 0 | 7 種重解 |
| #48 | 23 | 10 | 0 | 連兩輪零新種→收斂 |

## XSS 偵測面實測方法（可複用）
手動 Playwright 對照兩 payload：`<iframe src="javascript:alert(\`xss\`)">` 觸發
localXssChallenge、`<img src=x onerror=alert(1)>` 不觸發——偵測掛在 URL 載入
類載體。據此寫進 XSS prompt 的是**通用雙載體紀律**（事件屬性類＋URL 載入類
各測一，偵測系統常只覆蓋一類）——不寫靶機機制，泛化紅線維持。

## 最終盤點
- **cumulative 26/112（未達 30，差 4）**
- 本 session 淨增 +4：scoreBoard、resetPasswordJimChallenge（帳號接管全鏈）、
  localXssChallenge、freeDeluxeChallenge
- 未穿瓶頸（下波標靶）：chatbot 簇（真端點引導入 image 但兩輪未觸發互動）、
  reset 剩 4（Bender/Bjoern 答案推理更深）、Bonus Payload、Admin Section、
  Password Hash Leak
- 新種邊際：#46 +2 → #47/#48 +0——M3 波動下 26 為當前穩定重現集

## 影響範圍
- runner.py 三處提示詞補強（XSS 雙載體/chatbot 真端點/reset 題型掃描）
- 測試環境流程：靶機就緒輪詢入建掃描前置

## 驗證方式
- scoreboard_diff（mark→掃→diff）＋comm 清單比對每輪新種
- apps.agent 64 tests OK（ad8239b 前）
