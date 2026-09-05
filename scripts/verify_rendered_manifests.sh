#!/usr/bin/env bash
# 渲染 k8s kustomize 產物並斷言關鍵安全與網路契約。
#
# 抽成獨立腳本而不是留在 quality.yml 的 inline run：build-backend.yml 也要跑同一套
# 檢查（image build 會做 GitOps write-back，寫進去的 manifest 壞掉卻照樣建 image 是
# 沒有意義的），複製一份 YAML 遲早會漂移。
#
# 需要 kubectl（含內建 kustomize）在 PATH 上。
set -euo pipefail

RENDERED="$(mktemp)"
trap 'rm -f "$RENDERED"' EXIT

kubectl kustomize k8s > "$RENDERED"

# NetworkPolicy 數量寫死：新增或刪除一條都必須是有意識的決定，不能悄悄發生
test "$(grep -c '^kind: NetworkPolicy$' "$RENDERED")" -eq 9
grep -q 'name: application-egress-boundary' "$RENDERED"
grep -q 'name: data-deny-egress' "$RENDERED"
grep -q 'name: argus-kali-default-deny' "$RENDERED"
grep -q 'name: argus-kali-runner-egress' "$RENDERED"

# ClientSettingsPolicy：對齊 frontend nginx client_max_body_size 6m
test "$(grep -c '^kind: ClientSettingsPolicy$' "$RENDERED")" -eq 1
grep -qE 'maxSize: ?"?6m"?' "$RENDERED"

# application-egress 同時含 IPv4 與 API Server 可接受的 IPv6 global-unicast rule
grep -q 'cidr: 0.0.0.0/0' "$RENDERED"
grep -q 'cidr: 2000::/3' "$RENDERED"
! grep -q 'cidr: ::/0' "$RENDERED"
! grep -q -- '::ffff:0:0/96' "$RENDERED"

# Task 7：Kali namespace 隔離 + fail-closed admission + least-privilege RBAC
grep -q 'name: argus-kali$' "$RENDERED"
grep -q 'name: argus-worker-kali-orchestrator' "$RENDERED"
grep -q 'name: kali-runner' "$RENDERED"
grep -q 'name: argus-kali-admission$' "$RENDERED"
grep -q 'failurePolicy: Fail' "$RENDERED"
grep -q 'cidr: 10.96.0.1/32' "$RENDERED"
grep -q 'cidr: 172.16.2.122/32' "$RENDERED"

# Kali disabled sentinel 必須在 admission 與 ConfigMap 同時出現
grep -q 'shijie85/argus-kali-runner@sha256:0000000000000000000000000000000000000000000000000000000000000000' "$RENDERED"

echo "k8s manifest 渲染斷言通過"
