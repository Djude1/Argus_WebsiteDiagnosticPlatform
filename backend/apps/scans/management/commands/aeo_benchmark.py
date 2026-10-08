"""跑 AEO 判定回歸資料集並列出指標（docs/scan-upgrade-roadmap.md P0-C）。

    uv run python backend/manage.py aeo_benchmark            # 指標、各標籤正確率、不一致清單
    uv run python backend/manage.py aeo_benchmark --holdout  # 只跑保留集
    uv run python backend/manage.py aeo_benchmark --json

只做本機規則判定，不連線任何網站、不寫資料庫。任一指標低於門檻時以非零狀態結束。
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.scans.aeo.benchmark import THRESHOLDS, run_benchmark
from apps.scans.aeo.gold_dataset import ALL_CASES, HOLDOUT_CASES


class Command(BaseCommand):
    help = "跑 AEO 判定回歸資料集，輸出準確率、precision、recall、誤判率與耗時"

    def add_arguments(self, parser):
        parser.add_argument("--holdout", action="store_true", help="只跑保留集")
        parser.add_argument("--json", action="store_true", help="以 JSON 輸出")

    def handle(self, *args, **options):
        cases = HOLDOUT_CASES if options["holdout"] else ALL_CASES
        result = run_benchmark(cases)
        payload = {
            "sites": result.sites,
            "judgements": result.total,
            "metrics": result.metrics(),
            "thresholds": THRESHOLDS,
            "by_tag": {tag: {"correct": c, "total": n} for tag, (c, n) in result.by_tag().items()},
            "confusion": result.confusion(),
            # 判「可回答」的題目依可信度分組的 precision：確認 ≥ 可能 ≥ 推測 才代表可信度有意義
            "precision_by_confidence": {
                level: {"correct": c, "total": n}
                for level, (c, n) in result.precision_by_confidence().items()
            },
            "mismatches": [
                {"case": j.case, "question": j.key, "expected": j.expected, "actual": j.actual}
                for j in result.mismatches
            ],
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(f"網站 {result.sites} 個、標註題目 {result.total} 題")
            for name, value in payload["metrics"].items():
                bound = THRESHOLDS.get(name)
                self.stdout.write(f"  {name}: {value}" + (f"（門檻 {bound}）" if bound else ""))
            for tag, item in payload["by_tag"].items():
                self.stdout.write(f"  [{tag}] {item['correct']}/{item['total']}")
            for level, item in payload["precision_by_confidence"].items():
                self.stdout.write(f"  可回答（{level}）正確 {item['correct']}/{item['total']}")
            for miss in payload["mismatches"]:
                self.stdout.write(
                    f"  不一致：{miss['case']}｜{miss['question']}｜"
                    f"標註 {miss['expected']}，規則 {miss['actual']}"
                )
        failed = result.failed_thresholds()
        if failed:
            raise CommandError("低於門檻：" + "；".join(failed))
