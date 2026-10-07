"""跑網站特徵（fingerprint）準確率資料集並列出指標（ADR-0004 階段 1）。

    uv run python backend/manage.py fingerprint_benchmark            # 指標、各特徵、不一致清單
    uv run python backend/manage.py fingerprint_benchmark --holdout  # 只跑保留集
    uv run python backend/manage.py fingerprint_benchmark --json

只做本機判定，不連線任何網站、不寫資料庫。任一指標低於門檻或有連線嘗試時以非零狀態結束。
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.scans.fingerprint_benchmark import THRESHOLDS, run_fingerprint_benchmark
from apps.scans.fingerprint_gold import ALL_CASES, HOLDOUT_CASES


class Command(BaseCommand):
    help = "跑網站特徵資料集，輸出 precision、recall、未知比例、耗時與連線次數"

    def add_arguments(self, parser):
        parser.add_argument("--holdout", action="store_true", help="只跑保留集")
        parser.add_argument("--json", action="store_true", help="以 JSON 輸出")

    def handle(self, *args, **options):
        cases = HOLDOUT_CASES if options["holdout"] else ALL_CASES
        result = run_fingerprint_benchmark(cases)
        payload = {
            "sites": result.sites,
            "metrics": result.metrics(),
            "thresholds": THRESHOLDS,
            "features": result.per_feature(),
            "mismatches": [
                {"case": m.case, "feature": m.feature, "expected": m.expected, "actual": m.actual}
                for m in result.mismatches
            ],
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            self.stdout.write(f"網站 {result.sites} 個")
            for name, value in payload["metrics"].items():
                bound = THRESHOLDS.get(name)
                self.stdout.write(f"  {name}: {value}" + (f"（門檻 {bound}）" if bound else ""))
            for name, item in payload["features"].items():
                self.stdout.write(
                    f"  [{name}] precision {item['precision']}、recall {item['recall']}"
                    f"（TP {item['tp']}／FP {item['fp']}／FN {item['fn']}）"
                )
            for miss in payload["mismatches"]:
                self.stdout.write(
                    f"  不一致：{miss['case']}｜{miss['feature']}｜"
                    f"標註 {miss['expected']}，判定 {miss['actual']}"
                )
        failed = result.failed_thresholds()
        if failed:
            raise CommandError("低於門檻：" + "；".join(failed))
