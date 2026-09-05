# image build 的品質閘門補齊至與 Quality Gate 等價

**日期**：2026-09-05
**操作者**：Claude

## 變更內容

- 新增 `scripts/verify_repository_text.py`：追蹤文字檔 UTF-8 可解碼性 + GitOps
  build workflow 的排隊契約（原本是 `quality.yml` 裡的 inline heredoc）。
- 新增 `scripts/verify_rendered_manifests.sh`：kustomize 渲染 + NetworkPolicy /
  ClientSettingsPolicy / Kali admission 斷言（原本是 `quality.yml` 裡的 inline run）。
- `quality.yml` 改為呼叫這兩支腳本。
- `build-backend.yml` 補上原本缺的四項：`promote_kali_image.py --check`、
  repository-text 檢查、kali-runner 單元測試、manifest 渲染斷言。
- `build-frontend.yml` 補上 repository-text 檢查與 manifest 渲染斷言。
- 新增 `tests/test_ci_quality_gate_parity.py`（3 項）鎖住等價性。

## 原因

使用者要求「Quality Gate 過了才 build image」。

查證後發現前提與我先前的說法不同：**兩個 build workflow 本來就有內建品質閘門**，
`build-backend.yml` 跑的是同一套 ruff + check + makemigrations --check + 部署契約
+ `test apps`（`98c7bee` 的 build log 顯示 `Ran 813 tests` 全過才繼續）。
`98c7bee` 的 Quality Gate 紅、build 綠，是同一個時序相依測試在不同 runner 上
結果不同，不是閘門被繞過。我先前說「紅燈照樣部署」是沒看 build log 就下的錯誤
推論，已在 `log/2026-09-05_ci-flaky-test-fix.md` 更正。

但查證過程發現一個**真實**的落差：build 的內建閘門是 Quality Gate 的子集，缺少
Kali digest 檢查、k8s manifest 渲染斷言、repository-text 檢查與 kali-runner
單元測試。`backend/**` 與 `k8s/**` 的混合 push（例如本日的 `98c7bee`）會建 image
並 write-back，此時 manifest 若壞掉，Quality Gate 會紅但 image 照樣產出。

抽成腳本而非兩邊各貼一份 YAML：複製的斷言遲早漂移，且沒有任何東西會告訴我們。

## 影響範圍

- 觸發條件完全未動（仍是 `push` + `paths` 過濾），部署流程行為不變。
- backend image build 會多跑約 30 秒（manifest 渲染 + 三項檢查）。
- frontend image build 會多跑約 30 秒並新增 kubectl 安裝步驟。
- `build-frontend.yml` **刻意不跑**後端測試：前端 push 改不到後端程式碼，跑 813
  個後端測試只是每次多花三分鐘卻不增加保護。此判斷已寫進 workflow 註解與測試
  docstring，避免下次被誤認為漏掉。

## 驗證方式

- `scripts/verify_repository_text.py` / `scripts/verify_rendered_manifests.sh`
  本機皆通過
- `unittest discover -s tests` → **42 tests OK**（39 → 42）
- `python3 -m unittest discover -s kali-runner/tests` → 38 tests OK
- `scripts/promote_kali_image.py --check` → runner digest 一致
- `ruff check backend scripts`、`manage.py check`、`makemigrations --check` 皆通過
- 三個 workflow YAML 皆可 `yaml.safe_load`
- **等價性測試確實抓得到退化**：移除 build-backend 的 kali-runner 步驟後測試失敗
  （`Lists differ: ['-m unittest discover -s kali-runner/tests'] != []`）
- 程式化比對確認 build-backend 相對 Quality Gate「無缺少項目」

## 尚未處理

- 真正消除重複（讓 build 以 `workflow_run` 依賴 Quality Gate，不再自己跑一遍）
  未採用：`workflow_run` 不支援 paths 過濾，需自行用 git diff 重寫路徑判斷，
  且無法在本機驗證；寫錯的後果是 image 從此不再自動建、部署靜默停擺。
  代價是每次 push 仍會把後端測試跑兩遍（Quality Gate 一次、build 一次，並行）。
