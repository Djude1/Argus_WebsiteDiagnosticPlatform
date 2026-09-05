#!/usr/bin/env python3
"""追蹤文字檔的 UTF-8 可解碼性，以及 GitOps build workflow 的排隊契約。

抽成獨立腳本而不是留在 quality.yml 裡的 inline heredoc：build-backend.yml 也要跑
同一套檢查，複製一份 YAML 遲早會漂移——兩邊各自演化、其中一邊悄悄變寬鬆，而
沒有任何東西會告訴我們。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

TEXT_SUFFIXES = {
    ".md", ".py", ".js", ".jsx", ".css", ".json", ".toml", ".yml", ".yaml",
}

GITOPS_WORKFLOWS = (
    ".github/workflows/build-backend.yml",
    ".github/workflows/build-frontend.yml",
    ".github/workflows/build-kali-runner.yml",
)


def check_text_files() -> None:
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    for value in files:
        path = pathlib.Path(value)
        if path.suffix.lower() in TEXT_SUFFIXES:
            path.read_text(encoding="utf-8")


def check_gitops_queue_contract() -> None:
    """image build 必須共用同一個 concurrency group 且保留完整排隊。

    cancel-in-progress 會讓密集 push 時較早的 build 被中途砍掉，那次 commit
    就永遠不會有對應的 image；queue: max 則確保 pending 的 run 不被後來者取代。
    """
    for value in GITOPS_WORKFLOWS:
        path = pathlib.Path(value)
        text = path.read_text(encoding="utf-8")
        assert "group: argus-gitops-cd" in text, f"{path} 缺少共用 GitOps concurrency group"
        assert "queue: max" in text, f"{path} 未保留完整 pending queue"
        assert "cancel-in-progress: true" not in text, f"{path} 不得取消執行中的 image build"


def main() -> int:
    check_text_files()
    check_gitops_queue_contract()
    print("repository-text 檢查通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
