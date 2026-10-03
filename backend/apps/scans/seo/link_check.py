"""連結狀態與站台層級網址檢查（掃描階段 stage_seo_links 執行，結果寫 ScanJob.seo_report）。

- 每一跳都重新過 assert_public_http_url（SSRF 防護與爬蟲一致），手動跟隨轉址最多 5 跳，
  記錄完整跳轉鏈。
- 302 → 200 這類「轉址後正常」不算失效連結；401／403／429 代表對方拒絕自動檢查，
  標成「無法確認」而不是失效。
- 先送 HEAD；HEAD 回 4xx／5xx 時一律改用 GET 再確認（只讀標頭、不下載內容）。
- 有總數與總時間上限：外部網站很多時只檢查前 N 個，其餘標「未檢查」。
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from django.conf import settings

from apps.scans.services import PublicScanTargetError, assert_public_http_url

MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 6
MAX_ROBOTS_BYTES = 512 * 1024
RESTRICTED_STATUSES = {401, 403, 429, 999}
# 兩層的公共後綴（台灣與常見地區）；不引入 publicsuffix 套件，判斷子網域夠用
_TWO_LEVEL_SUFFIXES = {
    "com.tw", "org.tw", "edu.tw", "gov.tw", "net.tw", "idv.tw", "co.uk", "org.uk", "ac.uk",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "com.cn", "com.hk", "org.hk", "com.sg", "com.au",
    "co.kr", "com.my",
}


def registrable_domain(host: str) -> str:
    labels = (host or "").lower().strip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _bare(host: str) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def classify_link(url: str, site_host: str) -> str:
    """internal（同網站，含 www 變體）／subdomain（同網域的其他子網域）／external。"""
    host = (urlsplit(url).hostname or "").lower()
    if _bare(host) == _bare(site_host):
        return "internal"
    if registrable_domain(host) == registrable_domain(site_host):
        return "subdomain"
    return "external"


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": settings.ARGUS_SCANNER_USER_AGENT, "Accept": "*/*"},
    )


def _request(client: httpx.Client, url: str) -> tuple[int, str]:
    """回傳 (狀態碼, Location)。"""
    response = client.head(url)
    if response.status_code >= 400:
        # 不少伺服器不支援或拒絕 HEAD（405／501，或經 Cloudflare 回 520），錯誤一律以 GET 再確認，
        # 只讀標頭不下載內容。2026-10-03 實測 ntubimdbirc.tw：HEAD 520、GET 才是真正的 404／200
        with client.stream("GET", url) as streamed:
            return streamed.status_code, streamed.headers.get("location", "")
    return response.status_code, response.headers.get("location", "")


def check_url(url: str, client: httpx.Client | None = None) -> dict:
    """回傳 {url, chain:[{url,status}], status, final_url, verdict, note}。"""
    owns_client = client is None
    client = client or _client()
    chain: list[dict] = []
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                current = assert_public_http_url(current)
            except (PublicScanTargetError, ValueError):
                return _result(url, chain, "skipped", note="非公開位址，未檢查")
            try:
                status, location = _request(client, current)
            except httpx.TimeoutException:
                chain.append({"url": current, "status": None})
                return _result(url, chain, "error", note="逾時")
            except httpx.HTTPError as exc:
                chain.append({"url": current, "status": None})
                return _result(url, chain, "error", note=f"無法連線（{exc.__class__.__name__}）")
            chain.append({"url": current, "status": status})
            if 300 <= status < 400 and location:
                current = urljoin(current, location)
                continue
            return _result(url, chain, _verdict(status, len(chain) - 1))
        return _result(url, chain, "loop", note=f"超過 {MAX_REDIRECTS} 次轉址")
    finally:
        if owns_client:
            client.close()


def _verdict(status: int, hops: int) -> str:
    if 200 <= status < 300:
        return "redirect" if hops else "ok"
    if status in RESTRICTED_STATUSES:
        return "restricted"
    if status >= 400:
        return "broken"
    return "other"


def _result(url: str, chain: list[dict], verdict: str, *, note: str = "") -> dict:
    last = chain[-1] if chain else {"url": url, "status": None}
    return {
        "url": url,
        "chain": chain,
        "status": last["status"],
        "final_url": last["url"],
        "verdict": verdict,
        "note": note,
    }


def check_links(
    urls: list[str],
    *,
    limit: int,
    budget_seconds: float,
    should_stop: Callable[[], None] | None = None,
    workers: int = 4,
) -> tuple[dict[str, dict], int]:
    """檢查前 limit 個網址；回傳 ({url: result}, 未檢查數)。should_stop 用來接取消檢查點。"""
    targets = urls[:limit]
    deadline = time.monotonic() + budget_seconds
    results: dict[str, dict] = {}

    def run(url: str) -> tuple[str, dict | None]:
        if time.monotonic() > deadline:
            return url, None
        with _client() as client:
            return url, check_url(url, client)

    # 分批送出，每批之間檢查取消
    batch = max(workers * 4, 1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(targets), batch):
            if should_stop:
                should_stop()
            for url, result in pool.map(run, targets[start:start + batch]):
                if result is not None:
                    results[url] = result
    return results, len(urls) - len(results)


# ---------------------------------------------------------------- 站台層級檢查


def _site_check(key: str, label: str, level: str, value: str, advice: str = "", **evidence):
    return {"key": key, "label": label, "level": level, "value": value, "advice": advice,
            "evidence": evidence}


def fetch_robots(origin_url: str) -> dict:
    """抓 robots.txt；回傳狀態、Sitemap 宣告與 User-agent: * 的 Disallow 規則。"""
    url = urljoin(origin_url, "/robots.txt")
    info = {"url": url, "status": None, "sitemaps": [], "disallow": [], "disallow_all": False}
    try:
        url = assert_public_http_url(url)
        with _client() as client, client.stream("GET", url) as response:
            info["status"] = response.status_code
            if response.status_code != 200:
                return info
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_ROBOTS_BYTES:
                    break
    except (PublicScanTargetError, ValueError, httpx.HTTPError):
        return info
    applies = False
    for raw in body.decode("utf-8", "replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field_name, value = (part.strip() for part in line.split(":", 1))
        field_name = field_name.lower()
        if field_name == "user-agent":
            applies = value == "*"
        elif field_name == "sitemap" and value:
            info["sitemaps"].append(value)
        elif field_name == "disallow" and applies and value and len(info["disallow"]) < 100:
            info["disallow"].append(value)
    info["disallow_all"] = "/" in info["disallow"]
    info["sitemaps"] = info["sitemaps"][:10]
    return info


def robots_blocks(path: str, disallow: list[str]) -> str:
    """回傳擋住 path 的那條 Disallow 規則（簡化比對：前綴，支援結尾 $ 與 *）。"""
    for rule in disallow:
        pattern = rule.rstrip("$")
        if "*" in pattern:
            head = pattern.split("*", 1)[0]
            if path.startswith(head):
                return rule
        elif (rule.endswith("$") and path == pattern) or path.startswith(pattern):
            return rule
    return ""


def site_checks(start_url: str, robots: dict, sample_paths: list[str]) -> list[dict]:
    parts = urlsplit(start_url)
    host = parts.hostname or ""
    origin = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
    checks: list[dict] = []

    if robots["status"] == 200:
        if robots["disallow_all"]:
            checks.append(_site_check(
                "robots_txt", "robots.txt", "critical", "Disallow: /（擋住所有搜尋引擎）",
                "移除 Disallow: /，只擋不該被收錄的路徑。", requested=robots["url"],
            ))
        else:
            checks.append(_site_check(
                "robots_txt", "robots.txt", "pass",
                f"存在；{len(robots['disallow'])} 條 Disallow、"
                f"{len(robots['sitemaps'])} 個 Sitemap",
                requested=robots["url"],
            ))
    else:
        checks.append(_site_check(
            "robots_txt", "robots.txt", "notice", f"HTTP {robots['status'] or '無法取得'}",
            "建議提供 robots.txt 並宣告 Sitemap。", requested=robots["url"],
        ))

    sitemap_url = robots["sitemaps"][0] if robots["sitemaps"] else urljoin(origin, "/sitemap.xml")
    sitemap = check_url(sitemap_url)
    sitemap_ok = sitemap["verdict"] in {"ok", "redirect"}
    checks.append(_site_check(
        "sitemap", "Sitemap", "pass" if sitemap_ok else "notice",
        f"{sitemap_url} → {sitemap['status'] or sitemap['note']}",
        "" if sitemap_ok else "提供 sitemap.xml 並在 robots.txt 宣告。",
        requested=sitemap_url, chain=sitemap["chain"],
    ))

    if parts.scheme == "https":
        http_url = urlunsplit(("http", parts.netloc, "/", "", ""))
        result = check_url(http_url)
        to_https = urlsplit(result["final_url"]).scheme == "https" and result["verdict"] in {
            "redirect", "ok"
        } and len(result["chain"]) > 1
        checks.append(_site_check(
            "http_to_https", "HTTP → HTTPS", "pass" if to_https else "warning",
            _chain_text(result),
            "" if to_https else "讓 http:// 以 301 轉到 https://，避免重複內容與不安全連線。",
            requested=http_url, chain=result["chain"],
        ))

    alt_host = host[4:] if host.startswith("www.") else f"www.{host}"
    alt_url = urlunsplit((parts.scheme, alt_host + (f":{parts.port}" if parts.port else ""),
                          "/", "", ""))
    result = check_url(alt_url)
    final_host = urlsplit(result["final_url"]).hostname or ""
    if result["verdict"] in {"error", "skipped"}:
        level, advice = "pass", ""
    elif _bare(final_host) == _bare(host) and final_host == host:
        level, advice = "pass", ""
    elif result["verdict"] == "ok":
        level, advice = "warning", f"{alt_host} 與 {host} 都直接回應內容，請擇一並 301 轉址。"
    else:
        level, advice = "notice", "確認 www 與非 www 版本最後都導向同一個網址。"
    checks.append(_site_check(
        "www", "www／非 www", level, _chain_text(result), advice,
        requested=alt_url, chain=result["chain"],
    ))

    missing_url = urljoin(origin, f"/argus-404-check-{secrets.token_hex(4)}")
    result = check_url(missing_url)
    if result["status"] in {404, 410}:
        level, advice = "pass", ""
    elif result["verdict"] in {"ok", "redirect"}:
        level = "warning"
        advice = "不存在的網址回 200（軟 404），應回 404 讓搜尋引擎知道頁面不存在。"
    else:
        level, advice = "notice", ""
    checks.append(_site_check(
        "not_found", "404 頁面", level, _chain_text(result), advice,
        requested=missing_url, chain=result["chain"],
    ))

    index_url = urljoin(origin, "/index.html")
    result = check_url(index_url)
    duplicate = result["verdict"] == "ok"
    checks.append(_site_check(
        "index_page", "首頁 index.html", "notice" if duplicate else "pass", _chain_text(result),
        "/index.html 與首頁內容相同卻不轉址，建議 301 到 /。" if duplicate else "",
        requested=index_url, chain=result["chain"],
    ))

    sample = next((p for p in sample_paths if p not in {"", "/"}), "")
    if sample:
        toggled = sample[:-1] if sample.endswith("/") else f"{sample}/"
        toggled_url = urljoin(origin, toggled)
        result = check_url(toggled_url)
        duplicate = result["verdict"] == "ok"
        checks.append(_site_check(
            "trailing_slash", "結尾斜線", "notice" if duplicate else "pass",
            f"{sample} ↔ {toggled}：{_chain_text(result)}",
            "有無結尾斜線都回 200，建議擇一並 301 轉址。" if duplicate else "",
            requested=toggled_url, chain=result["chain"],
        ))
    return checks


def _chain_text(result: dict) -> str:
    if not result["chain"]:
        return result["note"] or "未檢查"
    steps = [f"{hop['status'] or '—'}" for hop in result["chain"]]
    text = " → ".join(steps)
    if len(result["chain"]) > 1:
        text += f"（最後：{result['final_url']}）"
    if result["note"]:
        text += f"；{result['note']}"
    return text
