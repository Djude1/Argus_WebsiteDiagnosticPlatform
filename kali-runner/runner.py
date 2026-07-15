"""Argus Kali SQLmap runner —— 在受限的 Kubernetes Job 內獨立執行 SQLmap。

設計目標：
- **純標準庫**：只用 ``sys / json / re / socket / subprocess / urllib.parse / ipaddress``，
  不依賴任何第三方套件，方便在 host 端用 ``python -m unittest`` 直接跑單元測試。
- **深層防禦**：上層（``kali_policy``）已驗證過目標；本 runner 在啟動前再驗一次
  公開 HTTP(S) / 80,443 / 無 userinfo / DNS 全公開 / 帶 query / 同源。任一不符就以
  snake_case 安全錯誤碼回報，絕不洩漏細節。
- **不外洩原始輸出**：sqlmap stdout 只在本 process 內解析出符合契約的安全摘要；
  raw stdout / 完整 query value / HTTP body / 資料庫列值一律不寫入最終 stdout。
- **固定 schema**：最終 stdout 為一份 ≤ 16384 bytes 的 UTF-8 JSON，頂層鍵恆為
  ``{schema_version, tool, results}``，每筆 result 恰為 8 個鍵，欄位格式符合
  ``backend/apps/scans/security/kali_contracts.py::parse_runner_result`` 的契約。
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import subprocess
import sys
import urllib.parse
from collections.abc import Sequence
from typing import Any

# ---------------------------------------------------------------------------
# Constants —— 與契約 / brief 一致，不可隨意改動。
# ---------------------------------------------------------------------------

TARGETS_PATH = "/run/argus-targets/targets.json"
MAX_RESULT_BYTES = 16384
MAX_TARGETS = 3
SQLMAP_TIMEOUT_SECONDS = 120

# --self-test 必須印出這份固定 payload，且不可讀 targets 檔或啟動 sqlmap。
SELF_TEST_PAYLOAD = '{"schema_version":1,"tool":"sqlmap","results":[]}'

# sqlmap 技術名稱白名名單（與 kali_contracts SAFE_TECHNIQUES 對齊）。
SAFE_TECHNIQUES = frozenset({
    "boolean-based blind",
    "error-based",
    "inline query",
    "stacked queries",
    "time-based blind",
    "union query",
})

# 契約 regex：parameter / dbms / error_code 的安全字元集。
_PARAMETER_RE = re.compile(r"[A-Za-z0-9_.-]{0,64}")
_DBMS_RE = re.compile(r"[A-Za-z0-9 ._-]{0,64}")
_ERROR_CODE_RE = re.compile(r"[a-z0-9_]{0,64}")

# 當正常彙整後的輸出仍超過 16384 bytes 時，每筆 result 一律退化為此 placeholder，
# 並以 ``runner_output_too_large`` 標記。executor 端會把它映射成 outward runner_failed。
PLACEHOLDER_ERROR_CODE = "runner_output_too_large"

_ALLOWED_SCHEMES = {"http", "https"}
_PUBLIC_PORTS = {80, 443}
_SCHEME_DEFAULT_PORT = {"http": 80, "https": 443}


# ---------------------------------------------------------------------------
# 命令建構
# ---------------------------------------------------------------------------

def command_for(index: int, target_url: str) -> list[str]:
    """組裝 sqlmap 命令（固定 level/risk/threads，避免不必要的風險與流量）。

    不同 ``index`` 使用獨立的 ``--output-dir`` 與 ``--flush-session``，避免 session
    在同一個 batch 內交叉污染。
    """
    return [
        sys.executable, "/opt/sqlmap/sqlmap.py", "-u", target_url,
        "--batch", "--flush-session", f"--output-dir=/tmp/sqlmap-{index}",
        "--disable-coloring", "--level=1", "--risk=1", "--threads=1",
        "--timeout=10", "--retries=1",
        "--user-agent=SiteSense-AI-Scanner/1.0 (authorized-audit)",
    ]


# ---------------------------------------------------------------------------
# sqlmap stdout 解析（只擷取白名單內的安全摘要）
# ---------------------------------------------------------------------------

def _clip(text: str, regex: re.Pattern[str]) -> str:
    match = regex.match(text)
    return match.group(0) if match else ""


def parse_sqlmap_stdout(
    stdout: str,
) -> tuple[str, list[str], str, bool]:
    """從 sqlmap stdout 擷取 ``(parameter, techniques, dbms, confirmed)``。

    只辨識少數高危險標記；其餘內容（含可能含有 PII / DB row / query value 的行）
    一律丟棄，不會進入回傳值。同一參數名只記第一個；technique 重複也去複。
    """
    parameter = ""
    techniques: list[str] = []
    dbms = ""
    confirmed = False
    for raw_line in stdout.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        # `Parameter: id (GET)` —— 只記第一個參數名（剝掉括號內的 method 註記）。
        if stripped.startswith("Parameter:") and not parameter:
            tail = stripped[len("Parameter:"):]
            paren = tail.find("(")
            name = tail[:paren].strip() if paren != -1 else tail.strip()
            parameter = _clip(name, _PARAMETER_RE)
        elif stripped.startswith("Type:"):
            technique = stripped[len("Type:"):].strip()
            if technique in SAFE_TECHNIQUES and technique not in techniques:
                techniques.append(technique)
        elif stripped.startswith("back-end DBMS:"):
            dbms = _clip(
                stripped[len("back-end DBMS:"):].strip(), _DBMS_RE,
            )
        elif "is vulnerable" in stripped:
            confirmed = True
    return parameter, techniques, dbms, confirmed


# ---------------------------------------------------------------------------
# 單一目標執行
# ---------------------------------------------------------------------------

def _result_item(
    index: int,
    *,
    ok: bool,
    confirmed: bool = False,
    returncode: int | None = None,
    parameter: str = "",
    techniques: list[str] | None = None,
    dbms: str = "",
    error_code: str = "",
) -> dict[str, Any]:
    """以 8 鍵契約格式組裝單筆 result。"""
    return {
        "index": index,
        "ok": ok,
        "confirmed": confirmed,
        "returncode": returncode,
        "parameter": parameter,
        "techniques": list(techniques or []),
        "dbms": dbms,
        "error_code": error_code,
    }


def run_target(index: int, target_url: str) -> dict[str, Any]:
    """對單一目標執行 sqlmap 並回傳符合契約的安全結果 dict。

    - 逾時 → ``runner_timeout``
    - 其他例外 → ``runner_failure``
    - returncode != 0 → ``runner_failure``（攜帶 returncode）
    - returncode == 0 → ``ok=True``，依 sqlmap stdout 決定 ``confirmed``、``parameter``
      與 ``techniques``；``error_code`` 一律為空字串。
    """
    try:
        completed = subprocess.run(
            command_for(index, target_url),
            capture_output=True,
            text=True,
            timeout=SQLMAP_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _result_item(index, ok=False, error_code="runner_timeout")
    except Exception:
        return _result_item(index, ok=False, error_code="runner_failure")

    returncode = completed.returncode
    # capture_output=True + text=True 保證 stdout/stderr 為 str；不直接寫入結果。
    parameter, techniques, dbms, confirmed = parse_sqlmap_stdout(
        completed.stdout or "",
    )
    if returncode != 0:
        return _result_item(
            index, ok=False, returncode=returncode,
            error_code="runner_failure",
        )
    return _result_item(
        index, ok=True, confirmed=confirmed, returncode=returncode,
        parameter=parameter, techniques=techniques, dbms=dbms,
        error_code="",
    )


# ---------------------------------------------------------------------------
# Batch 驗證（深層防禦：上層 policy 已驗，本 runner 再驗一次）
# ---------------------------------------------------------------------------

def _is_public_ip(ip: str) -> bool:
    """判定位址是否為可路由的公開位址。

    沿用設計規格的「private、loopback、link-local、multicast、reserved、unspecified」
    全部拒絕；這也覆蓋了常見的雲端 metadata 端點（169.254.169.254 為 link-local）。
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _all_dns_results_public(host: str) -> bool:
    """``host`` 的**所有** DNS 解析結果都必須是公開可路由位址。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, socket.herror, OSError):
        return False
    if not infos:
        return False
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if not _is_public_ip(ip):
            return False
    return True


def validate_batch(targets: Sequence[tuple[int, str]]) -> str | None:
    """檢查整批目標是否同時滿足安全條件。

    回傳 ``None`` 代表全數通過；否則回傳 snake_case 錯誤碼（符合契約的
    ``[a-z0-9_]{0,64}``）。任一規則失敗即 short-circuit，不揭示其他目標資訊。
    """
    if not targets:
        return "no_targets"

    origins: list[tuple[str, str, int]] = []
    for _index, url in targets:
        try:
            parsed = urllib.parse.urlsplit(url)
        except ValueError:
            return "malformed_url"
        scheme = (parsed.scheme or "").lower()
        # 無 scheme（空字串）視為格式錯誤；有 scheme 但非 http/https 才算 invalid_scheme。
        if not scheme:
            return "malformed_url"
        if scheme not in _ALLOWED_SCHEMES:
            return "invalid_scheme"
        if parsed.username or parsed.password:
            return "userinfo_forbidden"
        host = parsed.hostname
        if not host:
            return "malformed_url"
        try:
            explicit_port = parsed.port
        except ValueError:
            return "invalid_port"
        if explicit_port is None:
            port = _SCHEME_DEFAULT_PORT[scheme]
        elif explicit_port not in _PUBLIC_PORTS:
            return "invalid_port"
        else:
            port = explicit_port
        if not parsed.query:
            return "no_query_parameter"
        if not _all_dns_results_public(host):
            return "target_not_public"
        origins.append((scheme, host, port))

    first_origin = origins[0]
    for origin in origins[1:]:
        if origin != first_origin:
            return "cross_origin_forbidden"
    return None


# ---------------------------------------------------------------------------
# Output 序列化與 16384-byte size guard
# ---------------------------------------------------------------------------

def _placeholder(index: int) -> dict[str, Any]:
    """當輸出超過 16384 bytes 時用來取代每筆 result 的最小 placeholder。"""
    return {
        "index": index,
        "ok": False,
        "confirmed": False,
        "returncode": None,
        "parameter": "",
        "techniques": [],
        "dbms": "",
        "error_code": PLACEHOLDER_ERROR_CODE,
    }


def serialize_output(results: list[dict[str, Any]]) -> bytes:
    """將 results 序列化為 compact UTF-8 bytes，並在超過上限時退化為 placeholders。

    不論結果多大，最終 bytes 一定 ≤ ``MAX_RESULT_BYTES``，且 schema 維持
    ``{"schema_version":1,"tool":"sqlmap","results":[...]}``。
    """
    document = {
        "schema_version": 1,
        "tool": "sqlmap",
        "results": results,
    }
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= MAX_RESULT_BYTES:
        return encoded
    placeholders = [_placeholder(item["index"]) for item in results]
    fallback = json.dumps(
        {"schema_version": 1, "tool": "sqlmap", "results": placeholders},
        separators=(",", ":"),
    ).encode("utf-8")
    return fallback


# ---------------------------------------------------------------------------
# Input 讀取與正規化
# ---------------------------------------------------------------------------

def _empty_payload_bytes() -> bytes:
    """產生格式正確但 results 為空的 payload bytes（用於 malformed / 超量輸入）。"""
    return SELF_TEST_PAYLOAD.encode("utf-8")


def _normalize_targets(
    raw_targets: object,
) -> tuple[list[tuple[int, str]], bytes | None]:
    """把輸入的 targets 正規化為 ``[(index, url), ...]``。

    回傳 ``(normalized, None)`` 代表成功；回傳 ``(normalized_or_empty, error_payload)``
    代表輸入不符契約（呼叫端應直接印出 ``error_payload`` 並結束）。
    """
    if not isinstance(raw_targets, list):
        return [], _empty_payload_bytes()
    if not raw_targets:
        return [], _empty_payload_bytes()
    if len(raw_targets) > MAX_TARGETS:
        return [], _empty_payload_bytes()

    normalized: list[tuple[int, str]] = []
    seen_indices: set[int] = set()
    for entry in raw_targets:
        if not isinstance(entry, dict):
            return [], _empty_payload_bytes()
        index = entry.get("index")
        url = entry.get("url")
        # 嚴格型別：index 必須是 int（不允許 bool），url 必須是 str。
        if not isinstance(index, int) or isinstance(index, bool):
            return [], _empty_payload_bytes()
        if not isinstance(url, str):
            return [], _empty_payload_bytes()
        if index in seen_indices:
            return [], _empty_payload_bytes()
        seen_indices.add(index)
        normalized.append((index, url))
    return normalized, None


def _read_input_document(path: str) -> tuple[object, bytes | None]:
    """讀取 ``targets.json``；失敗時回傳可用來直接輸出的空 payload bytes。"""
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, _empty_payload_bytes()
    if not isinstance(document, dict):
        return None, _empty_payload_bytes()
    if document.get("schema_version") != 1:
        return None, _empty_payload_bytes()
    return document, None


# ---------------------------------------------------------------------------
# main() —— K8s Pod 內 ENTRYPOINT
# ---------------------------------------------------------------------------

def main(argv: Sequence[str]) -> int:
    """runner ENTRYPOINT；支援 ``--self-test`` 與正常 batch 執行。"""
    if "--self-test" in argv:
        # 不讀 targets 檔、不啟動 sqlmap，直接印出固定 payload。
        sys.stdout.write(SELF_TEST_PAYLOAD)
        return 0

    document, error_payload = _read_input_document(TARGETS_PATH)
    if error_payload is not None:
        sys.stdout.write(error_payload.decode("utf-8"))
        return 0

    targets, error_payload = _normalize_targets(document.get("targets"))
    if error_payload is not None:
        sys.stdout.write(error_payload.decode("utf-8"))
        return 0

    validation_error = validate_batch(targets)
    if validation_error is not None:
        # 驗證失敗：每筆 result 都帶同一個 snake_case 錯誤碼，不揭示哪一目標觸發。
        results = [
            _result_item(index, ok=False, error_code=validation_error)
            for index, _url in targets
        ]
        sys.stdout.write(serialize_output(results).decode("utf-8"))
        return 0

    results = [run_target(index, url) for index, url in targets]
    sys.stdout.write(serialize_output(results).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
