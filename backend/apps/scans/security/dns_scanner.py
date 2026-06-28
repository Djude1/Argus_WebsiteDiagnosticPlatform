"""DNS/郵件安全：SPF / DMARC / DNSSEC。用 dnspython 查詢，任何例外 silent-fail 回 []。
只對掃描目標自身網域做標準查詢，無 SSRF 面；不做 DKIM（黑盒無法可靠列舉 selector）。"""
import dns.resolver

from apps.scans.scanners import make_finding

_TIMEOUT = 3.0
_LIFETIME = 5.0


def _resolver() -> "dns.resolver.Resolver":
    r = dns.resolver.Resolver()
    r.timeout = _TIMEOUT
    r.lifetime = _LIFETIME
    return r


def _query_txt(name: str) -> list[str]:
    """回傳 name 的 TXT 字串清單；查不到 / 失敗回 []。"""
    try:
        answers = _resolver().resolve(name, "TXT")
        return [b"".join(r.strings).decode("utf-8", "ignore") for r in answers]
    except Exception:
        return []


def _has_dnskey(name: str) -> bool | None:
    """有 DNSKEY → True；name 存在但無 DNSKEY → False；查詢失敗 → None（不報）。"""
    try:
        _resolver().resolve(name, "DNSKEY")
        return True
    except dns.resolver.NoAnswer:
        return False
    except Exception:
        return None


def _org_domain(host: str) -> str:
    """去掉最左 label 退一層父網域；兩層以下回原值（不引入 publicsuffix）。"""
    parts = host.split(".")
    return ".".join(parts[1:]) if len(parts) > 2 else host


def _find_spf(domain: str) -> str | None:
    for txt in _query_txt(domain):
        if txt.lower().startswith("v=spf1"):
            return txt
    return None


def _find_dmarc(domain: str) -> str | None:
    for txt in _query_txt(f"_dmarc.{domain}"):
        if txt.lower().startswith("v=dmarc1"):
            return txt
    return None


def _dmarc_policy(record: str) -> str:
    for part in record.split(";"):
        part = part.strip().lower()
        if part.startswith("p="):
            return part[2:].strip()
    return ""


def _eval_spf(spf_record: str | None, domain: str) -> list[dict]:
    if spf_record is None:
        return [make_finding(
            category="security", severity="medium", rule_id="dns-spf-missing",
            title="網域缺少 SPF 記錄",
            description=(
                f"網域 {domain} 未設定 SPF（v=spf1）TXT 記錄，"
                "攻擊者可偽冒此網域寄送釣魚郵件。"
            ),
            remediation="於 DNS 新增 SPF TXT 記錄，明確列出允許的寄件來源並以 -all 結尾。",
            evidence=f"{domain} TXT：查無 v=spf1",
            impact_area="vulnerability",
        )]
    if spf_record.replace(" ", "").lower().endswith("+all"):
        return [make_finding(
            category="security", severity="high", rule_id="dns-spf-permissive",
            title="SPF 政策過寬（+all）",
            description=f"網域 {domain} 的 SPF 以 +all 結尾，等同允許任何來源代發郵件。",
            remediation="將 SPF 結尾改為 -all（嚴格）或 ~all（軟性），勿用 +all。",
            evidence=f"{domain} SPF：{spf_record}",
            impact_area="vulnerability",
        )]
    return []


def _eval_dmarc(dmarc_record: str | None, domain: str) -> list[dict]:
    if dmarc_record is None:
        return [make_finding(
            category="security", severity="low", rule_id="dns-dmarc-missing",
            title="網域缺少 DMARC 記錄",
            description=f"網域 {domain} 未設定 DMARC（v=DMARC1）政策，無法防止寄件者偽冒。",
            remediation="於 _dmarc 子網域新增 DMARC TXT 記錄，政策建議至少 p=quarantine。",
            evidence=f"_dmarc.{domain} TXT：查無 v=DMARC1",
            impact_area="vulnerability",
        )]
    if _dmarc_policy(dmarc_record) == "none":
        return [make_finding(
            category="security", severity="low", rule_id="dns-dmarc-policy-weak",
            title="DMARC 政策過寬（p=none）",
            description=f"網域 {domain} 的 DMARC 政策為 p=none，僅監測不阻擋偽冒郵件。",
            remediation="將 DMARC 政策提升為 p=quarantine 或 p=reject。",
            evidence=f"{domain} DMARC：{dmarc_record}",
            impact_area="vulnerability",
        )]
    return []


def _eval_dnssec(has_dnskey: bool | None, domain: str) -> list[dict]:
    if has_dnskey is False:
        return [make_finding(
            category="security", severity="low", rule_id="dns-dnssec-missing",
            title="網域未啟用 DNSSEC（最佳實務建議）",
            description=(
                f"網域 {domain} 未偵測到 DNSKEY 記錄，"
                "建議啟用 DNSSEC 以防 DNS 回應遭竄改。"
            ),
            remediation="向網域註冊商或 DNS 服務商啟用 DNSSEC 簽章。",
            evidence=f"{domain} DNSKEY：查無記錄",
            impact_area="vulnerability",
        )]
    return []


def analyze_dns(host: str) -> list[dict]:
    """查 SPF/DMARC（host 查不到退父網域一層）與 DNSSEC（查 org domain）。"""
    try:
        if not host:
            return []
        org = _org_domain(host)
        candidates = [host] if org == host else [host, org]

        spf = next((r for d in candidates if (r := _find_spf(d))), None)
        dmarc = next((r for d in candidates if (r := _find_dmarc(d))), None)

        out: list[dict] = []
        out += _eval_spf(spf, org)
        out += _eval_dmarc(dmarc, org)
        out += _eval_dnssec(_has_dnskey(org), org)
        return out
    except Exception:
        return []
