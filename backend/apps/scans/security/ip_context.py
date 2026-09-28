"""核對證據中出現的 IP 位址屬性，避免把「公開位址」或「掃描器自己的位址」誤判成內部 IP 外洩。

WAF 攔截頁與錯誤頁常回顯「訪客的來源 IP」；看到 IP 不等於伺服器內部位址外洩。
這裡只做被動判斷（位址種類＋與網站公開 DNS 解析結果比對），不發任何額外請求給目標。
"""

import ipaddress
import re
import socket

_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def _resolve(hostname: str) -> set[str]:
    try:
        return {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except (OSError, UnicodeError):
        return set()


def describe_ips(text: str, hostname: str, *, limit: int = 5) -> list[str]:
    """回傳每個 IP 的判讀句；沒有 IP 時回空 list。"""
    found = []
    for raw in dict.fromkeys(_IPV4.findall(text or "")):
        try:
            found.append(ipaddress.ip_address(raw))
        except ValueError:
            continue
    if not found:
        return []
    resolved = _resolve(hostname) if hostname else set()
    lines = []
    for addr in found[:limit]:
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            verdict = "私有／內部網段位址，出現在對外回應中屬於內部網路資訊外洩"
        elif str(addr) in resolved:
            verdict = "與網站公開 DNS 解析結果相同，本來就是公開位址，不構成內部 IP 外洩"
        else:
            verdict = (
                "不在網站公開 DNS 解析結果中；WAF 或錯誤頁常回顯訪客來源 IP，"
                "可能是掃描器自己的位址，需人工確認後才能視為外洩"
            )
        lines.append(f"{addr}：{verdict}")
    return lines
