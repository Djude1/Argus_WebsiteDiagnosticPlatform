"""第三方 JS 庫版本→CVE 比對（OWASP A06 Vulnerable & Outdated Components）。

被動偵測：只解析爬蟲已抓到的 HTML <script>（外部 src URL + inline 內容），
用 vendored Retire.js jsrepository.json 規則萃取版本並比對已知漏洞版本區間。
零額外 HTTP、零新第三方套件；任何例外 silent-fail 回 []。
"""
import json
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

from apps.scans.scanners import make_finding

# Retire.js 對 §§version§§ 佔位符的實際替換（版本捕獲組）
_VERSION_RE = r"([0-9][0-9.a-z_\-]+)"

# 從捕獲到的字串截取開頭的「數字點號版本核心」，丟棄尾端 .min/.bundle 等非版本雜訊
_VERSION_CORE_RE = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:-[0-9a-z.]+)?")


class _ScriptParser(HTMLParser):
    """收集 <script src> 的 URL 與 inline <script> 內容。沿用 stdlib，不引入 BeautifulSoup。"""

    def __init__(self) -> None:
        super().__init__()
        self.src_urls: list[str] = []
        self.inline_scripts: list[str] = []
        self._in_script = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = {name.lower(): (value or "") for name, value in attrs}
        src = attributes.get("src", "").strip()
        if src:
            self.src_urls.append(src)
        else:
            self._in_script = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_script:
            self._in_script = False
            content = "".join(self._buffer)
            if content.strip():
                self.inline_scripts.append(content)
            self._buffer = []


def _collect_scripts(pages: list[dict]) -> tuple[list[str], list[str]]:
    """掃所有頁面的 HTML，回 (外部 script src URL 清單, inline script 內容清單)。"""
    src_urls: list[str] = []
    inline_scripts: list[str] = []
    for page in pages or []:
        html = (page or {}).get("html") or ""
        if not html:
            continue
        parser = _ScriptParser()
        try:
            parser.feed(html)
        except Exception:
            continue
        src_urls.extend(parser.src_urls)
        inline_scripts.extend(parser.inline_scripts)
    return src_urls, inline_scripts


def _to_comparable(token: str | None) -> tuple[int, object]:
    """單一版本段轉可比較值：純數字→(1, int)，其餘字串→(0, str)，缺段或空字串→(1, 0)。

    回傳 tuple 首位為型別旗標（1=數字 > 0=字串），對齊 Retire.js「數字段大於字串段」語意。
    """
    if not token:
        return (1, 0)
    if re.fullmatch(r"\d+", token):
        return (1, int(token))
    return (0, token)


def _compare_versions(v1: str, v2: str) -> int:
    """以 . 與 - 切段逐段比較，回 -1 / 0 / 1。數字段以整數比較（非字典序）。"""
    p1 = re.split(r"[.\-]", (v1 or "").strip())
    p2 = re.split(r"[.\-]", (v2 or "").strip())
    for i in range(max(len(p1), len(p2))):
        c1 = _to_comparable(p1[i] if i < len(p1) else None)
        c2 = _to_comparable(p2[i] if i < len(p2) else None)
        if c1[0] != c2[0]:
            return 1 if c1[0] > c2[0] else -1
        if c1[1] > c2[1]:  # type: ignore[operator]
            return 1
        if c1[1] < c2[1]:  # type: ignore[operator]
            return -1
    return 0


def _is_vulnerable(version: str, vuln: dict) -> bool:
    """版本是否落入此 vuln 的受影響區間（atOrAbove / below / atOrBelow）。"""
    at_or_above = vuln.get("atOrAbove")
    below = vuln.get("below")
    at_or_below = vuln.get("atOrBelow")
    if at_or_above is not None and _compare_versions(version, at_or_above) < 0:
        return False
    if below is not None and _compare_versions(version, below) >= 0:
        return False
    if at_or_below is not None and _compare_versions(version, at_or_below) > 0:
        return False
    # 至少要有一個邊界才算有效區間，避免無邊界 entry 命中所有版本
    return any(x is not None for x in (at_or_above, below, at_or_below))


_DB_PATH = Path(__file__).parent / "data" / "jsrepository.json"


@lru_cache(maxsize=1)
def _load_db() -> dict:
    """讀 vendored Retire.js 規則庫；檔案不存在 / JSON 壞掉 → 回 {}（silent-fail）。"""
    try:
        with open(_DB_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _compile_patterns(patterns: list[str] | None) -> list[re.Pattern]:
    """把 §§version§§ 佔位符換成版本捕獲組後編譯；個別 regex 編譯失敗就跳過。"""
    compiled = []
    for raw in patterns or []:
        try:
            compiled.append(re.compile(raw.replace("§§version§§", _VERSION_RE)))
        except Exception:
            continue
    return compiled


def _first_version(pattern_list: list, text: str) -> str | None:
    """對 text 套用一組 pattern，回第一個看起來像版本（數字開頭）的捕獲值。"""
    for pat in pattern_list:
        match = pat.search(text)
        if match and match.groups():
            candidate = match.group(1)
            if candidate and candidate[0].isdigit():
                # 截取數字點號版本核心，丟棄尾端 .min/.bundle/.js 等雜訊
                return _VERSION_CORE_RE.match(candidate).group(0)
    return None


def _detect_version(
    extractors: dict, src_urls: list[str], inline_scripts: list[str]
) -> tuple[str | None, str | None]:
    """用 uri/filename（打 URL）與 filecontent（打 inline）萃取版本。回 (version, source)。

    已知限制：每個庫的 extractor 會打所有 src_url，命中即回；若某庫的 regex 過於寬鬆而
    比對到不相干的 script URL，可能誤判版本（偽陽性）。實務上 Retire.js extractor 多含庫名
    特徵故風險低，且 analyze_js_libraries 以 (庫名,版本) 去重收斂；如需更嚴謹可改為先以
    URL 含庫名過濾再萃取（YAGNI，現階段不做）。
    """
    uri_pats = _compile_patterns(extractors.get("uri"))
    filename_pats = _compile_patterns(extractors.get("filename"))
    filecontent_pats = _compile_patterns(extractors.get("filecontent"))

    for url in src_urls:
        version = _first_version(uri_pats, url)
        if version:
            return version, url
        filename = url.rsplit("/", 1)[-1].split("?")[0]
        version = _first_version(filename_pats, filename)
        if version:
            return version, url

    for content in inline_scripts:
        version = _first_version(filecontent_pats, content)
        if version:
            return version, "inline"

    return None, None


# Retire.js severity → 排名；critical 封頂為 high（被動偵測未實機確認可利用）
_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_RANK_TO_CAPPED = {1: "low", 2: "medium", 3: "high", 4: "high"}


def _build_finding(name: str, version: str, source: str, vulns: list[dict]) -> dict:
    """把一組命中的 vuln 聚合成單筆 finding；per-CVE 細節進 evidence_json。"""
    cve_ids: list[str] = []
    detail: list[dict] = []
    rank = 1
    for vuln in vulns:
        identifiers = vuln.get("identifiers") or {}
        cves = identifiers.get("CVE") or []
        cve_ids.extend(cves)
        rank = max(rank, _SEVERITY_RANK.get((vuln.get("severity") or "low").lower(), 1))
        detail.append({
            "cve": cves,
            "cwe": vuln.get("cwe") or [],
            "severity": vuln.get("severity") or "low",
            "summary": identifiers.get("summary") or "",
            "info": vuln.get("info") or [],
        })
    capped = _RANK_TO_CAPPED.get(rank, "low")
    cve_ids = list(dict.fromkeys(cve_ids))  # 去重保序

    if not cve_ids:
        cve_summary = f"{len(vulns)} 項已知漏洞"
        cve_list = "（無 CVE 編號，詳見參考連結）"
    elif len(cve_ids) <= 2:
        cve_summary = cve_list = "、".join(cve_ids)
    else:
        cve_summary = f"{cve_ids[0]} 等 {len(cve_ids)} 項"
        cve_list = "、".join(cve_ids)

    return make_finding(
        category="security", severity=capped, rule_id="js-lib-known-vuln",
        title=f"過時的第三方庫 {name} {version} 含已知漏洞（{cve_summary}）",
        description=(
            f"偵測到網站載入 {name} {version}，此版本存在 {len(vulns)} 項已知公開漏洞"
            f"（{cve_list}）。攻擊者可利用對應漏洞對使用此庫的頁面發動攻擊。"
        ),
        remediation=(
            f"將 {name} 升級至已修補的最新穩定版本，"
            "並建立前端依賴的定期更新與漏洞掃描流程。"
        ),
        evidence=f"{name} {version}（來源：{source}）；命中：{cve_list}",
        evidence_json={
            "library": name,
            "version": version,
            "detected_from": source,
            "vulnerabilities": detail,
        },
        impact_area="vulnerability",
    )


def analyze_js_libraries(pages: list[dict]) -> list[dict]:
    """偵測過時第三方 JS 庫並比對已知 CVE。任何例外 silent-fail 回 []。"""
    try:
        db = _load_db()
        if not db:
            return []
        src_urls, inline_scripts = _collect_scripts(pages)
        if not src_urls and not inline_scripts:
            return []

        seen: set[tuple[str, str]] = set()
        out: list[dict] = []
        for name, component in db.items():
            if not isinstance(component, dict):
                continue
            extractors = component.get("extractors") or {}
            version, source = _detect_version(extractors, src_urls, inline_scripts)
            if not version:
                continue
            key = (name, version)
            if key in seen:
                continue
            matched = [
                v for v in (component.get("vulnerabilities") or [])
                if _is_vulnerable(version, v)
            ]
            if not matched:
                continue
            seen.add(key)
            out.append(_build_finding(name, version, source or "unknown", matched))
        return out
    except Exception:
        return []
