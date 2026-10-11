"""Programmatic chart generation for Argus reports.

All charts are driven by the report data dict — the Agent never edits images by
hand. Each function writes a transparent PNG and returns its path.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import numpy as np

from . import theme as T

# 字型延後建立：module import 時解析會讓沒有 CJK 字型的環境（CI runner）連
# Django 都啟動不了。改由 build_all() 在真的要畫圖時呼叫 _ensure_fonts()。
_reg = None
_bold = None


def _ensure_fonts():
    global _reg, _bold
    if _reg is None or _bold is None:
        regular_path, bold_path = T.require_cjk_fonts()
        _reg = fm.FontProperties(fname=regular_path)
        _bold = fm.FontProperties(fname=bold_path)


def _hex(c):  # matplotlib wants leading '#'
    return "#" + c


def score_donut(score, out):
    fig, ax = plt.subplots(figsize=(3.0, 3.0), dpi=T.chart_dpi())
    col = _hex(T.score_band_color(score))
    ax.pie([score, 100 - score], colors=[col, _hex(T.LINE)],
           startangle=90, counterclock=False,
           wedgeprops=dict(width=0.30, edgecolor="white", linewidth=1.5))
    ax.text(0, 0.12, str(score), ha="center", va="center",
            fontproperties=_bold, fontsize=52, color=col)
    ax.text(0, -0.30, "/ 100", ha="center", va="center",
            fontproperties=_reg, fontsize=15, color=_hex(T.LIGHTGREY))
    ax.set(aspect="equal")
    plt.tight_layout(pad=0.1)
    plt.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return out


def category_bars(categories, out):
    """categories: list of {name, score} (score may be None = 未評估)."""
    cats = [c["name"] for c in categories]
    vals = [c["score"] for c in categories]
    fig, ax = plt.subplots(figsize=(5.6, 0.55 * len(cats) + 0.4), dpi=T.chart_dpi())
    y = np.arange(len(cats))[::-1]
    ax.barh(y, 100, color="#F1F5F9", height=0.55, zorder=1)
    for yi, v in zip(y, vals):
        if v is None:
            ax.text(2, yi, "未評估", va="center", ha="left",
                    fontproperties=_reg, fontsize=11, color=_hex(T.LIGHTGREY))
            continue
        ax.barh(yi, v, color=_hex(T.score_band_color(v)), height=0.55, zorder=2)
        ax.text(v + 2, yi, f"{v}", va="center", ha="left",
                fontproperties=_bold, fontsize=13, color=_hex(T.SLATE))
    ax.set_yticks(y)
    ax.set_yticklabels(cats, fontproperties=_reg, fontsize=12, color=_hex(T.SLATE))
    ax.set_xlim(0, 112)
    ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    for thr in (60, 80):
        ax.axvline(thr, color=_hex(T.LIGHTGREY), lw=0.8, ls=(0, (3, 3)), zorder=3)
    plt.tight_layout(pad=0.2)
    plt.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return out


def severity_bar(counts, out):
    """counts: dict severity_label -> int. Draws a single stacked bar."""
    fig, ax = plt.subplots(figsize=(5.6, 0.78), dpi=T.chart_dpi())
    left = 0
    total = sum(counts.get(s, 0) for s in T.SEVERITY_ORDER) or 1
    for s in T.SEVERITY_ORDER:
        n = counts.get(s, 0)
        if n == 0:
            continue
        ax.barh(0, n, left=left, color=_hex(T.SEVERITY[s]["fill"]),
                height=0.6, edgecolor="white", linewidth=2)
        ax.text(left + n / 2, 0, f"{n}", ha="center", va="center",
                fontproperties=_bold, fontsize=13, color="white")
        left += n
    ax.set_xlim(0, total)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")
    plt.tight_layout(pad=0.1)
    plt.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return out


def category_share(ordered_counts, out):
    """ordered_counts: [(顯示名稱, 數量), ...]，畫成單一條堆疊佔比。

    回答的是「問題集中在哪一類」，與上方「各分類分數」的「這一類做得多好」互補。
    佔比小的分段塞不下數字，數量由 report.py 在圖下方以文字圖例呈現。
    """
    fig, ax = plt.subplots(figsize=(5.6, 0.78), dpi=T.chart_dpi())
    total = sum(n for _, n in ordered_counts) or 1
    left = 0
    for name, n in ordered_counts:
        if n == 0:
            continue
        ax.barh(0, n, left=left, color=_hex(T.category_color(name)),
                height=0.6, edgecolor="white", linewidth=2)
        if n / total >= 0.08:      # 太窄的分段放不下字，留白比擠成一團好讀
            ax.text(left + n / 2, 0, f"{n}", ha="center", va="center",
                    fontproperties=_bold, fontsize=13, color="white")
        left += n
    ax.set_xlim(0, total)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")
    plt.tight_layout(pad=0.1)
    plt.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return out


def trend_line(prev, curr, out):
    """prev/curr: {date, score}. Draws a 2-point sparkline."""
    fig, ax = plt.subplots(figsize=(2.4, 1.5), dpi=T.chart_dpi())
    xs, ys = [0, 1], [prev["score"], curr["score"]]
    ax.plot(xs, ys, color=_hex(T.NAVY), lw=2.5, marker="o", markersize=7,
            markerfacecolor=_hex(T.NAVY), zorder=3)
    ax.fill_between(xs, ys, 0, color=_hex(T.NAVY), alpha=0.07, zorder=1)
    for x, yv in zip(xs, ys):
        ax.text(x, yv + 7, str(yv), ha="center",
                fontproperties=_bold, fontsize=13, color=_hex(T.NAVY))
    ax.set_xlim(-0.25, 1.25)
    ax.set_ylim(0, 100)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([prev["date"], curr["date"]],
                       fontproperties=_reg, fontsize=9, color=_hex(T.LIGHTGREY))
    ax.set_yticks([])
    for name in ("top", "right", "left"):
        ax.spines[name].set_visible(False)
    ax.spines["bottom"].set_color(_hex(T.LINE))
    ax.tick_params(length=0)
    plt.tight_layout(pad=0.2)
    plt.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return out


# ---------- 網站總覽：效能、連結、搜尋詞與拓撲（Argus 在地擴充，2026-10-11） ----------
# 狀態色（良好／需改善／不佳）一律附文字標籤，不只靠顏色；與 Google PageSpeed 的門檻一致
GOOD, WARN, BAD, MUTED, BLUE = "15803D", "B45309", "B91C1C", "94A3B8", "1F6591"


def _status_color(score):
    if score >= 90:
        return GOOD
    return WARN if score >= 50 else BAD


def _status_label(score):
    if score >= 90:
        return "良好"
    return "需改善" if score >= 50 else "不佳"


def _save(fig, out):
    plt.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return out


def perf_gauges(scores, out):
    """Lighthouse 四項分數：一列圓環儀表，中間大數字、下方名稱與等級。"""
    n = len(scores)
    fig, axes = plt.subplots(1, n, figsize=(1.75 * n, 2.15), dpi=T.chart_dpi())
    axes = np.atleast_1d(axes)
    for ax, item in zip(axes, scores):
        score = item["score"]
        col = _hex(_status_color(score))
        ax.pie([score, 100 - score], colors=[col, _hex(T.LINE)], startangle=90,
               counterclock=False, wedgeprops=dict(width=0.22, edgecolor="white", linewidth=1.2))
        ax.text(0, 0.02, str(score), ha="center", va="center",
                fontproperties=_bold, fontsize=24, color=col)
        ax.text(0, -1.42, item["label"], ha="center", va="center",
                fontproperties=_bold, fontsize=11, color=_hex(T.SLATE))
        ax.text(0, -1.78, _status_label(score), ha="center", va="center",
                fontproperties=_reg, fontsize=9, color=_hex(T.GREY))
        ax.set(aspect="equal")
        ax.set_ylim(-1.95, 1.1)
    plt.tight_layout(pad=0.2, w_pad=1.2)
    return _save(fig, out)


_LINK_COLORS = {"ok": GOOD, "redirect": BLUE, "broken": BAD, "unknown": WARN, "unchecked": MUTED}


def link_matrix(matrix, group_labels, out):
    """站內／子網域／站外連結各一條堆疊長條，依檢查結果分段；圖例在下方。"""
    rows = [m for m in matrix if m["total"]]
    fig, ax = plt.subplots(figsize=(5.8, 0.42 * len(rows) + 0.6), dpi=T.chart_dpi())
    width = max(m["total"] for m in rows)
    for i, m in enumerate(rows[::-1]):
        left = 0
        for g in group_labels:
            n = m["groups"].get(g["key"], 0)
            if not n:
                continue
            ax.barh(i, n, left=left, height=0.62, color=_hex(_LINK_COLORS[g["key"]]),
                    edgecolor="white", linewidth=2)
            if n / width >= 0.06:
                ax.text(left + n / 2, i, str(n), ha="center", va="center",
                        fontproperties=_bold, fontsize=10.5, color="white")
            left += n
        ax.text(left + width * 0.015, i, f"共 {m['total']}", va="center", ha="left",
                fontproperties=_reg, fontsize=9.5, color=_hex(T.GREY))
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([m["type"] for m in rows[::-1]], fontproperties=_reg, fontsize=11,
                       color=_hex(T.SLATE))
    ax.set_xlim(0, width * 1.14)
    ax.set_xticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    present = [g for g in group_labels if any(m["groups"].get(g["key"]) for m in rows)]
    handles = [plt.Rectangle((0, 0), 1, 1, color=_hex(_LINK_COLORS[g["key"]])) for g in present]
    leg = ax.legend(handles, [g["label"] for g in present], loc="upper center",
                    bbox_to_anchor=(0.5, -0.02), ncol=len(present), frameon=False,
                    prop=_reg, handlelength=1, handleheight=1, columnspacing=1.4)
    for text in leg.get_texts():
        text.set_color(_hex(T.GREY))
        text.set_fontsize(9)
    plt.tight_layout(pad=0.2)
    return _save(fig, out)


def kpi_tiles(tiles, out):
    """一列數字卡：大數字＋說明（Search Console 點擊、曝光、點閱率、搜尋詞數）。"""
    n = len(tiles)
    fig, ax = plt.subplots(figsize=(6.2, 1.15), dpi=T.chart_dpi())
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for i, tile in enumerate(tiles):
        ax.add_patch(plt.Rectangle((i + 0.04, 0.04), 0.92, 0.92, facecolor=_hex(T.BG),
                                   edgecolor=_hex(T.LINE), linewidth=0.8))
        ax.text(i + 0.5, 0.6, tile["value"], ha="center", va="center",
                fontproperties=_bold, fontsize=19, color=_hex(T.NAVY))
        ax.text(i + 0.5, 0.24, tile["label"], ha="center", va="center",
                fontproperties=_reg, fontsize=9.5, color=_hex(T.GREY))
    return _save(fig, out)


def search_trend(trend, out):
    """每日點擊與每日曝光：兩張並排的小圖（各自的縱軸，不做雙軸圖）。"""
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 1.9), dpi=T.chart_dpi())
    dates = [t["date"] for t in trend]
    xs = np.arange(len(dates))
    for ax, key, title in ((axes[0], "clicks", "每日點擊"), (axes[1], "impressions", "每日曝光")):
        ys = [t[key] for t in trend]
        ax.plot(xs, ys, color=_hex(T.NAVY), lw=1.6, zorder=3)
        ax.fill_between(xs, ys, 0, color=_hex(T.NAVY), alpha=0.08, zorder=1)
        peak = max(ys) if ys else 0
        ax.set_title(f"{title}（最高 {peak:,}）", fontproperties=_bold, fontsize=10,
                     color=_hex(T.SLATE), loc="left")
        ax.set_ylim(0, peak * 1.15 or 1)
        ax.set_xticks([0, len(xs) - 1] if len(xs) > 1 else [0])
        ax.set_xticklabels([dates[0][5:].replace("-", "/"), dates[-1][5:].replace("-", "/")]
                           if len(xs) > 1 else [dates[0][5:]],
                           fontproperties=_reg, fontsize=8, color=_hex(T.LIGHTGREY))
        ax.yaxis.set_major_locator(plt.MaxNLocator(3, integer=True))
        for label in ax.get_yticklabels():
            label.set_fontproperties(_reg)
            label.set_fontsize(8)
            label.set_color(_hex(T.LIGHTGREY))
        ax.grid(axis="y", color=_hex(T.LINE), lw=0.6)
        for name in ("top", "right", "left"):
            ax.spines[name].set_visible(False)
        ax.spines["bottom"].set_color(_hex(T.LINE))
        ax.tick_params(length=0)
    plt.tight_layout(pad=0.3, w_pad=2.0)
    return _save(fig, out)


_TONE_COLORS = {"good": GOOD, "medium": WARN, "bad": BAD, "blocked": MUTED}
_TONE_LABELS = {"good": "沒有中風險以上問題", "medium": "有中風險問題",
                "bad": "有高風險以上問題", "blocked": "被阻擋或回應錯誤"}


def _tree(nodes, edges):
    """從入口頁以 BFS 建立樹：每頁取第一個發現它的上層頁；連不到的頁掛在入口頁下。"""
    ids = [n["id"] for n in nodes]
    root = min(nodes, key=lambda n: (n["depth"], n["id"]))["id"]
    adjacency = {i: [] for i in ids}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)
    parent = {root: None}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for nxt in adjacency.get(current, []):
            if nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    for i in ids:
        parent.setdefault(i, root)
    children = {i: [] for i in ids}
    for child, par in parent.items():
        if par is not None:
            children[par].append(child)
    return root, parent, children


def topology_map(nodes, edges, out):
    """放射狀樹：入口頁在中央，依連結層級往外；節點顏色＝該頁最高嚴重度。"""
    by_id = {n["id"]: n for n in nodes}
    root, parent, children = _tree(nodes, edges)
    leaves = {}

    def count(node):
        leaves[node] = sum(count(c) for c in children[node]) or 1
        return leaves[node]

    count(root)
    pos, level = {}, {root: 0}

    def place(node, start, span):
        mid = start + span / 2
        r = level[node]
        pos[node] = (r * np.cos(mid), r * np.sin(mid))
        cursor = start
        for child in sorted(children[node], key=lambda c: by_id[c]["label"]):
            share = span * leaves[child] / leaves[node]
            level[child] = r + 1
            place(child, cursor, share)
            cursor += share

    place(root, np.pi / 2, 2 * np.pi)
    fig, ax = plt.subplots(figsize=(6.2, 5.4), dpi=T.chart_dpi())
    tree_edges = {(p, c) for c, p in parent.items() if p is not None}
    for source, target in edges:
        if (source, target) in tree_edges or (target, source) in tree_edges:
            continue
        (x1, y1), (x2, y2) = pos[source], pos[target]
        ax.plot([x1, x2], [y1, y2], color=_hex(T.LINE), lw=0.4, zorder=1)
    for p, c in tree_edges:
        (x1, y1), (x2, y2) = pos[p], pos[c]
        ax.plot([x1, x2], [y1, y2], color=_hex(T.BORD), lw=1.0, zorder=2)
    many = len(nodes) > 24
    for node_id, (x, y) in pos.items():
        n = by_id[node_id]
        size = 260 if node_id == root else 90
        ax.scatter(x, y, s=size, color=_hex(_TONE_COLORS.get(n["tone"], MUTED)),
                   edgecolors="white", linewidths=1.6, zorder=3)
        if node_id == root or level[node_id] == 1 or not many:
            label = n["label"] if len(n["label"]) <= 20 else n["label"][:19] + "…"
            ax.text(x, y - (0.16 if node_id == root else 0.12), label, ha="center", va="top",
                    fontproperties=_reg, fontsize=7.5 if many else 8, color=_hex(T.SLATE),
                    zorder=4)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.margins(0.12)
    present = [t for t in _TONE_LABELS if any(n["tone"] == t for n in nodes)]
    handles = [plt.Line2D([0], [0], marker="o", color="w", markersize=8,
                          markerfacecolor=_hex(_TONE_COLORS[t])) for t in present]
    leg = ax.legend(handles, [_TONE_LABELS[t] for t in present], loc="upper center",
                    bbox_to_anchor=(0.5, 0.0), ncol=min(len(present), 4), frameon=False,
                    prop=_reg, columnspacing=1.2, handletextpad=0.3)
    for text in leg.get_texts():
        text.set_color(_hex(T.GREY))
        text.set_fontsize(8.5)
    plt.tight_layout(pad=0.2)
    return _save(fig, out)


def _site_metric_charts(sm, p):
    paths = {}
    perf = sm.get("performance") or {}
    if perf.get("scores"):
        paths["perf_gauges"] = perf_gauges(perf["scores"], p("chart_perf.png"))
    links = sm.get("links") or {}
    if any(m["total"] for m in links.get("matrix") or []):
        paths["link_matrix"] = link_matrix(links["matrix"], links["group_labels"],
                                           p("chart_links.png"))
    search = sm.get("search") or {}
    if search.get("totals"):
        t = search["totals"]
        paths["search_kpis"] = kpi_tiles([
            {"value": f"{t['clicks']:,}", "label": "點擊"},
            {"value": f"{t['impressions']:,}", "label": "曝光"},
            {"value": f"{t['ctr'] * 100:.1f}%", "label": "點閱率（CTR）"},
            {"value": f"{t['queries']:,}", "label": "搜尋詞數"},
        ], p("chart_search_kpis.png"))
        if search.get("trend"):
            paths["search_trend"] = search_trend(search["trend"], p("chart_search_trend.png"))
    topo = sm.get("topology") or {}
    if topo.get("nodes"):
        paths["topology"] = topology_map(topo["nodes"], topo["edges"], p("chart_topology.png"))
    return paths


def build_all(data, workdir):
    """Generate every chart the report needs; return a dict of paths."""
    _ensure_fonts()
    os.makedirs(workdir, exist_ok=True)
    p = lambda n: os.path.join(workdir, n)
    summary = data["summary"]
    counts = {f["severity"]: 0 for f in data["findings"]}
    for f in data["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    paths = {
        "score": score_donut(summary["overall_score"], p("chart_score.png")),
        "categories": category_bars(summary["categories"], p("chart_categories.png")),
        "severity": severity_bar(counts, p("chart_severity.png")),
    }
    # 分類佔比同樣由 findings 推導，不必擴充 schema。順序沿用 summary.categories，
    # 與上方的分類分數長條對齊，讀者兩張圖之間不用重新找對應。
    cat_counts = {}
    for f in data["findings"]:
        cat_counts[f["category"]] = cat_counts.get(f["category"], 0) + 1
    ordered = [(c["name"], cat_counts.get(c["name"], 0)) for c in summary["categories"]]
    for name, n in sorted(cat_counts.items()):     # findings 帶了但 summary 沒有的分類
        if not any(name == existing for existing, _ in ordered):
            ordered.append((name, n))
    if any(n for _, n in ordered):
        paths["category_share"] = category_share(ordered, p("chart_cat_share.png"))
    if data.get("site_metrics"):
        paths.update(_site_metric_charts(data["site_metrics"], p))
    if summary.get("previous"):
        paths["trend"] = trend_line(
            summary["previous"],
            {"date": summary["scan_date"], "score": summary["overall_score"]},
            p("chart_trend.png"))
    return paths
