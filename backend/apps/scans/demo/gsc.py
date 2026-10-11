"""示範專案的 Search Console 資料（虛構，2026-10-11）。

示範專案是虛構網站，無法連接 Google；為了讓「SEO 分析 → 搜尋關鍵字」與報告的搜尋詞段落
可以完整瀏覽，回傳與 `seo.gsc.performance()` 同格式的固定資料。數字由搜尋詞與日期決定
（不用亂數），每次結果相同；畫面與報告都標示為示範資料。
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from zlib import crc32

from apps.scans.seo.gsc import ALLOWED_DAYS, period

# 示範專案預設的目標關鍵字（seed.py 建立時寫入，migration 0034 補到既有示範專案）：
# 與下方搜尋詞部分重疊，讓「目標關鍵字」與「有曝光但還不是目標的搜尋詞」兩張表都有內容
DEMO_TARGET_KEYWORDS = ["耶加雪菲", "手沖咖啡", "濾掛咖啡", "冷萃咖啡", "咖啡豆 訂閱"]

# (搜尋詞, 頁面路徑, 每日基準曝光, 點閱率, 平均排名)
QUERIES = (
    ("晨光咖啡", "/", 48, 0.31, 1.4),
    ("晨光咖啡烘焙所", "/", 22, 0.42, 1.1),
    ("台北 精品咖啡豆", "/", 64, 0.035, 8.6),
    ("耶加雪菲", "/products/ethiopia-yirgacheffe", 41, 0.052, 7.9),
    ("耶加雪菲 g1 風味", "/products/ethiopia-yirgacheffe", 12, 0.071, 5.3),
    ("綜合咖啡豆 推薦", "/products/house-blend", 35, 0.028, 11.2),
    ("濾掛咖啡 禮盒", "/products/drip-bag-gift-box", 52, 0.044, 6.8),
    ("咖啡禮盒 送禮", "/products/drip-bag-gift-box", 30, 0.019, 14.5),
    ("手沖咖啡 比例", "/blog/hand-drip-guide", 88, 0.026, 9.4),
    ("手沖咖啡 水溫", "/blog/hand-drip-guide", 46, 0.033, 7.2),
    ("手沖咖啡 新手", "/blog/hand-drip-guide", 27, 0.048, 6.1),
    ("冷萃咖啡 做法", "/blog/cold-brew-at-home", 73, 0.039, 6.5),
    ("冷萃咖啡 比例", "/blog/cold-brew-at-home", 31, 0.045, 5.9),
    ("拉花 教學", "/blog/latte-art-basics", 58, 0.017, 13.8),
    ("拉花 鬱金香", "/blog/latte-art-basics", 14, 0.036, 9.1),
    ("咖啡 杯測 活動", "/events", 9, 0.083, 4.2),
    ("台北 咖啡店 營業時間", "/stores", 19, 0.024, 12.6),
    ("晨光咖啡 菜單", "/menu", 11, 0.29, 1.8),
    ("咖啡豆 訂閱", "/subscribe", 16, 0.012, 18.4),
    ("咖啡師 徵才", "/careers", 7, 0.05, 10.3),
)


def _seed(*parts) -> float:
    """0～1 的固定擾動（同一組輸入永遠得到同一個值）。"""
    return (crc32("|".join(str(p) for p in parts).encode()) % 1000) / 1000


def _daily(query: str, base: int, day: date) -> int:
    weekly = 1 + 0.18 * math.sin(day.toordinal() * 2 * math.pi / 7)
    return max(0, round(base * weekly * (0.75 + 0.5 * _seed(query, day))))


def _rows(origin: str, start: date, end: date) -> tuple[list[dict], list[dict]]:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    queries, trend = [], {d: [0, 0] for d in days}
    for query, path, base, ctr, position in QUERIES:
        impressions = clicks = 0
        for day in days:
            shown = _daily(query, base, day)
            got = round(shown * ctr * (0.6 + 0.8 * _seed("c", query, day)))
            impressions += shown
            clicks += got
            trend[day][0] += got
            trend[day][1] += shown
        queries.append({
            "query": query,
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(clicks / impressions, 4) if impressions else 0,
            # 平均排名最好是 1，擾動後不可低於 1
            "position": max(1.0, round(position + (_seed("p", query, start) - 0.5) * 1.2, 1)),
            "page": origin.rstrip("/") + path,
        })
    queries.sort(key=lambda r: (-r["clicks"], -r["impressions"]))
    trend_rows = [
        {"date": d.isoformat(), "clicks": c, "impressions": i,
         "ctr": round(c / i, 4) if i else 0, "position": 0}
        for d, (c, i) in sorted(trend.items())
    ]
    return queries, trend_rows


def demo_performance(project, days: int, today: date | None = None) -> dict:
    """與 `gsc.performance()` 相同的回傳格式；搜尋詞附與前一期的比較。"""
    if days not in ALLOWED_DAYS:
        days = 28
    origin = project.origin
    start, end = period(days, today)
    queries, trend = _rows(origin, start, end)
    previous, _ = _rows(origin, start - timedelta(days=days), start - timedelta(days=1))
    before = {row["query"]: row for row in previous}
    for row in queries:
        old = before.get(row["query"])
        row["clicks_change"] = row["clicks"] - old["clicks"] if old else None
        row["position_change"] = round(old["position"] - row["position"], 1) if old else None
    pages: dict[str, dict] = {}
    for row in queries:
        page = pages.setdefault(row["page"], {"url": row["page"], "clicks": 0,
                                              "impressions": 0, "position": row["position"]})
        page["clicks"] += row["clicks"]
        page["impressions"] += row["impressions"]
    totals = {
        "clicks": sum(r["clicks"] for r in trend),
        "impressions": sum(r["impressions"] for r in trend),
    }
    shown = totals["impressions"]
    totals["ctr"] = round(totals["clicks"] / shown, 4) if shown else 0
    return {
        "property": demo_property(project),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "totals": totals,
        "queries": queries,
        "pages": [
            {**p, "ctr": round(p["clicks"] / p["impressions"], 4) if p["impressions"] else 0}
            for p in sorted(pages.values(), key=lambda p: -p["clicks"])
        ],
        "trend": trend,
        "demo": True,
    }


def demo_property(project) -> str:
    host = project.origin.split("://", 1)[-1].split("/", 1)[0]
    return f"sc-domain:{host.removeprefix('www.')}"


def demo_inspection(url: str) -> dict:
    """網址檢查：示範網站的頁面一律回「已收錄」（格式同 `gsc.inspect_url`）。"""
    return {
        "url": url,
        "verdict": "PASS",
        "coverage_state": "已提交並建立索引（示範資料）",
        "indexing_state": "INDEXING_ALLOWED",
        "robots_txt_state": "ALLOWED",
        "page_fetch_state": "SUCCESSFUL",
        "last_crawl_time": "",
        "google_canonical": url,
        "user_canonical": url,
    }
