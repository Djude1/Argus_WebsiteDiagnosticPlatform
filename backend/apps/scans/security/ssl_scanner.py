"""SSL/TLS 深度分析。使用 Python 內建 ssl 模組，任何例外 silent-fail 回 []。"""
import socket
import ssl
import time

from apps.scans.scanners import make_finding

_WEAK_CIPHER_TOKENS = ("RC4", "3DES", "DES-CBC3", "DES-CBC")
_OLD_PROTOCOLS = ("TLSv1", "TLSv1.1", "SSLv2", "SSLv3")


def _eval_cert_expiry(not_after: str) -> list[dict]:
    """notAfter 字串（如 'Jun  1 12:00:00 2027 GMT'）→ 到期 finding。"""
    if not not_after:
        return []
    try:
        expires = ssl.cert_time_to_seconds(not_after)
    except Exception:
        return []
    days = (expires - time.time()) / 86400
    if days <= 7:
        sev, rule = "critical", "ssl-cert-expiring"
    elif days <= 30:
        sev, rule = "high", "ssl-cert-expiring"
    else:
        return []
    if days <= 0:
        rule = "ssl-cert-expired"
    return [make_finding(
        category="security", severity=sev, rule_id=rule,
        title="SSL 憑證即將到期或已過期",
        description=f"憑證距到期約 {int(days)} 天（notAfter={not_after}）。",
        remediation="儘速更新 SSL 憑證，避免使用者連線出現警告或中斷。",
        evidence=f"notAfter={not_after}", impact_area="vulnerability",
    )]


def _eval_protocol(version: str) -> list[dict]:
    """ssock.version() 字串 → 過期協議 finding。"""
    if version in _OLD_PROTOCOLS:
        return [make_finding(
            category="security", severity="high", rule_id="ssl-weak-protocol",
            title="使用過時的 TLS/SSL 協議",
            description=f"伺服器協商出過時協議 {version}，低於 TLS 1.2。",
            remediation="停用 TLS 1.0/1.1 與所有 SSL 版本，僅啟用 TLS 1.2 以上。",
            evidence=f"protocol={version}", impact_area="vulnerability",
        )]
    return []


def _eval_cipher(cipher_name: str) -> list[dict]:
    """ssock.cipher()[0] → 弱 cipher finding。"""
    upper = (cipher_name or "").upper()
    if any(tok in upper for tok in _WEAK_CIPHER_TOKENS):
        return [make_finding(
            category="security", severity="high", rule_id="ssl-weak-cipher",
            title="使用弱加密套件（cipher）",
            description=f"伺服器協商出弱加密套件 {cipher_name}（RC4/DES/3DES）。",
            remediation="停用 RC4、DES、3DES 等弱 cipher，改用 AES-GCM/ChaCha20。",
            evidence=f"cipher={cipher_name}", impact_area="vulnerability",
        )]
    return []


def _eval_cert_verify_error(message: str) -> list[dict]:
    """憑證驗證失敗訊息 → self-signed/expired finding。"""
    msg = message.lower()
    if "expired" in msg:
        return [make_finding(
            category="security", severity="critical", rule_id="ssl-cert-expired",
            title="SSL 憑證已過期",
            description="憑證驗證失敗：憑證已過期。",
            remediation="儘速更新 SSL 憑證。",
            evidence=message[:500], impact_area="vulnerability",
        )]
    if "self signed" in msg or "self-signed" in msg:
        return [make_finding(
            category="security", severity="medium", rule_id="ssl-self-signed",
            title="使用自簽憑證或憑證鏈不完整",
            description="憑證驗證失敗：自簽憑證或憑證鏈不完整。",
            remediation="改用受信任 CA 簽發的憑證，並補齊中繼憑證鏈。",
            evidence=message[:500], impact_area="vulnerability",
        )]
    return []


def _probe_insecure(hostname: str, port: int) -> list[dict]:
    """憑證驗證失敗後，用不驗證連線取得協議/cipher。"""
    try:
        ctx = ssl._create_unverified_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                return (
                    _eval_protocol(ssock.version() or "")
                    + _eval_cipher((ssock.cipher() or ("",))[0])
                )
    except Exception:
        return []


def analyze_ssl(hostname: str, port: int = 443, scan_job_id: int = 0) -> list[dict]:
    """連線取得憑證/協議/cipher 資訊，回傳 Finding list。任何例外回 []。"""
    if not hostname:
        return []
    findings: list[dict] = []
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert() or {}
                findings += _eval_cert_expiry(cert.get("notAfter", ""))
                findings += _eval_protocol(ssock.version() or "")
                findings += _eval_cipher((ssock.cipher() or ("",))[0])
    except ssl.SSLCertVerificationError as exc:
        findings += _eval_cert_verify_error(str(exc))
        findings += _probe_insecure(hostname, port)
    except Exception:
        return []
    return findings
