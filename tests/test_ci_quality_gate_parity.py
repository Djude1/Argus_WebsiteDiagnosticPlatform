"""image build 的品質閘門不得弱於 Quality Gate。

為什麼需要這個測試：image build 會做 GitOps write-back，直接決定正式站跑什麼。
閘門若是 Quality Gate 的子集，就會出現「Quality Gate 會抓到、但 image 照樣建出來
並上線」的缺口——而且這個缺口是靜默的：Quality Gate 紅燈時 image 仍然產出，
除非有人剛好去比對兩邊的步驟，否則不會發現。

實際發生過：build-backend.yml 曾缺少 Kali digest 檢查、k8s manifest 渲染斷言、
repository-text 檢查與 kali-runner 單元測試。

比對用「指令」而非步驟名稱：名稱可以隨意改，指令才是真正跑的東西。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# 只有 build 流程才有的環境準備與 write-back 動作，不算品質檢查
_NOISE_PREFIXES = (
    "sudo apt-get", "set -e", "SHA_TAG=", "curl", "sudo mv", "git ", "(",
    "uv sync", "npm ci", "npm run build",
)

# Quality Gate 專屬、刻意不要求 build 也跑的項目。
# 新增條目前先問：這項檢查抓到的問題，會不會讓已經建好的 image 不該上線？
# 會的話就不該例外，應該補進 build 而不是加進這裡。
_QUALITY_ONLY: set[str] = set()


def _normalise(command: str) -> str:
    previous = None
    while previous != command:
        previous = command
        command = re.sub(r"^(uv run |python3 |python |\./)", "", command).strip()
    return command


def _commands(workflow: str, job: str) -> set[str]:
    document = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    found = set()
    for step in document["jobs"][job]["steps"]:
        for line in (step.get("run") or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(_NOISE_PREFIXES) or "kustomize edit" in line:
                continue
            if line.startswith("echo ") or line == "exit 0":
                continue
            found.add(_normalise(line))
    return found


class QualityGateParityTest(unittest.TestCase):
    def test_backend_image_build_runs_every_quality_gate_check(self):
        """後端 push 能弄壞的東西，build 前都要驗過。"""
        expected = set()
        for job in ("backend", "repository-text", "kubernetes-manifests", "runner-unit-tests"):
            expected |= _commands("quality.yml", job)
        actual = _commands("build-backend.yml", "build")

        missing = sorted(expected - actual - _QUALITY_ONLY)
        self.assertEqual(
            missing, [],
            "build-backend.yml 的閘門弱於 Quality Gate，這些檢查只有 Quality Gate 會跑："
            f"{missing}。image build 會 write-back 到 kustomization.yaml 直接影響正式站，"
            "閘門不得是子集。",
        )

    def test_frontend_image_build_verifies_what_a_frontend_push_can_break(self):
        """前端 build 不跑後端測試是刻意的，但 repo 層級與 manifest 契約必須驗。

        前端 push 改不到後端程式碼，跑 813 個後端測試只是每次多花三分鐘卻不增加
        保護；但 frontend/** 與 k8s/** 的混合 push 一樣會建 image 並 write-back，
        所以 manifest 契約要在建 image 之前驗過。
        """
        actual = _commands("build-frontend.yml", "build")

        for required in (
            "scripts/verify_repository_text.py",
            "scripts/verify_rendered_manifests.sh",
        ):
            self.assertIn(required, actual, f"build-frontend.yml 缺少 {required}")

    def test_shared_check_scripts_are_used_by_both_sides(self):
        """斷言內容抽成腳本後，兩邊必須都呼叫同一支，否則等於沒抽。"""
        quality = _commands("quality.yml", "repository-text") | _commands(
            "quality.yml", "kubernetes-manifests"
        )

        self.assertIn("scripts/verify_repository_text.py", quality)
        self.assertIn("scripts/verify_rendered_manifests.sh", quality)


if __name__ == "__main__":
    unittest.main()
