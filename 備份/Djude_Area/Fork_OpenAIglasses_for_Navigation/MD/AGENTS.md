<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# MD（專案文件中心）

## 用途

集中存放專案的規劃、現況、使用說明與規則導覽。**修改任何程式前應先讀此處的現況文件**，完成任務後須回來更新對應記錄（見 `CLAUDE.md` 行為準則 4）。

## 關鍵文件

| 檔案 | 內容 |
|------|------|
| `現況快照.md` | 專案當前狀態、進度、未解 bug —— **每次對話前必讀** |
| `系統介紹.md` | 系統架構、模組職責總覽 |
| `idea.md` | 決策與想法記錄；每次對話結束前須更新（見 `update-md` skill） |
| `CHANGELOG.md` | 變更歷史 |
| `規則導覽.md` | 專案規則與準則索引 |
| `部署安裝.md` | 部署與安裝步驟 |
| `語音指令.md` / `關鍵字語音流程圖.md` | 語音指令清單與關鍵字觸發流程 |
| `APP使用說明.md` / `展示網站使用說明.md` | Android App 與展示網站操作說明 |
| `COMMANDS.md` | 常用命令速查 |
| `YOLO_obstacle_training_v1.md` | YOLO 障礙物訓練筆記 |
| `plan_mobile_inference_framework.md` | 行動端推論框架規劃 |
| `plan_mobile_yolo_deployment.md` | 行動端 YOLO 部署規劃 |
| `plan_model_management.md` / `plan_model_on_device.md` | 模型管理與裝置端模型規劃 |
| `plan_vertex_ai_integration.md` | Vertex AI 整合規劃 |

## For AI Agents

### 在本目錄工作

- 文件一律 **繁體中文**
- 完成任務後依 `update-md` skill 更新 `idea.md` 與相關 `.md`，並同步 `MEMORY.md` 索引
- 修改規則/MD 後必須執行 `CLAUDE.md` 的「MD 修改強制核對清單」（跨檔一致性、引用有效性、無矛盾、完整性）

### 常見模式

- `plan_*.md` 為前瞻規劃，未必已實作；對照 `現況快照.md` 確認實際狀態再行動

<!-- MANUAL: 此線以下手動註記在重新產生時會保留 -->
