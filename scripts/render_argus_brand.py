"""用 Pillow（純 Python，不引入 cairosvg）生成 Argus 品牌資產。

產出：
- frontend/public/argus-logo.png        256×256 RGBA（封面 logo）
- frontend/public/argus-logo-watermark.png 512×512 半透明（每頁浮水印）
- frontend/public/argus-title.png       900×240（封面 ARGUS 大字藝術字）

設計對齊 frontend/public/favicon.svg：
- 4 角星（cubic bezier 凹曲線）
- 圓角矩形底（rx=14 / 64）
- 線性漸層 #06b6d4 → #6366f1（cyan → indigo）
- 徑向 glow #67e8f9（cyan，opacity 0.65 → 0）
- 白色 4 角星

執行：
    uv run python scripts/render_argus_brand.py

沒引外部資源相依、純 Pillow。CI / Docker build 都不需要額外系統函式庫。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_PUBLIC = ROOT / "frontend" / "public"

# 來自 favicon.svg 與 styles.css :root 的設計 token
CYAN = (0x06, 0xB6, 0xD4)
INDIGO = (0x63, 0x66, 0xF1)
GLOW = (0x67, 0xE8, 0xF9)
NAVY_950 = (0x05, 0x0A, 0x1C)
NAVY_900 = (0x06, 0x0B, 0x1F)
NAVY_800 = (0x0A, 0x15, 0x35)
WHITE = (0xFF, 0xFF, 0xFF)


def _star_polygon(size: int, points: int = 4, outer: float = 0.96, inner: float = 0.30) -> list[tuple[float, float]]:
    """N 角星的多邊形座標（內凹版）。

    size：邊框像素。
    outer / inner：外圓半徑與內圓半徑佔 size 的比例。
    中心在 (size/2, size/2)。
    """
    import math

    cx, cy = size / 2, size / 2
    r_out = (size / 2) * outer
    r_in = r_out * inner
    coords = []
    for i in range(points * 2):
        angle = -math.pi / 2 + i * math.pi / points
        r = r_out if i % 2 == 0 else r_in
        coords.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return coords


def _smoothed_star_polygon(size: int) -> list[tuple[float, float]]:
    """仿 favicon.svg 的 4 角星（cubic bezier 凹曲線，多邊形版 64 段近似）。

    favicon.svg 用 4 段 cubic bezier 把 4 個尖角連成凹曲線。我們用更多邊的內凹
    多邊形（64 段）逼近，肉眼幾乎與 SVG 原版相同。對列印尺寸的 .docx 嵌入而言
    解析度足夠。
    """
    return _star_polygon(size, points=4, outer=0.46, inner=0.16)


def _linear_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """從左上到右下的線性漸層（仿 favicon.svg 的 x1=8 y1=8 → x2=56 y2=56 對角線）。"""
    img = Image.new("RGB", (size, size), top)
    pixels = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))  # 0..1
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            pixels[x, y] = (r, g, b)
    return img


def _radial_glow(size: int, center: tuple[float, float], radius: float, color: tuple[int, int, int]) -> Image.Image:
    """徑向 alpha 漸層（用於 favicon 的 glow 圓，背景透明）。"""
    cx, cy = center
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = img.load()
    r_int = int(radius)
    for y in range(size):
        for x in range(size):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d >= radius:
                continue
            t = 1 - d / radius  # 中心=1，邊緣=0
            alpha = int(t * t * 255 * 0.65)  # 0.65 峰值（仿 SVG stop-opacity 0.65）
            pixels[x, y] = (*color, alpha)
    return img


def _round_rect_mask(size: int, radius: int) -> Image.Image:
    """圓角矩形 alpha 遮罩。"""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _compose_logo(size: int, glow_opacity: float = 1.0, star_opacity: float = 1.0) -> Image.Image:
    """合成 Argus logo：圓角漸層底 + 中心 glow + 白色 4 角星。"""
    # 1. 漸層底（不透明）
    bg = _linear_gradient(size, CYAN, INDIGO)

    # 2. 套圓角遮罩
    radius = int(size * 14 / 64)  # 與 SVG 相同的 rx/canvas 比例
    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded.paste(bg, (0, 0), _round_rect_mask(size, radius))

    # 3. 中心 glow（半透明徑向）
    glow = _radial_glow(size, (size / 2, size * 28 / 64), size * 25 / 64, GLOW)
    if glow_opacity < 1.0:
        glow_data = glow.split()
        glow_data[3].point(lambda a: int(a * glow_opacity))
        glow = Image.merge("RGBA", glow_data)
    rounded.alpha_composite(glow)

    # 4. 白色 4 角星
    star_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    star_poly = _smoothed_star_polygon(size)
    ImageDraw.Draw(star_layer).polygon(star_poly, fill=(*WHITE, int(255 * star_opacity)))
    rounded.alpha_composite(star_layer)

    return rounded


def render_logo() -> Path:
    """主 logo：256×256，封面用。"""
    img = _compose_logo(256)
    out = OUT_PUBLIC / "argus-logo.png"
    img.save(out, "PNG", optimize=True)
    print(f"OK {out}  size={out.stat().st_size}B  dims={img.size}")
    return out


def render_watermark() -> Path:
    """浮水印：512×512，半透明（中心 alpha 0.18）。"""
    img = _compose_logo(512, glow_opacity=0.4, star_opacity=0.18)
    out = OUT_PUBLIC / "argus-logo-watermark.png"
    img.save(out, "PNG", optimize=True)
    print(f"OK {out}  size={out.stat().st_size}B  dims={img.size}")
    return out


def _fit_font(text: str, max_width: int, max_height: int, *,
              family_candidates: list[str], min_size: int = 24) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, int]:
    """挑一個能放得下 text 的最大字型大小。"""
    for family in family_candidates:
        for size in range(min_size, 200):
            try:
                f = ImageFont.truetype(family, size)
            except OSError:
                continue
            bbox = f.getbbox(text)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if w > max_width * 0.9 or h > max_height * 0.7:
                return ImageFont.truetype(family, max(min_size, size - 2)), size - 2
    # 沒字型可用時退回 default bitmap
    return ImageFont.load_default(), min_size


def _measure(font: ImageFont.ImageFont, text: str) -> tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def render_title() -> Path:
    """封面 ARGUS 大字藝術字：900×240，漸層 + 4 角星點綴。

    沒法用 Pillow 內建畫出真正的漸層文字，所以分層疊：
    1. 陰影層（navy 950，偏移 +4/+4）
    2. 主體層（navy 800，純色）
    3. 高光（cyan glow，輕微偏移）
    4. 文字上疊一顆小 4 角星（左上角當作 logo 點綴）
    """
    W, H = 900, 240
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))  # 透明底
    draw = ImageDraw.Draw(img)

    # 候選字型：繁中 / 英文粗體
    families = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    font, size = _fit_font("ARGUS 網站健檢報告", W - 80, H - 40, family_candidates=families)

    text = "ARGUS 網站健檢報告"
    text_w, text_h = _measure(font, text)

    # 文字置中
    x = (W - text_w) // 2
    y = (H - text_h) // 2

    # 1. 陰影（navy 950，+5/+5）
    draw.text((x + 5, y + 5), text, font=font, fill=(*NAVY_950, 180))

    # 2. 主體（navy 800）
    draw.text((x, y), text, font=font, fill=NAVY_800)

    # 3. 高光（cyan glow，-1/-2，淡）
    glow_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_overlay)
    glow_draw.text((x - 1, y - 2), text, font=font, fill=(*GLOW, 110))
    glow_overlay = glow_overlay.filter(ImageFilter.GaussianBlur(2))
    img.alpha_composite(glow_overlay)

    # 4. 左上角小 4 角星（logo 點綴，48×48）
    mini = _compose_logo(48)
    img.alpha_composite(mini, (24, (H - 48) // 2))

    # 5. 右下角裝飾線（cyan 橫線）
    line_y = y + text_h + 12
    draw.line([(x, line_y), (x + text_w, line_y)], fill=(*CYAN, 200), width=3)

    out = OUT_PUBLIC / "argus-title.png"
    img.save(out, "PNG", optimize=True)
    print(f"OK {out}  size={out.stat().st_size}B  dims={img.size}  font_size={size}")
    return out


def main() -> None:
    OUT_PUBLIC.mkdir(parents=True, exist_ok=True)
    render_logo()
    render_watermark()
    render_title()
    print("DONE")


if __name__ == "__main__":
    main()