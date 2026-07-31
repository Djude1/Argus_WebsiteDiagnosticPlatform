"""NVD CVE → 後端服務 CVE DB 轉換（離線、可單元測試的純函式）。

把 NVD 2.0 API 的 CVE 物件過濾出 nginx / Apache / PHP 三個產品，轉成
``data/backend_services.json`` 結構——版本區間欄位與 ``jsrepository.json`` 一致
（atOrAbove / below / atOrBelow），供 ``service_cve_scanner`` 透過
``js_library_scanner._is_vulnerable`` 比對。

NVD ``cpeMatch`` 版本欄位對應：
- ``versionStartIncluding`` → ``atOrAbove``（含下界）
- ``versionStartExcluding`` → ``atOrAbove``（近似；邊界些微誤差，被動掃描可接受）
- ``versionEndIncluding``   → ``atOrBelow``（含上界）
- ``versionEndExcluding``   → ``below``（不含上界）

本模組只負責轉換；下載與寫檔由 ``scripts/refresh_backend_cve_db.py`` 處理，使此處可獨立測試。
"""
from __future__ import annotations

# product 鍵 → CPE 2.3 比對前綴（vendor:product，結尾加 ':' 避免部分誤 match）
TARGET_PRODUCTS: dict[str, str] = {
    "nginx": "cpe:2.3:a:nginx:nginx:",
    "apache": "cpe:2.3:a:apache:http_server:",
    "php": "cpe:2.3:a:php:php:",
}

_METRIC_KEYS = ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2")


def cvss_severity(cve: dict) -> str:
    """取 CVSS baseSeverity（low/medium/high/critical）；無則回 'medium'。"""
    metrics = cve.get("metrics") or {}
    for key in _METRIC_KEYS:
        block = metrics.get(key)
        if isinstance(block, list) and block and isinstance(block[0], dict):
            data = block[0].get("cvssData") or {}
            sev = (data.get("baseSeverity") or "").lower()
            if sev:
                return sev
    return "medium"


def _version_range(cpe_match: dict) -> dict:
    """NVD cpeMatch 版本欄位 → jslibrary-style 區間。無任何邊界回 {}（無法比對）。"""
    rng: dict = {}
    if cpe_match.get("versionStartIncluding"):
        rng["atOrAbove"] = cpe_match["versionStartIncluding"]
    elif cpe_match.get("versionStartExcluding"):
        # > X 近似為 >= X（邊界些微誤差，被動掃描可接受）
        rng["atOrAbove"] = cpe_match["versionStartExcluding"]
    if cpe_match.get("versionEndIncluding"):
        rng["atOrBelow"] = cpe_match["versionEndIncluding"]
    elif cpe_match.get("versionEndExcluding"):
        rng["below"] = cpe_match["versionEndExcluding"]
    return rng


def _english_description(cve: dict) -> str:
    for d in cve.get("descriptions") or []:
        if isinstance(d, dict) and d.get("lang") == "en":
            return (d.get("value") or "").strip()
    return ""


def _cwes(cve: dict) -> list[str]:
    out: list[str] = []
    for w in cve.get("weaknesses") or []:
        if not isinstance(w, dict):
            continue
        for wd in w.get("description") or []:
            v = (wd.get("value") or "") if isinstance(wd, dict) else ""
            if v.startswith("CWE-") and v not in out:
                out.append(v)
    return out[:3]


def build_db_from_nvd(cve_objects: list[dict]) -> dict:
    """把 NVD 2.0 CVE 物件清單過濾目標產品，轉成 backend_services.json 結構。

    一個 CVE 若含多個目標 cpeMatch（不同區間）會產生多筆 vulnerabilities entry，
    與 jsrepository.json 一庫多 vuln 的結構一致；scanner 端會把同 (產品,版本) 命中
    的多筆聚合成單一 finding。
    """
    db: dict[str, dict] = {}
    for cve in cve_objects:
        if not isinstance(cve, dict):
            continue
        cve_id = cve.get("id") or ""
        if not cve_id:
            continue
        severity = cvss_severity(cve)
        summary = _english_description(cve)[:140]
        cwes = _cwes(cve)
        for config in cve.get("configurations") or []:
            if not isinstance(config, dict):
                continue
            for node in config.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                for cpe_match in node.get("cpeMatch") or []:
                    if not isinstance(cpe_match, dict):
                        continue
                    crit = cpe_match.get("criteria") or ""
                    for product, prefix in TARGET_PRODUCTS.items():
                        if crit.startswith(prefix):
                            rng = _version_range(cpe_match)
                            if rng:
                                db.setdefault(product, {"vulnerabilities": []})[
                                    "vulnerabilities"
                                ].append({
                                    **rng,
                                    "severity": severity,
                                    "identifiers": {"CVE": [cve_id], "summary": summary},
                                    "cwe": cwes,
                                    "info": [f"https://nvd.nist.gov/vuln/detail/{cve_id}"],
                                })
                            break  # 同一 cpe_match 只歸一個產品
    return db
