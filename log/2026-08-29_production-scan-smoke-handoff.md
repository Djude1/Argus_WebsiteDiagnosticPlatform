# 正式站掃描 smoke test handoff 文件建立

**日期**：2026-08-29
**操作者**：Claude（ZCode session）

## 變更內容
- 新增 `docs/handoff-2026-08-29-production-scan-smoke-test.md`：正式站完整掃描主流程回歸驗證（smoke test）＋ worker1 健康確認的交接文件，含已固定決策表、逐步 curl 指令、強成功條件清單、失敗分流表、收尾清單與地雷禁令。

## 原因
使用者要求把「第一優先事項」寫成 handoff，且盡可能減少執行時的抉擇。整體未完成功能盤點後，判定「目前正式影像自 2026-07-24 scan 18 後未再做端到端掃描驗證，期間又經多次 rollout」為最高優先；worker1 節點故障（07-24 標記待修、無已修復紀錄）與「前端 `scan_effectiveness` 顯示」需要的資料形狀擷取，一併併入同一次驗證流程。

## 影響範圍
- 僅新增文件，不改任何程式碼與設定。
- 文件內容引用並固定多項事實：掃描 API 欄位（`backend/apps/scans/serializers.py`）、狀態機與 cancel 語意（`backend/apps/scans/views.py`）、JWT/註冊流程（`backend/apps/accounts/views.py`）、錢包 API（`backend/apps/billing/views.py`）、預設頁數與點數單價（`settings.py`：50 頁／10 coin）、對外網域（`k8s/01-namespace-config.yaml`）。相關文件若日後改版，本 handoff 的指令需同步檢查。

## 驗證方式
- handoff 內所有 API 路徑、欄位與預設值均當日以 Read／rg 對原始碼核對（非僅依文件轉述）。
- 尚未實際執行 smoke test 本身；文件即為執行脚本，執行結果應回寫 `k8s/README.md` 驗證矩陣與後續 log。
