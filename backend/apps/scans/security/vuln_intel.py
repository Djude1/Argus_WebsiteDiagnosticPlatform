"""已知漏洞的優先序補強：EPSS 被利用機率＋OSV.dev 修補版本（roadmap §5 第 3 項、P2）。

只補強 `js-lib-known-vuln`（Retire.js 離線比對）與 `service-known-cve`（NVD 離線比對）兩種 finding，
**不改嚴重度**（嚴重度仍依漏洞本身），只做三件事：

- **EPSS**（FIRST.org）：每個 CVE 未來 30 天被實際利用的機率與百分位。finding 取最高值寫進
  `evidence_json["epss"]`，並調整 `priority_score`：同樣嚴重度下，越可能被利用的排越前面。
- **OSV.dev**（只查 npm 套件，也就是前端函式庫）：這個版本受哪些公告影響、最低修補版本。
  修補版本寫進修法（「升級至 X 以上」）；OSV 有、Retire.js 沒列的公告只記數量，不拿來提高嚴重度。
- 兩者查不到或服務無法連線時原樣保留 finding，`evidence_json["vuln_intel"]` 註明原因。

送出的只有函式庫名稱、版本與 CVE 編號，**不含受測網址或頁面內容**。結果以 Django cache 保存
`ARGUS_VULN_INTEL_CACHE_SECONDS`（預設 1 天，EPSS 每日更新）。
"""

from __future__ import annotations

import logging

import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

EPSS_URL = "https://api.first.org/data/v1/epss"
OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"
TARGET_RULES = ("js-lib-known-vuln", "service-known-cve")
MAX_OSV_DETAILS = 20  # 每次掃描最多查幾筆公告的修補版本
EPSS_PRIORITY_BOOST = 14

# Retire.js 元件名稱 → npm 套件名稱（沒列的同名）
_NPM_NAMES = {
    "angularjs": "angular",
    "backbone.js": "backbone",
    "moment.js": "moment",
    "mustache.js": "mustache",
    "underscore.js": "underscore",
    "jquery.datatables": "datatables.net",
    "nextjs": "next",
    "pdf.js": "pdfjs-dist",
    "threejs": "three",
    "tinyMCE": "tinymce",
    "highlightjs": "highlight.js",
    "jquery-ui-autocomplete": "jquery-ui",
    "jquery-ui-dialog": "jquery-ui",
    "jquery-ui-tooltip": "jquery-ui",
    "DOMPurify": "dompurify",
}


class _Unavailable(Exception):
    pass


def enabled() -> bool:
    return bool(settings.ARGUS_VULN_INTEL_ENABLED)


def _client() -> httpx.Client:
    return httpx.Client(timeout=settings.ARGUS_VULN_INTEL_TIMEOUT_SECONDS)


def _cache_key(kind: str, value: str) -> str:
    return f"argus-vuln-intel:{kind}:{value}"


def fetch_epss(cve_ids: list[str], client: httpx.Client) -> dict[str, dict]:
    """{CVE: {"epss": 0–1, "percentile": 0–1, "date": "YYYY-MM-DD"}}；沒有分數的 CVE 不列。"""
    out: dict[str, dict] = {}
    missing = []
    for cve in cve_ids:
        cached = cache.get(_cache_key("epss", cve))
        if cached is not None:
            if cached:
                out[cve] = cached
        else:
            missing.append(cve)
    for start in range(0, len(missing), 100):
        chunk = missing[start:start + 100]
        try:
            response = client.get(EPSS_URL, params={"cve": ",".join(chunk)})
            response.raise_for_status()
            rows = response.json().get("data") or []
        except (httpx.HTTPError, ValueError) as exc:
            raise _Unavailable(f"EPSS 無法查詢（{exc.__class__.__name__}）") from exc
        found = {}
        for row in rows:
            try:
                found[row["cve"]] = {
                    "epss": float(row["epss"]),
                    "percentile": float(row["percentile"]),
                    "date": row.get("date", ""),
                }
            except (KeyError, TypeError, ValueError):
                continue
        for cve in chunk:
            # 查過但沒有分數（太新或保留中的 CVE）也快取，避免每次掃描重查
            cache.set(_cache_key("epss", cve), found.get(cve, {}),
                      settings.ARGUS_VULN_INTEL_CACHE_SECONDS)
        out.update(found)
    return out


def _version_key(version: str) -> tuple:
    parts = []
    for piece in version.replace("-", ".").split("."):
        parts.append((0, int(piece), "") if piece.isdigit() else (1, 0, piece))
    return tuple(parts)


def _osv_vuln(vuln_id: str, client: httpx.Client) -> dict:
    cached = cache.get(_cache_key("osv-vuln", vuln_id))
    if cached is not None:
        return cached
    try:
        response = client.get(OSV_VULN_URL.format(id=vuln_id))
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise _Unavailable(f"OSV.dev 無法查詢（{exc.__class__.__name__}）") from exc
    slim = {"id": data.get("id", vuln_id), "aliases": data.get("aliases") or [],
            "affected": data.get("affected") or []}
    cache.set(_cache_key("osv-vuln", vuln_id), slim, settings.ARGUS_VULN_INTEL_CACHE_SECONDS)
    return slim


def _fixed_versions(vuln: dict, package: str, version: str) -> list[str]:
    """這個公告中，涵蓋目前版本的區間的修補版本。"""
    fixed = []
    current = _version_key(version)
    for affected in vuln.get("affected") or []:
        pkg = affected.get("package") or {}
        if pkg.get("ecosystem") != "npm" or pkg.get("name") != package:
            continue
        for rng in affected.get("ranges") or []:
            introduced = None
            for event in rng.get("events") or []:
                if "introduced" in event:
                    introduced = event["introduced"]
                elif "fixed" in event and introduced is not None:
                    # "0" 代表從最早的版本就受影響；空 tuple 比任何版本都小
                    low = () if introduced == "0" else _version_key(introduced)
                    if low <= current < _version_key(event["fixed"]):
                        fixed.append(event["fixed"])
                    introduced = None
    return fixed


def fetch_osv(packages: list[tuple[str, str]], client: httpx.Client) -> dict[tuple, dict]:
    """{(npm 名稱, 版本): {"ids": [...], "aliases": {...}, "fixed": "x.y.z" 或 ""}}。"""
    out: dict[tuple, dict] = {}
    pending = []
    for package in packages:
        cached = cache.get(_cache_key("osv-pkg", f"{package[0]}@{package[1]}"))
        if cached is not None:
            out[package] = cached
        else:
            pending.append(package)
    if pending:
        try:
            response = client.post(OSV_BATCH_URL, json={"queries": [
                {"package": {"ecosystem": "npm", "name": name}, "version": version}
                for name, version in pending
            ]})
            response.raise_for_status()
            results = response.json().get("results") or []
        except (httpx.HTTPError, ValueError) as exc:
            raise _Unavailable(f"OSV.dev 無法查詢（{exc.__class__.__name__}）") from exc
        budget = MAX_OSV_DETAILS
        for package, result in zip(pending, results, strict=False):
            ids = [v["id"] for v in (result or {}).get("vulns") or [] if v.get("id")]
            aliases: set[str] = set()
            fixed: list[str] = []
            for vuln_id in ids:
                if budget <= 0:
                    break
                budget -= 1
                vuln = _osv_vuln(vuln_id, client)
                aliases.update(a for a in vuln["aliases"] if a.startswith("CVE-"))
                fixed += _fixed_versions(vuln, *package)
            entry = {
                "ids": ids,
                "cves": sorted(aliases),
                # 要全部修好，得升到所有公告修補版本中最高的那個
                "fixed": max(fixed, key=_version_key) if fixed else "",
            }
            cache.set(_cache_key("osv-pkg", f"{package[0]}@{package[1]}"), entry,
                      settings.ARGUS_VULN_INTEL_CACHE_SECONDS)
            out[package] = entry
    return out


def _cves(finding: dict) -> list[str]:
    ids = []
    for vuln in (finding.get("evidence_json") or {}).get("vulnerabilities") or []:
        ids += [c for c in vuln.get("cve") or [] if str(c).startswith("CVE-")]
    return list(dict.fromkeys(ids))


def _npm_package(finding: dict) -> tuple[str, str] | None:
    data = finding.get("evidence_json") or {}
    if finding.get("rule_id") != "js-lib-known-vuln" or not data.get("library"):
        return None
    name = data["library"]
    return _NPM_NAMES.get(name, name), str(data.get("version", ""))


def _apply_epss(finding: dict, scores: dict[str, dict]) -> None:
    data = finding["evidence_json"]
    for vuln in data.get("vulnerabilities") or []:
        best = max((scores[c] for c in vuln.get("cve") or [] if c in scores),
                   key=lambda s: s["epss"], default=None)
        if best:
            vuln["epss"] = best
    hits = [(cve, scores[cve]) for cve in _cves(finding) if cve in scores]
    if not hits:
        return
    cve, top = max(hits, key=lambda item: item[1]["epss"])
    data["epss"] = {"cve": cve, **top}
    # 同嚴重度內依被利用機率排序：最多加 EPSS_PRIORITY_BOOST 分，小於嚴重度之間的最小間距
    # （scanners._SEVERITY_DEFAULT_PRIORITY：critical 90／high 75…），不會越過更高的嚴重度
    finding["priority_score"] = round(
        float(finding.get("priority_score") or 0) + EPSS_PRIORITY_BOOST * top["epss"], 2
    )
    finding["description"] += (
        f"依 EPSS（FIRST.org，{top['date']}），其中 {cve} 未來 30 天被實際利用的機率約"
        f" {top['epss'] * 100:.1f}%，高於 {int(top['percentile'] * 100)}% 的已知漏洞。"
    )


def _apply_osv(finding: dict, entry: dict, package: str) -> None:
    data = finding["evidence_json"]
    known = set(_cves(finding))
    data["osv"] = {
        "package": package,
        "advisories": len(entry["ids"]),
        "extra_cves": [c for c in entry["cves"] if c not in known],
        "fixed": entry["fixed"],
    }
    if entry["fixed"]:
        finding["remediation"] = (
            f"至少升級至 {entry['fixed']}（依 OSV.dev，這個版本修補了目前版本受影響的公告），"
            "建議直接使用最新穩定版本，並建立前端依賴的定期更新與漏洞掃描流程。"
        )


def enrich_findings(findings: list[dict]) -> list[dict]:
    """就地補強已知漏洞類 finding；失敗不影響掃描，只在 evidence_json 註明。"""
    targets = [f for f in findings if f.get("rule_id") in TARGET_RULES]
    if not targets or not enabled():
        return findings
    cve_ids = list(dict.fromkeys(c for f in targets for c in _cves(f)))
    packages = list(dict.fromkeys(p for f in targets if (p := _npm_package(f))))
    status = {"epss": "skipped", "osv": "skipped"}
    with _client() as client:
        scores: dict[str, dict] = {}
        osv: dict[tuple, dict] = {}
        if cve_ids:
            try:
                scores = fetch_epss(cve_ids, client)
                status["epss"] = "ok"
            except _Unavailable as exc:
                logger.warning("%s", exc)
                status["epss"] = str(exc)
        if packages:
            try:
                osv = fetch_osv(packages, client)
                status["osv"] = "ok"
            except _Unavailable as exc:
                logger.warning("%s", exc)
                status["osv"] = str(exc)
    for finding in targets:
        finding.setdefault("evidence_json", {})
        finding["evidence_json"]["vuln_intel"] = dict(status)
        _apply_epss(finding, scores)
        package = _npm_package(finding)
        if package and package in osv:
            _apply_osv(finding, osv[package], package[0])
    return findings
