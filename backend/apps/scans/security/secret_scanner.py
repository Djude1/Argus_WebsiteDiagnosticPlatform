"""硬編碼秘鑰 / 憑證偵測。

純文字規則引擎：給一段文字（檔案內容、HTML、inline script），抓出疑似外洩的
API key、雲端金鑰、連線字串、私鑰、JWT、明文密碼等。任何例外 silent-fail 回 []。

設計重點：
- 只用「高訊號前綴」的特定 pattern，避免一般網站誤報（新手信任）。
- 回傳的 evidence 一律遮罩秘鑰值（只留前綴 / 連線字串只遮密碼段），
  讓報告可貼給使用者看「外洩了什麼」而不會二次外洩完整秘鑰。
- 既能用於「主動探測到的檔案內容」，也能用於「已爬頁面的 inline script」（被動）。
"""
from __future__ import annotations

import re

from apps.scans.scanners import make_finding

# 明顯的佔位字串：值看起來是這些時不報，降低 .env.example 之類的誤報
_PLACEHOLDER_TOKENS = (
    "changeme", "change_me", "your_", "yourkey", "example", "placeholder",
    "xxxxx", "<", "...", "***", "dummy", "todo", "replace", "sample",
)


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(tok in low for tok in _PLACEHOLDER_TOKENS)


def _mask(value: str, keep: int = 6) -> str:
    """遮罩秘鑰值，只保留前 keep 字元。"""
    value = value.strip()
    if len(value) <= keep:
        return value[: max(1, keep - 2)] + "…"
    return value[:keep] + "…"


def _mask_conn_string(match: str) -> str:
    """連線字串 scheme://user:pass@host 只遮 pass 段，保留 scheme/user/host 當證據。"""
    return re.sub(
        r"(://[^\s:@/]+:)([^\s:@/]+)(@)",
        lambda m: f"{m.group(1)}****{m.group(3)}",
        match,
    )


# (kind, 標籤, severity, 已編譯 pattern, group_index_of_value)
# pattern 以高訊號前綴為主；fake/測試 token 也要抓得到，因此長度放寬。
_SECRET_PATTERNS: tuple[tuple[str, str, str, re.Pattern[str], int], ...] = (
    ("private_key", "私鑰（PEM）", "critical",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"), 0),
    ("aws_access_key", "AWS Access Key ID", "critical",
     re.compile(r"\bAKIA[0-9A-Z]{12,20}\b"), 0),
    ("github_pat", "GitHub Personal Access Token", "critical",
     re.compile(r"\bgh[pousr]_[0-9A-Za-z_]{16,}\b"), 0),
    ("stripe_live", "Stripe 正式金鑰 (sk_live)", "critical",
     re.compile(r"\bsk_live_[0-9A-Za-z_]{10,}\b"), 0),
    ("google_api_key", "Google API Key", "high",
     re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}\b"), 0),
    ("stripe_test", "Stripe 測試金鑰 (sk_test)", "high",
     re.compile(r"\bsk_test_[0-9A-Za-z_]{10,}\b"), 0),
    ("stripe_webhook", "Stripe Webhook Secret", "high",
     re.compile(r"\bwhsec_[0-9A-Za-z_]{10,}\b"), 0),
    ("sendgrid", "SendGrid API Key", "high",
     re.compile(r"\bSG\.[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}\b"), 0),
    ("slack_token", "Slack Token", "high",
     re.compile(r"\bxox[baprs]-[0-9A-Za-z_\-]{8,}\b"), 0),
    ("conn_string", "含帳密的連線字串", "high",
     re.compile(r"\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqp)://"
                r"[^\s:@/]{1,128}:[^\s:@/]{1,128}@[^\s/\"']{1,256}"), 0),
    ("jwt", "JSON Web Token (JWT)", "medium",
     re.compile(r"\beyJ[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{6,}\b"), 0),
)

# 泛用「賦值」型：KEY=VALUE / "key": "value"。高訊號 key 名 + 非佔位值才報。
_GENERIC_ASSIGN = re.compile(
    r"(?i)(?P<key>password|passwd|pwd|secret|api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|client[_-]?secret|jwt[_-]?secret|aws_secret_access_key)"
    r"\s*[:=]\s*[\"']?(?P<val>[^\s\"'#,}<>]{6,})"
)


def detect_secrets_in_text(text: str) -> list[dict]:
    """從文字中抓疑似秘鑰，回傳去重後的 list（每筆 {kind,label,severity,masked}）。

    僅做格式比對，不驗證秘鑰是否實際有效。任何例外回 []。
    """
    try:
        text = text or ""
        if not text:
            return []
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()

        def _add(kind: str, label: str, severity: str, raw: str, masked: str) -> None:
            key = (kind, raw)
            if key in seen:
                return
            seen.add(key)
            out.append({"kind": kind, "label": label, "severity": severity, "masked": masked})

        for kind, label, severity, pattern, _gi in _SECRET_PATTERNS:
            for m in pattern.finditer(text):
                raw = m.group(0)
                masked = _mask_conn_string(raw) if kind == "conn_string" else _mask(raw)
                _add(kind, label, severity, raw, masked)

        for m in _GENERIC_ASSIGN.finditer(text):
            val = m.group("val")
            if _is_placeholder(val):
                continue
            key_name = m.group("key")
            _add("credential_assignment", f"明文機密賦值（{key_name}）", "medium",
                 f"{key_name}={val}", f"{key_name}={_mask(val)}")

        return out
    except Exception:
        return []


def redact_secrets_in_text(text: str) -> str:
    """把文字中所有偵測到的秘鑰值就地遮罩，供「檔案內容片段」當證據時不二次外洩。

    連線字串只遮密碼段、賦值型只遮值、其餘遮整段（保留前綴）。任何例外回原文。
    """
    try:
        text = text or ""
        if not text:
            return text
        for kind, _label, _sev, pattern, _gi in _SECRET_PATTERNS:
            text = pattern.sub(
                lambda m, k=kind: _mask_conn_string(m.group(0)) if k == "conn_string"
                else _mask(m.group(0)),
                text,
            )

        def _repl_assign(m: re.Match[str]) -> str:
            # 遮罩路徑一律遮（即使值含 example 之類子字串也可能是真密碼）；
            # placeholder 判斷只用於 detect_secrets_in_text 決定「是否回報」，不在此豁免遮罩。
            val = m.group("val")
            return m.group(0).replace(val, _mask(val))

        return _GENERIC_ASSIGN.sub(_repl_assign, text)
    except Exception:
        return text or ""


def _summarize(secrets: list[dict]) -> str:
    """把偵測結果整理成新手可讀的證據文字（已遮罩）。"""
    lines: list[str] = []
    for s in secrets[:30]:
        lines.append(f"• {s['label']}：{s['masked']}")
    if len(secrets) > 30:
        lines.append(f"…（另有 {len(secrets) - 30} 筆）")
    return "\n".join(lines)


def build_secret_finding(secrets: list[dict], location: str, *, source: str) -> dict | None:
    """把一批秘鑰偵測結果包成單一 Finding dict（用 make_finding，含 owasp 待 tag）。

    location：來源描述（頁面 URL 或檔案路徑）。source：evidence_source 標記。
    無秘鑰回 None。severity 取批次中最高者。
    """
    if not secrets:
        return None
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    severity = max((s["severity"] for s in secrets), key=lambda x: order.get(x, 0))
    kinds = sorted({s["label"] for s in secrets})
    evidence = f"位置：{location}\n偵測到 {len(secrets)} 筆疑似秘鑰：\n{_summarize(secrets)}"
    return make_finding(
        category="security",
        severity=severity,
        rule_id="exposure-hardcoded-secret",
        title="偵測到硬編碼 / 外洩的秘鑰",
        description=(
            f"在「{location}」發現 {len(secrets)} 筆疑似秘鑰（{', '.join(kinds)}）。"
            "這類秘鑰一旦被任何人（含搜尋引擎、自動化工具）讀到，"
            "攻擊者可直接拿去登入資料庫、雲端服務或第三方 API，"
            "通常不需要進一步入侵就能造成資料外洩或費用損失。"
        ),
        remediation=(
            "1. 立刻將這些秘鑰視為已外洩，到對應服務後台「撤銷 / 重新產生」（rotate）。\n"
            "2. 把秘鑰改放環境變數或密鑰管理服務（Vault、雲端 Secrets Manager），"
            "不要寫進前端、設定檔或版本控制。\n"
            "3. 確認該檔案 / 路徑不該對外公開時，於伺服器或 CDN 封鎖其存取。\n"
            "4. 檢查存取紀錄，確認秘鑰未被濫用。"
        ),
        evidence=evidence,
        evidence_source=source,
        impact_area="secret_disclosure",
        confidence=0.85,
        priority_score=90.0 if severity == "critical" else 75.0,
    )
