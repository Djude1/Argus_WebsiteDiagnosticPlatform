#!/usr/bin/env python3
"""Juice Shop 記分板差集量測（log ground truth 版）。

用法：
  scoreboard_diff.py mark     # 掃描前：記錄當前 log 行數基準
  scoreboard_diff.py diff     # 掃描後：從基準起列新解鎖＋未解鎖差集

原理：/api/challenges 的 solvedAt 在 v20 實測全 null（API 層異常），
但容器 stdout 的 `info: Solved <name>` 事件完整可靠——以此為 ground truth。
"""
import json
import subprocess
import sys
from pathlib import Path

MARK_FILE = Path(__file__).with_suffix(".mark")
CONTAINER = "argus-juice-shop-1"
# 佔位項（人類玩法/文件閱讀類，非漏洞能力訊號；scoreBoard 已被 agent 解開故保留計數）
PLACEHOLDER = {"Privacy Policy", "Privacy Policy Inspection", "Mass Dispel"}


def _logs() -> list[str]:
    r = subprocess.run(
        ["docker", "logs", CONTAINER],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, timeout=60,  # 時間序混合流（node 輸出走 stderr）
    )
    return (r.stdout or "").splitlines()


def mark() -> None:
    lines = _logs()
    MARK_FILE.write_text(str(len(lines)), encoding="utf-8")
    print(f"mark: {len(lines)} log lines (run scan now, then `diff`)")


def diff() -> None:
    if not MARK_FILE.exists():
        sys.exit("no mark; run `mark` before scan")
    start = int(MARK_FILE.read_text(encoding="utf-8"))
    lines = _logs()
    solved_new, solved_all = [], set()
    for idx, line in enumerate(lines):
        if line.startswith("info: Solved "):
            name = line.split(" (")[0].removeprefix("info: Solved ").strip()
            star = line.split("-star")[0].split()[-1]
            solved_all.add(name)
            if idx >= start:
                solved_new.append((name, star))
    print(f"=== this run: {len(solved_new)} new unlocks ===")
    for name, star in solved_new:
        print(f"  [NEW] {name} ({star}★)")
    print(f"=== cumulative: {len(solved_all)} unique unlocks ===")
    try:
        challenges = json.loads(
            subprocess.run(
                ["curl", "-s", "http://localhost:3000/api/challenges"],
                capture_output=True, text=True, timeout=30,
            ).stdout
        )["data"]
    except Exception:
        challenges = []
    remaining = [
        (c["name"], c["difficulty"])
        for c in challenges
        if c["name"] not in solved_all and c["name"] not in PLACEHOLDER
    ]
    remaining.sort(key=lambda x: x[1])
    print(f"=== NOT unlocked (excl. placeholders): {len(remaining)} ===")
    for name, diff_level in remaining:
        print(f"  [{diff_level}★] {name}")


if __name__ == "__main__":
    {"mark": mark, "diff": diff}[sys.argv[1]]()
