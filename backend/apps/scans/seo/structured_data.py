"""結構化資料的 Google 複合式搜尋結果必填欄位檢查（roadmap §1 SEO 第 2 項）。

只檢查網站**已經有**的 JSON-LD：某個類型缺少 Google 列為必填（required）的欄位時，
該類型就不符合複合式搜尋結果資格。語法錯誤由 AEO 的 `aeo/markup.py` 回報，這裡略過無法解析的區塊。
不因為沒有某種標記就要求補上，也不檢查建議（recommended）欄位——那些只影響呈現的完整度。

必填欄位依 Google Search Central 各類型說明頁（2026-09 版）：
https://developers.google.com/search/docs/appearance/structured-data/search-gallery
FAQPage／HowTo 已不在 Google 支援的複合式搜尋結果清單中，不列入；
Article、Organization 沒有必填欄位。

只看頂層節點（區塊根、陣列、`@graph`、`mainEntity`）的類型規則，巢狀的實體多半只是被引用
（例如 Offer.itemOffered 裡的 Product），套用頂層規則會誤報。
Review／AggregateRating 不論出現在哪裡都檢查，
Offer 與活動地點只在 Product／Event 底下依該類型的規則檢查。純 `{"@id": ...}` 的參照節點不檢查。
"""

from __future__ import annotations

import json

DOCS = "https://developers.google.com/search/docs/appearance/structured-data/"

# 必填條件：每個 tuple 是「其中之一即可」的欄位路徑（點號＝巢狀）
Requirement = tuple[str, ...]

LOCAL_BUSINESS_TYPES = {
    "LocalBusiness", "Restaurant", "CafeOrCoffeeShop", "Bakery", "BarOrPub", "FastFoodRestaurant",
    "FoodEstablishment", "Store", "ClothingStore", "ElectronicsStore", "BookStore", "GroceryStore",
    "Dentist", "MedicalClinic", "Physician", "Pharmacy", "Hotel", "LodgingBusiness", "AutoRepair",
    "AutoDealer", "ProfessionalService", "LegalService", "Attorney", "AccountingService",
    "RealEstateAgent", "HealthAndBeautyBusiness", "BeautySalon", "HairSalon", "DaySpa",
    "SportsActivityLocation", "ExerciseGym", "EntertainmentBusiness", "TravelAgency",
    "HomeAndConstructionBusiness", "ChildCare", "EducationalOrganization",
}
EVENT_TYPES = {
    "Event", "MusicEvent", "Festival", "BusinessEvent", "EducationEvent", "SportsEvent",
    "TheaterEvent", "ExhibitionEvent", "ComedyEvent", "DanceEvent", "FoodEvent", "LiteraryEvent",
    "SaleEvent", "ScreeningEvent", "SocialEvent", "ChildrensEvent",
}

# 類型 → (中文名稱, 說明頁, 必填條件)
TYPE_RULES: dict[str, tuple[str, str, tuple[Requirement, ...]]] = {
    "Product": ("產品", "product-snippet", (("name",), ("review", "aggregateRating", "offers"))),
    "SoftwareApplication": (
        "軟體應用程式", "software-app",
        (("name",), ("offers.price",), ("aggregateRating", "review")),
    ),
    "JobPosting": (
        "職缺", "job-posting",
        (("datePosted",), ("description",), ("hiringOrganization",), ("title",),
         ("jobLocation", "jobLocationType")),
    ),
    "Recipe": ("食譜", "recipe", (("name",), ("image",))),
    "VideoObject": ("影片", "video", (("name",), ("thumbnailUrl",), ("uploadDate",))),
    "BreadcrumbList": ("導覽路徑", "breadcrumb", (("itemListElement",),)),
    "Event": ("活動", "event", (("name",), ("startDate",), ("location",))),
    "LocalBusiness": ("在地商家", "local-business", (("name",), ("address",))),
}
TYPE_ALIASES = {
    "MobileApplication": "SoftwareApplication",
    "WebApplication": "SoftwareApplication",
    **{name: "Event" for name in EVENT_TYPES},
    **{name: "LocalBusiness" for name in LOCAL_BUSINESS_TYPES},
}

REVIEW_RULES = ("評論", "review-snippet", (("author",), ("reviewRating.ratingValue",)))
AGGREGATE_RATING_RULES = (
    "評分彙總", "review-snippet", (("ratingValue",), ("ratingCount", "reviewCount")),
)
# (上層類型, 欄位) → {子節點類型: 規則}
NESTED_RULES: dict[tuple[str, str], dict[str, tuple[str, str, tuple[Requirement, ...]]]] = {
    ("Product", "offers"): {
        "Offer": ("產品優惠", "product-snippet", (("price", "priceSpecification.price"),)),
        "AggregateOffer": ("產品優惠", "product-snippet", (("lowPrice",), ("priceCurrency",))),
    },
    ("Event", "location"): {
        "Place": ("活動地點", "event", (("address",),)),
    },
}
SELF_SERVING_TYPES = {"Organization", "LocalBusiness"}
_TOP_LEVEL_KEYS = ("@graph", "mainEntity")


def _type_names(node: dict) -> list[str]:
    raw = node.get("@type") or []
    raw = raw if isinstance(raw, list) else [raw]
    # "https://schema.org/Product"、"schema:Product" → "Product"
    return [str(t).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1] for t in raw if t]


def _canonical(name: str) -> str:
    return TYPE_ALIASES.get(name, name)


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _has_path(node, path: str) -> bool:
    head, _, rest = path.partition(".")
    values = node if isinstance(node, list) else [node]
    for item in values:
        if not isinstance(item, dict):
            continue
        value = item.get(head)
        if not rest:
            if _present(value) and not (isinstance(value, list) and not any(map(_present, value))):
                return True
        elif value is not None and _has_path(value, rest):
            return True
    return False


def _missing(node: dict, requirements: tuple[Requirement, ...]) -> list[str]:
    return [
        "／".join(options) + ("（其中之一）" if len(options) > 1 else "")
        for options in requirements
        if not any(_has_path(node, path) for path in options)
    ]


def _is_reference(node: dict) -> bool:
    return set(node) <= {"@id", "@context"} and "@id" in node


def _top_level_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _top_level_nodes(item)
    elif isinstance(data, dict):
        yield data
        for key in _TOP_LEVEL_KEYS:
            if key in data:
                yield from _top_level_nodes(data[key])


def _as_dicts(value) -> list[dict]:
    values = value if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, dict) and not _is_reference(v)]


def _label(node: dict, fallback: str) -> str:
    name = node.get("name") or node.get("headline") or ""
    return str(name).strip()[:60] if isinstance(name, str) and name.strip() else fallback


def _check(node: dict, rules, where: str) -> dict | None:
    label, doc, requirements = rules
    missing = _missing(node, requirements)
    if not missing:
        return None
    return {"type": label, "item": where, "missing": missing, "doc": DOCS + doc}


def _check_ratings(node, where: str, issues: list[dict]) -> None:
    """Review／AggregateRating 不論在哪一層都檢查（巢狀時 itemReviewed 可省略）。"""
    if isinstance(node, list):
        for item in node:
            _check_ratings(item, where, issues)
        return
    if not isinstance(node, dict) or _is_reference(node):
        return
    types = {_canonical(t) for t in _type_names(node)}
    for key, value in node.items():
        if key == "review":
            for review in _as_dicts(value):
                issue = _check(review, REVIEW_RULES, where)
                if issue:
                    issues.append(issue)
        elif key == "aggregateRating":
            for rating in _as_dicts(value):
                issue = _check(rating, AGGREGATE_RATING_RULES, where)
                if issue:
                    issues.append(issue)
        # @graph／mainEntity 底下的節點會以頂層節點各自檢查，這裡不重複
        skip = {"review", "aggregateRating", *_TOP_LEVEL_KEYS}
        if isinstance(value, (dict, list)) and key not in skip:
            _check_ratings(value, where, issues)
    if "Review" in types:
        issue = _check(node, REVIEW_RULES, where)
        if issue:
            issues.append(issue)
    if "AggregateRating" in types:
        issue = _check(node, AGGREGATE_RATING_RULES, where)
        if issue:
            issues.append(issue)


def validate_blocks(json_ld_blocks: list[str]) -> dict:
    """{"issues": [{type, item, missing, doc}], "self_serving": [類型名稱], "checked": [類型]}。

    issues 依出現順序、同一項目同樣的缺漏只列一次。
    """
    issues: list[dict] = []
    self_serving: list[str] = []
    checked: list[str] = []
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        for node in _top_level_nodes(data):
            if _is_reference(node):
                continue
            names = _type_names(node)
            canonical = {_canonical(name) for name in names}
            for type_name in sorted(canonical & set(TYPE_RULES)):
                rules = TYPE_RULES[type_name]
                checked.append(rules[0])
                where = _label(node, rules[0])
                issue = _check(node, rules, where)
                if issue:
                    issues.append(issue)
                for (parent, key), child_rules in NESTED_RULES.items():
                    if parent != type_name:
                        continue
                    for child in _as_dicts(node.get(key)):
                        nested = _check_nested(child, child_rules, where)
                        if nested:
                            issues.append(nested)
                if type_name == "BreadcrumbList":
                    issues.extend(_check_breadcrumb_items(node, where))
            _check_ratings(node, _label(node, "結構化資料"), issues)
            if canonical & SELF_SERVING_TYPES and (
                _has_path(node, "aggregateRating") or _has_path(node, "review")
            ):
                self_serving.append(_label(node, "商家"))
    unique: list[dict] = []
    seen: set[tuple] = set()
    for issue in issues:
        key = (issue["type"], issue["item"], tuple(issue["missing"]))
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return {"issues": unique, "self_serving": self_serving, "checked": checked}


def _check_nested(child: dict, child_rules: dict, where: str) -> dict | None:
    """沒寫 @type 時視為該欄位的預設類型（規則表第一個）；活動地點只要不是線上活動都要有地址。"""
    types = {_canonical(t) for t in _type_names(child)}
    default = next(iter(child_rules))
    if not types or (default == "Place" and "VirtualLocation" not in types):
        types = {default}
    for child_type in sorted(types & set(child_rules)):
        return _check(child, child_rules[child_type], where)
    return None


def _check_breadcrumb_items(node: dict, where: str) -> list[dict]:
    """ListItem：position 必填；name 必填（item 是帶 name 的物件時可省略）；最後一項可省略 item。"""
    items = [i for i in (node.get("itemListElement") or []) if isinstance(i, dict)]
    issues = []
    for index, item in enumerate(items):
        missing = []
        if not _present(item.get("position")):
            missing.append("position")
        if not _present(item.get("name")) and not _has_path(item, "item.name"):
            missing.append("name")
        if index < len(items) - 1 and not _present(item.get("item")):
            missing.append("item")
        if missing:
            issues.append({
                "type": "導覽路徑項目",
                "item": f"{where} 第 {index + 1} 項",
                "missing": missing,
                "doc": DOCS + "breadcrumb",
            })
    return issues
