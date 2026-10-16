"""表單欄位的被動資安檢查：密碼欄位沒有遮蔽（2026-10-16）。

ntubimdbirc.tw 的登入頁密碼欄位是 `type="text"`，輸入時明碼顯示。這項原本只有 AI Agent
的 UX 測試偶然回報（歸在 UX），三次掃描只出現一次；它其實是資安問題，而且從 HTML 就能
確定判斷，所以改成規則。純解析已抓到的 HTML、不發請求，由 tasks.py 資安分支被動呼叫。

判定刻意保守：欄位名稱、id、autocomplete、placeholder、aria-label、對應的 label 文字，
或緊接在欄位前的短標題（不用 <label> 的框架常寫成 `<p>密碼</p><input>`，ntubimdbirc.tw 即是）
明確是「密碼」，而且 `type` 是 text 或沒寫（沒寫＝text）才算。email、hidden、number 等其他
型別不算（例如驗證碼、重設密碼用的隱藏 token）；顯示／隱藏密碼按鈕切換後的狀態不在初始 HTML
裡，不會誤判。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from apps.scans.models import Finding
from apps.scans.scanners import make_finding

RULE_ID = "form-password-unmasked"

# 欄位識別字（name／id）：密碼這個詞要是獨立的一段（user_password、pwd），不是字的一部分
_NAME_RE = re.compile(
    r"(?:^|[_\-.\[\s])(password|passwd|passwort|pwd|pass)(?:$|[_\-.\]\s\d])", re.I
)
# 給人看的文字（placeholder、aria-label、label）
_LABEL_RE = re.compile(r"密碼|密码|password|passwort|mot de passe|パスワード|비밀번호", re.I)
# 「確認密碼」「忘記密碼」也是密碼欄位；但這些字樣代表不是要輸入密碼
_NOT_PASSWORD_RE = re.compile(r"驗證碼|验证码|captcha|otp|一次性|簡訊|code", re.I)
_TEXT_TYPES = {"", "text"}
_MAX_REPORTED = 5
_MAX_CAPTION_CHARS = 20


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inputs: list[dict[str, str]] = []
        self.labels: dict[str, str] = {}
        self._label_for: str | None = None
        self._label_text: list[str] = []
        # 上一個欄位之後最近的一段文字：很多框架不用 <label>，把「密碼」寫在欄位前的 <p>／<span>
        self._last_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): (value or "") for name, value in attrs}
        if tag == "input":
            values["_preceding"] = self._last_text
            self._last_text = ""
            self.inputs.append(values)
        elif tag == "label":
            self._label_for = values.get("for", "")
            self._label_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._label_for is not None:
            if self._label_for:
                self.labels[self._label_for] = " ".join(self._label_text)
            self._label_for = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if self._label_for is not None:
            self._label_text.append(text)
        if text:
            self._last_text = text


def _is_password_field(field: dict[str, str], labels: dict[str, str]) -> bool:
    if field.get("type", "").strip().lower() not in _TEXT_TYPES:
        return False
    if field.get("autocomplete", "").lower() in {"current-password", "new-password"}:
        return True
    caption = field.get("_preceding", "")
    human_text = " ".join([
        field.get("placeholder", ""),
        field.get("aria-label", ""),
        labels.get(field.get("id", ""), ""),
        # 只認短標題（「密碼」「Password」），整段說明文字不算
        caption if len(caption) <= _MAX_CAPTION_CHARS else "",
    ])
    if _NOT_PASSWORD_RE.search(human_text):
        return False
    identifiers = f" {field.get('name', '')} {field.get('id', '')} "
    return bool(_NAME_RE.search(identifiers) or _LABEL_RE.search(human_text))


def find_unmasked_password_fields(html: str) -> list[dict[str, str]]:
    """回傳看起來是密碼、卻會明碼顯示的欄位（name／id／type／placeholder）。"""
    parser = _FormParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 — 壞掉的 HTML 不影響其他檢查
        return []
    return [
        {
            "name": field.get("name", ""),
            "id": field.get("id", ""),
            "type": field.get("type", ""),
            "placeholder": field.get("placeholder", ""),
            "caption": field.get("_preceding", "")[:_MAX_CAPTION_CHARS],
        }
        for field in parser.inputs
        if _is_password_field(field, parser.labels)
    ]


def analyze_password_fields(html: str, location: str) -> list[dict]:
    fields = find_unmasked_password_fields(html)
    if not fields:
        return []
    shown = fields[:_MAX_REPORTED]
    evidence = "\n".join(
        "<input "
        + " ".join(
            f'{key}="{field[key]}"' for key in ("name", "id", "type", "placeholder") if field[key]
        )
        + (' type 未設定（預設為 text）' if not field["type"] else "")
        + ">"
        + (f"（欄位標題：{field['caption']}）" if field["caption"] else "")
        for field in shown
    )
    return [
        make_finding(
            category="security",
            severity=Finding.Severity.MEDIUM,
            rule_id=RULE_ID,
            title="密碼欄位沒有遮蔽，輸入時明碼顯示",
            description=(
                f"這一頁有 {len(fields)} 個密碼欄位沒有設成 type=\"password\"，"
                "使用者輸入的密碼會直接顯示在畫面上，旁人或螢幕錄影都看得到；"
                "瀏覽器也不會把它當成密碼處理（不提示產生強密碼、可能被一般表單自動完成記住）。"
            ),
            remediation=(
                '把密碼欄位改成 <input type="password">，並加上 autocomplete="current-password"'
                '（登入）或 "new-password"（註冊、改密碼）。需要「顯示密碼」時用按鈕暫時切換 type。'
            ),
            evidence=evidence,
            evidence_json={
                "type": "html",
                "url": location,
                "fields": shown,
                "count": len(fields),
            },
            impact_area="vulnerability",
        )
    ]
