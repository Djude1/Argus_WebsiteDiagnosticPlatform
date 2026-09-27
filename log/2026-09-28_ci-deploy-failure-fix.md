# CI 部署失敗診斷與修復——send_message 偵測分支漏 fill（fdea668）

**日期**：2026-09-28
**操作者**：ZCode（GLM-5.3）

## 問題
push 後 Quality Gate＋Build & Push Backend Image 連三失敗（8c49c80 起），
bot 無法回寫 kustomization → 部署鏈中斷。

## 根因（三層）
1. **handler 真 bug（最重要）**：`_send_message` 偵測分支找到輸入框後
   直接 `press("Enter")`——**漏了 `loc.fill(text)`**。影響：真實掃描中
   send_message 一直在送「空訊息」（#51/52 new_req 多為空的另一半解釋
   ——Enter 前沒內容）。已補 fill。
2. **test_alg_none 斷言寫錯**：`assertIn("admin", token)`——token 是
   base64，明文 admin 不存在；改 decode payload 驗內容。
3. **SendMessage 測試 mock 結構錯**：handler 取 `page.locator(...).first`
   ——auto-attr MagicMock 不可 await；修 `locator.first = locator`＋
   `locator.click = AsyncMock`（fallback 按鈕路徑）。

## 為何本機綠、CI 紅（流程教訓）
本機「apps.agent 70 全綠」是**測試順序僥倖**；CI 跑 1144 全量暴露。
此後 agent 測試驗證口徑：**單類＋apps.agent 全套＋必要時 apps 全量**
三層（單類抓 mock 結構、套件抓順序相依）。

## 驗證與部署鏈
- apps.agent 70 OK（單類雙測＋全套）；ruff 通過
- push fdea668 → **Quality Gate ✓（5m54s）＋Backend Image ✓（7m37s）**
  → bot 回寫 38a15fc（argus-backend → sha-fdea668）
- 後續：Argo CD Sync/Health 與正式 Pod rollout 在部署機——依 K8s 規則
  需實機追蹤（本 log 不覆蓋）

## 影響範圍
- send_message 偵測分支從此真的填字＋送出（chat 鏈工具行為修正——
  下次 chat 定向輪预期 new_requests 命中率提升）
