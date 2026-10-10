"""AEO 判定的回歸指標（docs/scan-upgrade-roadmap.md P0-C）。

對 `gold_dataset.ALL_CASES`（調整用案例＋保留集）跑 `evaluate_site`，與人工標註比對。
指標以「可回答」為正類：

- precision：判成可回答的題目中，真的可回答的比例（誤把非答案當答案會誤導網站主「這題沒問題」）
- recall：真的可回答的題目中，判成可回答的比例
- false_positive_rate：真的不可回答的題目中，被判成可回答的比例
- accuracy：四種判定完全一致的比例
- 成本：每個網站平均判定耗時（規則判定，不呼叫任何外部服務）

門檻 `THRESHOLDS` 由 `tests_aeo_benchmark.py` 鎖定：規則調整後任一指標掉到門檻以下，測試失敗。
門檻依資料集首次量測結果訂定（見 docs/scan-upgrade-roadmap.md P0-C），只能往上調。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from apps.scans.aeo.answers import ANSWERED, MISSING, VERDICT_LABELS
from apps.scans.aeo.evaluate import evaluate_site
from apps.scans.aeo.gold_dataset import ALL_CASES, GoldCase

THRESHOLDS = {
    "accuracy": 0.95,
    "precision": 0.95,
    "recall": 0.95,
    "false_positive_rate": 0.05,
}

NO_QUESTION = "no_question"  # 標註了，但規則根本沒出這題


@dataclass
class Judgement:
    case: str
    key: str
    expected: str
    actual: str
    tags: tuple[str, ...]
    confidence: str = ""

    @property
    def correct(self) -> bool:
        return self.expected == self.actual


@dataclass
class BenchmarkResult:
    judgements: list[Judgement] = field(default_factory=list)
    sites: int = 0
    seconds: float = 0.0

    @property
    def total(self) -> int:
        return len(self.judgements)

    def _count(self, predicate) -> int:
        return sum(1 for j in self.judgements if predicate(j))

    @property
    def accuracy(self) -> float:
        return self._count(lambda j: j.correct) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        predicted = self._count(lambda j: j.actual == ANSWERED)
        hit = self._count(lambda j: j.actual == ANSWERED and j.expected == ANSWERED)
        return hit / predicted if predicted else 1.0

    @property
    def recall(self) -> float:
        positives = self._count(lambda j: j.expected == ANSWERED)
        hit = self._count(lambda j: j.actual == ANSWERED and j.expected == ANSWERED)
        return hit / positives if positives else 1.0

    @property
    def false_positive_rate(self) -> float:
        negatives = self._count(lambda j: j.expected != ANSWERED)
        wrong = self._count(lambda j: j.expected != ANSWERED and j.actual == ANSWERED)
        return wrong / negatives if negatives else 0.0

    @property
    def avg_ms_per_site(self) -> float:
        return 1000 * self.seconds / self.sites if self.sites else 0.0

    @property
    def mismatches(self) -> list[Judgement]:
        return [j for j in self.judgements if not j.correct]

    def confusion(self) -> dict[str, dict[str, int]]:
        """confusion[人工標註][規則判定] = 題數。"""
        labels = [*VERDICT_LABELS, NO_QUESTION]
        matrix = {e: {a: 0 for a in labels} for e in VERDICT_LABELS}
        for j in self.judgements:
            matrix[j.expected][j.actual] += 1
        return matrix

    def by_tag(self) -> dict[str, tuple[int, int]]:
        """每個資料標籤（answerable、near_miss…）的 (正確題數, 題數)。"""
        out: dict[str, list[int]] = {}
        for j in self.judgements:
            for tag in j.tags:
                bucket = out.setdefault(tag, [0, 0])
                bucket[0] += int(j.correct)
                bucket[1] += 1
        return {tag: (c, n) for tag, (c, n) in out.items()}

    def precision_by_confidence(self) -> dict[str, tuple[int, int]]:
        """規則判「可回答」的題目，依可信度分組：(標註也是可回答的題數, 該組題數)。"""
        out: dict[str, list[int]] = {}
        for j in self.judgements:
            if j.actual == ANSWERED:
                bucket = out.setdefault(j.confidence, [0, 0])
                bucket[0] += int(j.expected == ANSWERED)
                bucket[1] += 1
        return {level: (hit, n) for level, (hit, n) in out.items()}

    def metrics(self) -> dict[str, float]:
        return {
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "avg_ms_per_site": round(self.avg_ms_per_site, 2),
        }

    def failed_thresholds(self) -> list[str]:
        values = self.metrics()
        failed = []
        for name, bound in THRESHOLDS.items():
            ok = values[name] <= bound if name == "false_positive_rate" else values[name] >= bound
            if not ok:
                failed.append(f"{name}={values[name]}（門檻 {bound}）")
        return failed


def _result_key(result) -> str:
    question = result.question
    return f"site:{question.text}" if question.source == "site" else question.key


def run_benchmark(cases: tuple[GoldCase, ...] = ALL_CASES) -> BenchmarkResult:
    benchmark = BenchmarkResult(sites=len(cases))
    for case in cases:
        started = time.perf_counter()
        evaluation = evaluate_site(list(case.pages))
        benchmark.seconds += time.perf_counter() - started
        results = {_result_key(r): r for r in evaluation.results}
        # 內容太少、整站不評估時，Argus 對任何題目都不宣稱有答案，視同「找不到」；
        # 記成「沒出題」會把正確的不評估當成規則漏掉（2026-10-10）
        site_not_evaluated = evaluation.status == "insufficient" and not evaluation.results
        for key, expected in case.expected.items():
            result = results.get(key)
            if result:
                actual = result.verdict
            else:
                actual = MISSING if site_not_evaluated else NO_QUESTION
            benchmark.judgements.append(
                Judgement(
                    case.name, key, expected, actual,
                    case.tags, result.confidence if result else "",
                )
            )
    return benchmark
