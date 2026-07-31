"""後端服務指紋→CVE 偵測（OWASP A06 Vulnerable & Outdated Components）。

被動偵測：解析爬蟲已抓到的 response ``Server``／``X-Powered-By`` 標頭，讀出
(產品, 版本)，用 vendored NVD 衍生 DB（``data/backend_services.json``）比對已知
受影響版本區間。零額外 HTTP、零新第三方套件；任何例外 silent-fail 回 []。

版本區間比對重用 ``js_library_scanner._is_vulnerable``（同 sub-package 的穩定純函式；
DB 的 atOrAbove/below/atOrBelow 欄位與 jsrepository.json 一致），不重寫 matcher。

版本暴露（rule_id=service-version-exposed）刻意**不依賴** CVE DB——即使 DB 缺失或損壞，
只要偵測到版本就回報 LOW 暴露；如此才能完整接手 ``header_scanner`` 的 header-server-version
職責而不造成回歸（過去該 rule 不需要任何 DB 即生效）。

註：``X-Powered-By`` 的無版本值（如 ``Express``）由 ``header_scanner`` 的
header-x-powered-by 報技術棧洩露；本 scanner 只處理「帶版本」的偵測，與之不衝突。
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from apps.scans.scanners import make_finding
from apps.scans.security.js_library_scanner import _is_vulnerable

# Server / X-Powered-By：<product>/<version>（版本以數字開頭），後方可能帶 (Ubuntu) 等註記
_SERVER_RE = re.compile(r"^\s*([A-Za-z][\w.\-]*)\s*/\s*(\d[\w.\-]*)")

# 依序檢查的標頭與其顯示名稱（evidence 用）
_HEADER_SOURCES: tuple[str, ...] = ("server", "x-powered-by")
_HEADER_LABEL: dict[str, str] = {"server": "Server", "x-powered-by": "X-Powered-By"}

_DB_PATH = Path(__file__).parent / "data" / "backend_services.json"

_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_RANK_TO_CAPPED = {1: "low", 2: "medium", 3: "high", 4: "high"}


@lru_cache(maxsize=1)
def _load_db() -> dict:
    """讀 vendored 後端服務 CVE DB；檔案不存在／JSON 壞掉 → 回 {}（silent-fail）。"""
    try:
        with open(_DB_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_server(value: str) -> tuple[str, str] | None:
    """``product/version`` 字串 → (product(小寫), version)；無可辨識版本回 None。"""
    if not value:
        return None
    m = _SERVER_RE.match(str(value))
    if not m:
        return None
    return m.group(1).lower(), m.group(2)


def _build_cve_finding(
    product: str, version: str, via: str, source: str, vulns: list[dict]
) -> dict:
    """把命中的 vuln 聚合成單筆 CVE 等級 finding；per-CVE 細節進 evidence_json。"""
    cve_ids: list[str] = []
    detail: list[dict] = []
    rank = 1
    for v in vulns:
        ids = (v.get("identifiers") or {}).get("CVE") or []
        cve_ids.extend(ids)
        rank = max(rank, _SEVERITY_RANK.get((v.get("severity") or "low").lower(), 1))
        detail.append({
            "cve": ids,
            "cwe": v.get("cwe") or [],
            "severity": v.get("severity") or "low",
            "summary": (v.get("identifiers") or {}).get("summary") or "",
            "info": v.get("info") or [],
        })
    capped = _RANK_TO_CAPPED.get(rank, "low")
    cve_ids = list(dict.fromkeys(cve_ids))  # 去重保序
    if not cve_ids:
        cve_summary, cve_list = f"{len(vulns)} 項已知漏洞", "（無 CVE 編號，詳見參考連結）"
    elif len(cve_ids) <= 2:
        cve_summary = cve_list = "、".join(cve_ids)
    else:
        cve_summary, cve_list = f"{cve_ids[0]} 等 {len(cve_ids)} 項", "、".join(cve_ids)
    return make_finding(
        category="security", severity=capped, rule_id="service-known-cve",
        title=f"過時的 {product} {version} 含已知漏洞（{cve_summary}）",
        description=(
            f"偵測到後端服務 {product} {version}，此版本存在 {len(vulns)} 項已知公開漏洞"
            f"（{cve_list}）。攻擊者可利用對應漏洞對此服務發動攻擊。"
        ),
        remediation=f"將 {product} 升級至已修補的最新穩定版本，並建立定期更新流程。",
        evidence=f"{product} {version}（{via}；來源：{source}）；命中：{cve_list}",
        evidence_json={
            "product": product, "version": version, "detected_from": source, "via": via,
            "vulnerabilities": detail,
        },
        impact_area="vulnerability",
    )


def _exposure_finding(product: str, version: str, via: str, source: str) -> dict:
    """無 CVE 命中（或 DB 缺失）時的版本暴露 LOW finding。"""
    return make_finding(
        category="security", severity="low", rule_id="service-version-exposed",
        title=f"{product} {version} 版本資訊外洩",
        description=(
            f"回應標頭 {via} 洩露了 {product} {version}，攻擊者可據此比對已知漏洞。"
            "目前雖比對不到已知 CVE，仍建議遮蔽以減少資訊暴露。"
        ),
        remediation=f"移除或遮蔽 {via} 標頭的版本字串。",
        evidence=f"{via}: {product}/{version}（來源：{source}）",
        impact_area="vulnerability",
    )


def analyze_services(pages: list[dict]) -> list[dict]:
    """偵測後端服務版本並比對已知 CVE；任何例外 silent-fail 回 []。

    依次檢查每頁的 ``Server`` 與 ``X-Powered-By``；版本暴露（LOW）不依賴 CVE DB：
    DB 缺失時仍回報暴露，僅缺 CVE 形成。以 (product, version) 去重，整個 scan 同一
    版本只開一張 finding。
    """
    try:
        db = _load_db()
        if not pages:
            return []
        seen: set[tuple[str, str]] = set()
        out: list[dict] = []
        for page in pages:
            headers = (page or {}).get("headers") or {}
            source = (page or {}).get("final_url") or (page or {}).get("url") or ""
            for hkey in _HEADER_SOURCES:
                parsed = _parse_server(headers.get(hkey, ""))
                if not parsed:
                    continue
                product, version = parsed
                if (product, version) in seen:
                    continue
                comp = db.get(product)
                matched = (
                    [v for v in (comp.get("vulnerabilities") or []) if _is_vulnerable(version, v)]
                    if isinstance(comp, dict) else []
                )
                seen.add((product, version))
                label = _HEADER_LABEL[hkey]
                out.append(
                    _build_cve_finding(product, version, label, source, matched) if matched
                    else _exposure_finding(product, version, label, source)
                )
        return out
    except Exception:
        return []
