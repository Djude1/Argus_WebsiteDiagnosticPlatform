"""Kali SQLmap 執行器共用的安全資料契約。"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings

MAX_RESULT_BYTES = 16_384
_RESULT_KEYS = {
    "index",
    "ok",
    "confirmed",
    "returncode",
    "parameter",
    "techniques",
    "dbms",
    "error_code",
}
SAFE_TECHNIQUES = {
    "boolean-based blind",
    "error-based",
    "inline query",
    "stacked queries",
    "time-based blind",
    "union query",
}


class KaliResultContractError(ValueError):
    """Runner 結果不符合安全契約。"""


@dataclass(frozen=True)
class ReservedSqlmapTarget:
    index: int
    url: str
    fingerprint: str


@dataclass(frozen=True)
class KaliResult:
    ok: bool
    tool: str = "sqlmap"
    blocked_reason: str = ""
    returncode: int | None = None
    stdout: str = ""
    error: str = ""
    confirmed: bool = False
    evidence_summary: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "blocked_reason": self.blocked_reason,
            "returncode": self.returncode,
            "stdout": "",
            "error": self.error,
            "confirmed": self.confirmed,
            "evidence_summary": dict(self.evidence_summary),
        }


@dataclass(frozen=True)
class SqlmapExecution:
    target: ReservedSqlmapTarget
    result: KaliResult


@dataclass(frozen=True)
class ReservationOutcome:
    targets: tuple[ReservedSqlmapTarget, ...] = ()
    blocked_reason: str = ""


class SqlmapExecutor(Protocol):
    def execute(
        self,
        scan_job_id: int,
        targets: Sequence[ReservedSqlmapTarget],
    ) -> tuple[KaliResult, ...]: ...


def redact_url_query_values(url: str) -> str:
    parsed = urlsplit(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode([(key, "[REDACTED]") for key, _value in pairs])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def parse_runner_result(
    payload: bytes,
    expected_targets: Sequence[ReservedSqlmapTarget],
) -> tuple[KaliResult, ...]:
    if len(payload) > settings.ARGUS_KALI_RESULT_MAX_BYTES:
        raise KaliResultContractError("result_too_large")
    try:
        document = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KaliResultContractError("invalid_result") from exc
    if not isinstance(document, dict):
        raise KaliResultContractError("invalid_result_type")
    if set(document) != {"schema_version", "tool", "results"}:
        raise KaliResultContractError("invalid_top_level_fields")
    if document["schema_version"] != 1 or document["tool"] != "sqlmap":
        raise KaliResultContractError("unknown_schema")
    if not isinstance(document["results"], list):
        raise KaliResultContractError("invalid_result_type")

    expected = {target.index: target for target in expected_targets}
    parsed: dict[int, KaliResult] = {}
    for item in document["results"]:
        if not isinstance(item, dict):
            raise KaliResultContractError("invalid_result_type")
        if set(item) != _RESULT_KEYS:
            raise KaliResultContractError("invalid_result_fields")
        index = item["index"]
        if not isinstance(index, int) or isinstance(index, bool) or index not in expected:
            raise KaliResultContractError("unexpected_index")
        if index in parsed:
            raise KaliResultContractError("duplicate_index")
        if not isinstance(item["ok"], bool) or not isinstance(item["confirmed"], bool):
            raise KaliResultContractError("invalid_result_type")
        returncode = item["returncode"]
        if returncode is not None and (
            not isinstance(returncode, int) or isinstance(returncode, bool)
        ):
            raise KaliResultContractError("invalid_result_type")
        parameter = item["parameter"]
        techniques = item["techniques"]
        dbms = item["dbms"]
        error_code = item["error_code"]
        if not isinstance(parameter, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{0,64}", parameter
        ):
            raise KaliResultContractError("unsafe_parameter")
        if not isinstance(techniques, list) or any(
            not isinstance(value, str) or value not in SAFE_TECHNIQUES
            for value in techniques
        ):
            raise KaliResultContractError("invalid_techniques")
        if not isinstance(dbms, str) or not re.fullmatch(
            r"[A-Za-z0-9 ._-]{0,64}", dbms
        ):
            raise KaliResultContractError("unsafe_dbms")
        if not isinstance(error_code, str) or not re.fullmatch(
            r"[a-z0-9_]{0,64}", error_code
        ):
            raise KaliResultContractError("unsafe_error_code")
        parsed[index] = KaliResult(
            ok=item["ok"],
            returncode=returncode,
            confirmed=item["confirmed"],
            error=error_code,
            evidence_summary={
                "parameter": parameter,
                "techniques": techniques,
                "dbms": dbms,
            },
        )
    if set(parsed) != set(expected):
        raise KaliResultContractError("missing_index")
    return tuple(parsed[target.index] for target in expected_targets)
