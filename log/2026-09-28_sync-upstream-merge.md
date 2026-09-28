# 合併 Djude1 正式 repo main，解決同步 PR 衝突

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- 把 `Djude1/Argus_WebsiteDiagnosticPlatform` 的 `main`（90ea133）合併進 XiuJie2 fork，解決「XiuJie2:main → Djude1:main」同步 PR 的 22 個衝突檔。
- 合併結果＝fork 內容，唯一取正式 repo 的是 `k8s/kustomization.yaml` 的 image tag（`sha-504eef1`，正式叢集目前部署的版本；下次 image build 後由 bot 回寫）。

## 原因
正式 repo 在共同祖先 de28c40（Night Watch 改版）之後：合併又 revert 了 Night Watch，再以單一 commit 504eef1 移植 fork 較早的成果（前台還原、Agent UX 掃描）。兩邊改了同一批檔案，因此衝突。

逐檔比對後：
- 正式 repo 改過的 144 個檔中，107 個與 fork 內容完全相同；
- 24 個等於 fork 歷史中較舊的版本（fork 之後的 PR #4～#6 又更新過），取 fork 新版；
- 10 個 CSS 與 3 個 log 只有空白差異；
- 正式 repo 沒有 fork 缺少的檔案，也沒有編號衝突的 migration。

## 影響範圍
- 合併後正式 repo 會多出 fork 在 504eef1 之後的全部內容：會員五頁 462848b 版與深色主題、導覽列統一、大頭貼、商業合作頁、細分掃描階段與進度條、報告證據品質、`renormalize_findings` 指令。
- 部署後需套用 migration：`accounts 0006_user_avatar`、`content 0013_partner_inquiry`、`content 0014_partner_inquiry_spam_status`（Argo PreSync migrate Job 會執行）。

## 驗證方式
- 合併後的程式樹與 fork main（1e8aa6b，已通過後端 1198 項、前端 lint／typecheck／147 項測試／build）只差 k8s image tag 兩行
- `manage.py check` 通過；root `tests/` 24 項通過，`test_kali_k8s_contract` 因 sandbox 沒有 kustomize 無法執行（與本次合併無關，k8s 僅 tag 值變動）
