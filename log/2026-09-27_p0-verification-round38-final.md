# P0 內部提升循環收官（#38 驗證輪）——三項全閉環

**日期**：2026-09-27
**操作者**：ZCode（GLM-5.3）

## #38 結果（29 findings、6 sessions、26 分鐘——本波最高）
- **probe_payload_injection 首次上場：10 次呼叫**（recon 2＋injection specialist 8），
  覆蓋 nosql/ssti/command/lfi 四家族；`when` 修正生效——orchestrator dispatch 3
  直接以「家族化覆蓋」語言派 injection
- **baseline 比對機制實戰發揮**：`param=name` nosql 探測 status 500＋
  `markers_hit: ['$where']`（baseline 無此標記才命中）——誤報控制鏈路驗證
- **XSS 三輪連中**：`DOM-based XSS in /#/search via q parameter (Search Results
  heading)`——#36/#37/#38 連續命中（#1-#35 全滅 → 三連中＝能力穩定化）
- SQLi login bypass＋search 注入延續；sess107 XSS specialist 標準工作流成形
  （navigate 8＋type_text 9＋report 1）

## 四輪趨勢（P0 改造前→後）
| 輪 | findings | XSS | prober | 備註 |
|---|---|---|---|---|
| #33/#34（改造前峰值） | 51/40 | 0 report×63/62 步 | — | replay 死路 |
| #35 | 20 | 0（打 API URL） | 0 | navigate 採用 27 次 |
| #36 | 25 | **首中**（hash 路由） | 0 | injection 未被派 |
| #37 | 25 | 連中＋report 修復 | 0 | orchestrator 誤覆蓋判斷 |
| #38 | **29** | **三連中** | **10 次＋命中訊號** | 全閉環 |

## P0 驗收結論
1. ✅ P0-1 navigate_and_observe：XSS 35 輪全滅→三連中；report 紀律同步修復
2. ✅ P0-2 假設/換道紀律：orchestrator 極簡任務二次派工＋帶證據 brief 成常態
3. ✅ P0-3 probe_payload_injection：上場＋baseline 命中訊號＋衍生 LFI 疑點報告
4. 教訓入檔：**工具進 schema ≠ 角色會用**——每個新工具需在對應角色提示詞/
   能力目錄 when 同步引導（#36/#37 兩輪才打通）

## 影響範圍
- P0 全部落地（7 commit）；P1/P2 backlog 見 log_assets_juice/gap_analysis_2026-09-26.md
- 單輪波動仍存在（M3 特性）——多輪聯集仍是建議呈現法

## 驗證方式
- apps.agent 56 tests OK＋全套 exit 0＋ruff 通過（每 commit 前跑）
- #35-#38 四輪實測鏈：行為統計（AgentStep Counter）＋findings 對照＋
  dispatch brief 記錄（本 log 與前三份 log）
