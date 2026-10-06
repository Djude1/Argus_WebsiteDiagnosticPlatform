"""優化前後可量測的差異（確定性計算，不呼叫模型）。

結果頁要回答「實際改善效果」：把原樣快照與優化版用同一套規則量一次，只列出
有變化的指標。量不到的（版面好不好看）不硬給分數，交給 Before／After 畫面與修改清單。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_LABELED_BY_ATTR = ("aria-label", "aria-labelledby", "title")
_FIELD_TAGS = {"input", "select", "textarea"}
_IGNORED_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.title = ""
        self._in_title = False
        self.meta_description = ""
        self.canonical = False
        self.viewport = False
        self.og_tags = 0
        self.h1 = 0
        self.images = 0
        self.images_missing_alt = 0
        self.images_lazy = 0
        self.fields: list[dict] = []
        self.label_for: set[str] = set()
        self._label_depth = 0
        self.landmarks = 0
        self.css_rules = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name == "description":
                self.meta_description = a.get("content", "").strip()
            elif name == "viewport":
                self.viewport = True
            elif name.startswith("og:"):
                self.og_tags += 1
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "img":
            self.images += 1
            if "alt" not in a:
                self.images_missing_alt += 1
            if a.get("loading", "").lower() == "lazy":
                self.images_lazy += 1
        elif tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        elif tag in _FIELD_TAGS:
            if tag == "input" and a.get("type", "text").lower() in _IGNORED_INPUT_TYPES:
                return
            self.fields.append(
                {
                    "id": a.get("id", ""),
                    "named": any(a.get(k) for k in _LABELED_BY_ATTR),
                    "wrapped": self._label_depth > 0,
                }
            )
        elif tag in {"main", "nav", "header", "footer"}:
            self.landmarks += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "label" and self._label_depth:
            self._label_depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    @property
    def unlabeled_fields(self) -> int:
        return sum(
            1
            for f in self.fields
            if not (f["named"] or f["wrapped"] or (f["id"] and f["id"] in self.label_for))
        )


def _collect(html: str) -> _Collector:
    collector = _Collector()
    try:
        collector.feed(html or "")
        collector.close()
    except Exception:  # noqa: BLE001 — 壞掉的 HTML 不應讓結果頁失敗
        pass
    collector.css_rules = sum(
        len(re.findall(r"\{", block))
        for block in re.findall(r"<style[^>]*>(.*?)</style>", html or "", re.S | re.I)
    )
    return collector


_A11Y = "accessibility"
# (key, 標籤, 分類, 取值, 越多越好？)；分類對應結果頁的分組
_METRICS = (
    ("title_length", "頁面標題長度（字）", "seo", lambda c: len(c.title.strip()), None),
    ("meta_description", "Meta description", "seo", lambda c: bool(c.meta_description), True),
    ("canonical", "Canonical 網址", "seo", lambda c: c.canonical, True),
    ("og_tags", "Open Graph 分享標籤（個）", "seo", lambda c: c.og_tags, True),
    ("lang", "頁面語言宣告", _A11Y, lambda c: bool(c.lang), True),
    ("h1", "H1 主標題（個）", _A11Y, lambda c: c.h1, None),
    ("images_missing_alt", "缺少 alt 的圖片", _A11Y, lambda c: c.images_missing_alt, False),
    ("unlabeled_fields", "沒有標籤的表單欄位", _A11Y, lambda c: c.unlabeled_fields, False),
    ("landmarks", "語意區塊（header／nav／main／footer）", _A11Y, lambda c: c.landmarks, True),
    ("viewport", "行動版 viewport 設定", "performance", lambda c: c.viewport, True),
    ("images_lazy", "延遲載入的圖片", "performance", lambda c: c.images_lazy, True),
    ("css_rules", "頁內樣式規則（版面調整）", "visual", lambda c: c.css_rules, None),
)


def compare(before_html: str, after_html: str) -> list[dict]:
    """回傳有變化的指標：[{key, label, category, before, after, improved}]。

    improved：True＝往好的方向、False＝變差、None＝沒有好壞方向（例如樣式規則數）。
    """
    before, after = _collect(before_html), _collect(after_html)
    rows = []
    for key, label, category, getter, more_is_better in _METRICS:
        old, new = getter(before), getter(after)
        if old == new:
            continue
        if key == "h1":
            improved = abs(new - 1) < abs(old - 1)
        elif key == "title_length":
            improved = abs(new - 30) < abs(old - 30)
        elif more_is_better is None:
            improved = None
        else:
            improved = (new > old) if more_is_better else (new < old)
        rows.append(
            {
                "key": key,
                "label": label,
                "category": category,
                "before": old,
                "after": new,
                "improved": improved,
            }
        )
    return rows
