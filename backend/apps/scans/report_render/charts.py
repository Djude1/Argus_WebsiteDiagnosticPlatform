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

_reg = fm.FontProperties(fname=T.MPL_FONT_REGULAR)
_bold = fm.FontProperties(fname=T.MPL_FONT_BOLD)


def _hex(c):  # matplotlib wants leading '#'
    return "#" + c


def score_donut(score, out):
    fig, ax = plt.subplots(figsize=(3.0, 3.0), dpi=300)
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
    fig, ax = plt.subplots(figsize=(5.6, 0.55 * len(cats) + 0.4), dpi=300)
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
    fig, ax = plt.subplots(figsize=(5.6, 0.78), dpi=300)
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


def trend_line(prev, curr, out):
    """prev/curr: {date, score}. Draws a 2-point sparkline."""
    fig, ax = plt.subplots(figsize=(2.4, 1.5), dpi=300)
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


def build_all(data, workdir):
    """Generate every chart the report needs; return a dict of paths."""
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
    if summary.get("previous"):
        paths["trend"] = trend_line(
            summary["previous"],
            {"date": summary["scan_date"], "score": summary["overall_score"]},
            p("chart_trend.png"))
    return paths
