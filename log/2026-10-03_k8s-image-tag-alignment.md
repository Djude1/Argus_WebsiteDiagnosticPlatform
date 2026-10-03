# 調整 K8s 映像標籤

**日期**：2026-10-03

## 變更內容

- 將 `k8s/kustomization.yaml` 中的 backend 與 frontend image tag 都指向 `sha-f633796`。

## 原因

- 把工作區既有的 GitOps manifest 變更獨立成可單獨審核與回退的 commit。

## 影響範圍

- Argo CD 同步此 manifest 時，backend 與 frontend 會使用該 tag 的既有映像；本次不建置映像、不推送 Git，也不觸發部署。

## 驗證方式

- 已確認 `f633796` 是本機已知的 Git commit，並逐項核對兩個 image 的 `newTag`。
