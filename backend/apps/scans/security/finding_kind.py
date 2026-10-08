"""資安發現的類型（roadmap §5 第 1 項、§12 第 6 項的第一階段：只標示，不影響分數與排序）。

同樣是「資安問題」，意義差很多：
- 設定建議（config）：防護設定可以更好，本身不是漏洞
  （缺少安全標頭、Cookie 旗標、SPF／DMARC、TLS 設定）。
- 曝露面（exposure）：對外透露了資訊，增加被鎖定的機會，但不等於能被利用
  （版本號、管理入口、公開聯絡資料）。
- 疑似弱點（suspected）：規則或工具推測可能有漏洞，尚未實際驗證（依版本比對的 CVE、秘鑰樣式、
  Nuclei 樣板命中、AI 觀察、可能缺 CSRF token）。
- 已驗證弱點（verified）：實際取得了證據（sqlmap 確認注入、真的下載到 .env／.git 等高風險檔案）。

類型由規則與來源推得，不依賴 `Finding.confidence`：既有資料的 confidence 幾乎都是預設 1.0，
是「沒有校準」而不是「已確認」，不能拿來分類。掃描本身的說明（例如被防護機制擋下）不屬於任何類型。
"""

from __future__ import annotations

CONFIG = "config"
EXPOSURE = "exposure"
SUSPECTED = "suspected"
VERIFIED = "verified"

KIND_LABELS = {
    CONFIG: "設定建議",
    EXPOSURE: "曝露面",
    SUSPECTED: "疑似弱點",
    VERIFIED: "已驗證弱點",
}
KIND_DESCRIPTIONS = {
    CONFIG: "防護設定可以更好，本身不是漏洞",
    EXPOSURE: "對外透露了資訊，增加被鎖定的機會，但不等於能被利用",
    SUSPECTED: "規則或工具推測可能有漏洞，尚未實際驗證",
    VERIFIED: "已取得實際證據的漏洞或外洩",
}

_EXACT = {
    "kali-sqlmap-sqli": VERIFIED,
    "service-known-cve": SUSPECTED,
    "js-lib-known-vuln": SUSPECTED,
    "exposure-hardcoded-secret": SUSPECTED,
    "agent-observed-security": SUSPECTED,
    "header-cors-credentials": SUSPECTED,
    "service-version-exposed": EXPOSURE,
    "header-x-powered-by": EXPOSURE,
    "header-x-generator": EXPOSURE,
    "header-x-aspnet-version": EXPOSURE,
    "header-x-recruiting": EXPOSURE,
    "exposure-robots-disclosure": EXPOSURE,
    "exposure-admin-panel": EXPOSURE,
    "exposure-securitytxt": CONFIG,
    "security-pii-public-contact": EXPOSURE,
    "security-pii-personal-contact": EXPOSURE,
    "SECURITY_PII_8B24BB8B28": EXPOSURE,
}
_PREFIXES = (
    ("header-", CONFIG),
    ("cookie-", CONFIG),
    ("dns-", CONFIG),
    ("ssl-", CONFIG),
    ("sri-", CONFIG),
    ("zap-", CONFIG),
)
# 沒有明確 rule_id 的內建檢查（rule_id 由標題推得），依標題判斷
_TITLES = {
    "頁面未使用 HTTPS": CONFIG,
    "缺少 HSTS": CONFIG,
    "缺少 CSP": CONFIG,
    "缺少 X-Frame-Options": CONFIG,
    "缺少 X-Content-Type-Options": CONFIG,
    "SSL 憑證已過期": CONFIG,
    "SSL 憑證即將到期": CONFIG,
    "使用過時的 TLS/SSL 協議": CONFIG,
    "使用弱加密套件（cipher）": CONFIG,
    "使用自簽憑證或憑證鏈不完整": CONFIG,
    "外部資源缺少 SRI 完整性驗證": CONFIG,
    "表單可能缺少 CSRF token": SUSPECTED,
}
_HIGH = {"critical", "high"}


def security_kind(
    *,
    category: str,
    rule_id: str = "",
    title: str = "",
    severity: str = "",
    evidence: str = "",
) -> str | None:
    """回傳資安發現的類型；非資安或屬於掃描說明（被防護擋下等）回 None。"""
    if category != "security":
        return None
    rule_id = rule_id or ""
    if rule_id in _EXACT:
        return _EXACT[rule_id]
    # 主動探測確實取得的敏感檔案：高風險（.env、.git、備份、憑證）＝已驗證，其餘是曝露面
    if rule_id.startswith("exposure-"):
        return VERIFIED if severity in _HIGH else EXPOSURE
    for prefix, kind in _PREFIXES:
        if rule_id.startswith(prefix):
            return kind
    if title in _TITLES:
        return _TITLES[title]
    # Nuclei 樣板命中：只代表符合樣板特徵
    # （與 reports._source_label 同樣以證據中的「Template：」辨識）
    if "Template：" in (evidence or ""):
        return SUSPECTED
    return None


def kind_payload(**fields) -> dict:
    """給 API／報告用：{"security_kind": 代號或 None, "security_kind_label": 中文或 ""}。"""
    kind = security_kind(**fields)
    return {"security_kind": kind, "security_kind_label": KIND_LABELS.get(kind, "")}
