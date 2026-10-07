"""網站特徵（fingerprint）準確率指標（ADR-0004 階段 1 的成功條件）。

對 `fingerprint_gold.ALL_CASES` 跑 `build_fingerprint`，逐項特徵與人工標註比對：

- precision：判定「有」的特徵中，真的有的比例（階段 2 會依此加掃，誤判＝多花點數與流量）
- recall：真的有的特徵中，判定出來的比例
- unknown_rate：登入／API／上傳三個是非題中，回 None（沒看到）的比例；只是觀察值，不設門檻
- avg_ms_per_site：每個網站的判定耗時
- requests：判定過程中嘗試建立的網路連線數，必須是 0

CMS、邊緣服務、驗證方式是單值：判對＝TP；判成別的值＝FP＋FN。frameworks 逐項比對。
門檻 `THRESHOLDS` 由 `tests_fingerprint.py` 鎖定，只能往上調。
"""

from __future__ import annotations

import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from unittest import mock

from apps.scans.fingerprint import build_fingerprint
from apps.scans.fingerprint_gold import ALL_CASES, FingerprintCase

THRESHOLDS = {"precision": 0.95, "recall": 0.95}
SINGLE = ("cms", "edge", "auth_scheme")
BOOLEAN = ("has_login", "has_api", "has_upload")
FEATURES = (*SINGLE, "frameworks", *BOOLEAN)


@dataclass
class Mismatch:
    case: str
    feature: str
    expected: object
    actual: object


@dataclass
class FeatureCount:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


@dataclass
class FingerprintBenchmark:
    sites: int = 0
    seconds: float = 0.0
    requests: int = 0
    unknown: int = 0
    boolean_slots: int = 0
    counts: dict[str, FeatureCount] = field(
        default_factory=lambda: {f: FeatureCount() for f in FEATURES}
    )
    mismatches: list[Mismatch] = field(default_factory=list)

    def _total(self) -> FeatureCount:
        total = FeatureCount()
        for count in self.counts.values():
            total.tp += count.tp
            total.fp += count.fp
            total.fn += count.fn
        return total

    def metrics(self) -> dict[str, float]:
        total = self._total()
        return {
            "precision": round(total.precision, 4),
            "recall": round(total.recall, 4),
            "unknown_rate": (
                round(self.unknown / self.boolean_slots, 4) if self.boolean_slots else 0
            ),
            "avg_ms_per_site": round(1000 * self.seconds / self.sites, 3) if self.sites else 0,
            "requests": self.requests,
        }

    def per_feature(self) -> dict[str, dict[str, float]]:
        return {
            name: {"precision": round(c.precision, 4), "recall": round(c.recall, 4),
                   "tp": c.tp, "fp": c.fp, "fn": c.fn}
            for name, c in self.counts.items()
        }

    def failed_thresholds(self) -> list[str]:
        values = self.metrics()
        failed = [f"{k}={values[k]}（門檻 {v}）" for k, v in THRESHOLDS.items() if values[k] < v]
        if self.requests:
            failed.append(f"requests={self.requests}（必須是 0）")
        return failed


@contextmanager
def _count_connections(benchmark: FingerprintBenchmark):
    """判定期間任何連線嘗試都記一次並擋下，證明特徵整理不會對目標發請求。"""

    def _blocked(*_args, **_kwargs):
        benchmark.requests += 1
        raise OSError("fingerprint 不得建立網路連線")

    with mock.patch.object(socket.socket, "connect", _blocked), \
            mock.patch.object(socket, "create_connection", _blocked), \
            mock.patch.object(socket, "getaddrinfo", _blocked):
        yield


def _score(benchmark: FingerprintBenchmark, case: FingerprintCase, actual: dict) -> None:
    for name in (*SINGLE, *BOOLEAN):
        want, got = case.expected[name], actual[name]
        count = benchmark.counts[name]
        if want and got == want:
            count.tp += 1
        else:
            if got:
                count.fp += 1
            if want:
                count.fn += 1
            if want != got:
                benchmark.mismatches.append(Mismatch(case.name, name, want, got))
    want_fw, got_fw = set(case.expected["frameworks"]), set(actual["frameworks"])
    count = benchmark.counts["frameworks"]
    count.tp += len(want_fw & got_fw)
    count.fp += len(got_fw - want_fw)
    count.fn += len(want_fw - got_fw)
    if want_fw != got_fw:
        benchmark.mismatches.append(
            Mismatch(case.name, "frameworks", sorted(want_fw), sorted(got_fw))
        )
    for name in BOOLEAN:
        benchmark.boolean_slots += 1
        benchmark.unknown += actual[name] is None


def run_fingerprint_benchmark(
    cases: tuple[FingerprintCase, ...] = ALL_CASES,
) -> FingerprintBenchmark:
    benchmark = FingerprintBenchmark(sites=len(cases))
    with _count_connections(benchmark):
        for case in cases:
            started = time.perf_counter()
            fingerprint = build_fingerprint(list(case.pages), list(case.endpoints))
            benchmark.seconds += time.perf_counter() - started
            _score(benchmark, case, fingerprint.as_dict())
    return benchmark
