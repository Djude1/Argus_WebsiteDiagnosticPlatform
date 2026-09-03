"""Argus report design tokens — single source of truth for colours, fonts, sizing."""

# Brand palette (hex, no #)
NAVY      = "0C4A6E"   # primary brand / headings
SLATE     = "334155"   # body text
GREY      = "64748B"   # secondary text
LIGHTGREY = "94A3B8"   # captions / de-emphasis
BG        = "F1F5F9"   # zebra / evidence background
BGBLUE    = "DCEEF9"   # table header / card header band
LINE      = "E2E8F0"   # inner grid lines
BORD      = "CBD5E1"   # table outer border
FIXBLUE   = "F0F9FF"   # "怎麼修" action-zone fill

# Fonts
FONT_CJK  = "Microsoft JhengHei"
FONT_MONO = "Consolas"

# matplotlib 的 CJK 字型路徑。
#
# 原始 module 把路徑寫死並註明「override via env if needed」，但實作裡沒有讀任何
# 環境變數——缺字型時 matplotlib 直接 FileNotFoundError，而且訊息完全看不出該裝
# 什麼。這裡補上真正的解析順序，並在找不到時給出可執行的修法。
#
# 缺字型時刻意「大聲失敗」而不是退回預設字型：退回的話圖表中文會變成一整排 □，
# 報告照樣產出、照樣寄給客戶，沒有人會發現。
_FONT_CANDIDATES = (
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-TC-Regular.otf",
     "/usr/share/fonts/opentype/noto/NotoSansCJK-TC-Bold.otf"),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
     "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
)


def _resolve_cjk_fonts() -> tuple[str | None, str | None]:
    """找出可用的 CJK 字型；找不到回 (None, None)，**不在此拋例外**。

    這支是 module import 時執行的。早期版本在找不到字型時直接 raise，結果
    reports.py -> report_render 的 import 鏈讓整個 Django 在沒有字型的環境
    （CI runner）啟動失敗——連 `manage.py check` 都跑不起來。字型只有畫圖才
    需要，失敗就該發生在畫圖時，見 require_cjk_fonts()。
    """
    import os

    override_regular = os.getenv("ARGUS_REPORT_FONT_REGULAR")
    override_bold = os.getenv("ARGUS_REPORT_FONT_BOLD")
    if override_regular and override_bold:
        return override_regular, override_bold

    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            return regular, bold
    return None, None


MPL_FONT_REGULAR, MPL_FONT_BOLD = _resolve_cjk_fonts()


def require_cjk_fonts() -> tuple[str, str]:
    """畫圖前取得字型路徑；缺字型時在這裡失敗。

    刻意大聲失敗而不是退回預設字型：退回的話圖表中文會變成一整排 □，報告照樣
    產出、照樣寄給客戶，沒有人會發現。
    """
    if MPL_FONT_REGULAR and MPL_FONT_BOLD:
        return MPL_FONT_REGULAR, MPL_FONT_BOLD
    raise RuntimeError(
        "報告圖表需要 CJK 字型，但找不到任何一組。"
        "容器請安裝 fonts-noto-cjk（Debian/Ubuntu：apt-get install -y fonts-noto-cjk），"
        "或以環境變數 ARGUS_REPORT_FONT_REGULAR / ARGUS_REPORT_FONT_BOLD 指定路徑。"
        f"已嘗試：{[c[0] for c in _FONT_CANDIDATES]}"
    )

# 分類配色：沿用前端 AppShared.jsx 的 CATEGORY_COLOR，讓同一份掃描在畫面與報告
# 上顏色一致。payload 給的是顯示名稱（「SEO 搜尋引擎最佳化」「資訊安全」），所以
# 用前綴比對而不是完全比對，日後改顯示名稱也不會整組失效。
CATEGORY_COLOR = {
    "SEO": "6366F1",
    "AEO": "A855F7",
    "GEO": "06B6D4",
    "資訊安全": "EF4444",
    "使用者體驗": "10B981",
}


def category_color(name: str) -> str:
    for key, colour in CATEGORY_COLOR.items():
        if name.startswith(key):
            return colour
    return GREY


# Severity levels: label -> chip fill / text colour + ordering weight
SEVERITY = {
    "嚴重風險": {"fill": "B91C1C", "text": "FFFFFF", "order": 0},
    "高風險":   {"fill": "C2410C", "text": "FFFFFF", "order": 1},
    "中風險":   {"fill": "B45309", "text": "FFFFFF", "order": 2},
    "低風險":   {"fill": "0369A1", "text": "FFFFFF", "order": 3},
    "資訊提示": {"fill": "64748B", "text": "FFFFFF", "order": 4},
}
SEVERITY_ORDER = sorted(SEVERITY, key=lambda k: SEVERITY[k]["order"])

# Score-band colour (for donut / bars) by numeric score
def score_band_color(score):
    if score is None:
        return LIGHTGREY
    if score >= 80:
        return "15803D"   # green  良好
    if score >= 60:
        return "CA8A04"   # amber  需改善
    if score >= 40:
        return "C2410C"   # orange 建議儘快處理
    return "B91C1C"       # red    需優先處理

def score_band_label(score):
    if score >= 80: return "良好"
    if score >= 60: return "需改善"
    if score >= 40: return "建議儘快處理"
    return "需優先處理"
