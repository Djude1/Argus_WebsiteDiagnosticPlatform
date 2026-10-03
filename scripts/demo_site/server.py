"""示範專案用的虛構網站：晨光咖啡烘焙所（www.morninglight-coffee.example）。

只用來重新產生示範資料（backend/apps/scans/demo/），不是產品的一部分，也不會部署。
網站刻意埋了各維度常見的問題，並有三個版本模擬「網站逐步改善」：
  v1：問題最多（約一個月前的第一次掃描）
  v2：修掉一部分（meta description、H1、.env 外洩、X-Content-Type-Options…）
  v3：再修一部分（升級 jQuery、移除 X-Powered-By 與前端金鑰、Cookie 加 HttpOnly、加 X-Frame-Options、llms.txt），
      也新增少數新問題（新文章缺 alt、新的 JS 錯誤），讓問題分析有「新增／持續／未出現」

用法（重產步驟見 backend/apps/scans/demo/README.md）：
  python scripts/demo_site/server.py --version 1 --port 80
www.morninglight-coffee.example、morninglight-coffee.example 與 shop.morninglight-coffee.example
需在 /etc/hosts 指到 127.0.0.1（裸網域在 v1 重複提供內容、v2 起 301 到 www；shop 是子網域商店）；所有內容（電話、Email、金鑰）都是虛構的。
"""

from __future__ import annotations

import argparse
import html
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = 1
HOST = "www.morninglight-coffee.example"
BRAND = "晨光咖啡烘焙所"

# ── 共用樣式：讓截圖像一個真的小品牌網站 ──
CSS = """
*{box-sizing:border-box}body{margin:0;font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;color:#3b2a20;background:#fbf7f2;line-height:1.7}
a{color:#9a4b1f}header.top{background:#2f1d14;color:#f6e7d6;padding:14px 32px;display:flex;align-items:center;gap:28px}
header.top .logo{font-weight:800;font-size:20px;letter-spacing:2px;color:#f6c48a;text-decoration:none}
header.top nav a{color:#f6e7d6;margin-right:18px;text-decoration:none;font-size:15px}
.hero{background:linear-gradient(120deg,#5b3420,#b8733b 60%,#f0b878);color:#fff8ef;padding:72px 32px}
.hero h1,.hero .h1{font-size:40px;margin:0 0 12px;font-weight:800}.hero p{max-width:620px;font-size:18px;margin:0 0 22px}
.btn{display:inline-block;background:#f6c48a;color:#2f1d14;padding:12px 22px;border-radius:999px;font-weight:700;text-decoration:none}
main{max-width:1080px;margin:0 auto;padding:40px 32px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}.card{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 18px rgba(80,40,10,.08)}
.card img{width:100%;height:170px;object-fit:cover;border-radius:12px;background:#ead7c3}
.price{color:#b8733b;font-weight:800;font-size:18px}
h2{font-size:26px;margin:36px 0 14px}footer{background:#2f1d14;color:#d8c2ac;padding:28px 32px;font-size:14px}
footer .social a{display:inline-block;width:18px;height:18px;margin-right:4px;background:#f6c48a;border-radius:4px;font-size:10px;text-align:center;line-height:18px;color:#2f1d14;text-decoration:none}
table{border-collapse:collapse;background:#fff}td,th{border:1px solid #ead7c3;padding:8px 14px;white-space:nowrap}
.menu-table{min-width:760px}form .row{margin-bottom:12px}input,textarea,select{width:100%;padding:10px;border:1px solid #d9c2a9;border-radius:10px;font:inherit}
.notice{background:#fff3e0;border:1px solid #f0c48a;border-radius:12px;padding:12px 16px}
.faq dt{font-weight:800;margin-top:16px}.faq dd{margin:4px 0 0}
.tag{display:inline-block;background:#f3e2cf;border-radius:999px;padding:2px 10px;font-size:13px;margin-right:6px}
"""

PRODUCTS = [
    ("ethiopia-yirgacheffe", "衣索比亞 耶加雪菲 G1", 520, "花香、柑橘與紅茶尾韻，淺焙。", "#e7b87a"),
    ("house-blend", "晨光招牌綜合豆", 420, "可可、堅果與焦糖甜感，中深焙，適合拿鐵。", "#a8653a"),
    ("drip-bag-gift-box", "濾掛咖啡禮盒（20 入）", 680, "四種產區各 5 包，節慶送禮熱銷。", "#c98d52"),
]

POSTS = [
    ("hand-drip-guide", "新手手沖咖啡完整指南：器材、比例與水溫", "2025-08-12"),
    ("latte-art-basics", "拉花入門：從愛心到鬱金香的五個練習", "2025-09-03"),
]
NEW_POST = ("cold-brew-at-home", "在家做冷萃咖啡：12 小時的零失敗配方", "2025-10-01")


def svg_image(color: str, label: str) -> str:
    """商品示意圖（SVG），避免依賴外部圖片。"""
    label = html.escape(label)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420" viewBox="0 0 640 420">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{color}"/>'
        f'<stop offset="1" stop-color="#3b2416"/></linearGradient></defs>'
        f'<rect width="640" height="420" fill="url(#g)"/>'
        f'<circle cx="320" cy="200" r="110" fill="#2f1d14" opacity=".55"/>'
        f'<ellipse cx="320" cy="200" rx="70" ry="95" fill="#6b3b20" transform="rotate(25 320 200)"/>'
        f'<path d="M290 120 C 340 180, 300 230, 350 285" stroke="#2f1d14" stroke-width="10" fill="none"/>'
        f'<text x="320" y="380" font-size="30" text-anchor="middle" fill="#fff6ea" font-family="sans-serif">{label}</text></svg>'
    )


def layout(title: str, body: str, *, description: str | None, canonical: bool = True,
           og: bool = True, extra_head: str = "", path: str = "/") -> str:
    v = VERSION
    meta_desc = f'<meta name="description" content="{html.escape(description)}">' if description else ""
    canon = f'<link rel="canonical" href="http://{HOST}{path}">' if canonical else ""
    og_tags = (
        f'<meta property="og:title" content="{html.escape(title)}">'
        f'<meta property="og:description" content="{html.escape(description or BRAND)}">'
        f'<meta property="og:image" content="http://{HOST}/static/img/og-cover.svg">'
        if og and v >= 2 else ""
    )
    # v1、v2 載入有已知漏洞的舊版 jQuery；v3 升級
    jquery = "/static/js/jquery-1.8.2.min.js" if v < 3 else "/static/js/jquery-3.7.1.min.js"
    # 外部 CDN 腳本沒有 SRI（每版都有，屬持續問題）
    cdn = '<script src="https://cdn.jsdelivr.net/npm/lazysizes@5.3.2/lazysizes.min.js" async></script>'
    # 連結問題（SEO 分析頁的「連結」）：外部社群、子網域商店；LINE 是純圖片連結，v1、v2 缺 alt＝沒有可讀文字
    line_alt = ' alt="LINE 官方帳號"' if v >= 3 else ""
    social = ('<span class="social"><a href="https://www.instagram.com/morninglight.coffee/" aria-label="Instagram">IG</a>'
              '<a href="https://zh.wikipedia.org/wiki/%E5%92%96%E5%95%A1" aria-label="認識咖啡">Wiki</a>'
              f'<a href="https://line.me/R/ti/p/@morninglight"><img src="/static/img/line.svg" width="18" height="18"{line_alt}></a></span>'
              f' <a href="http://shop.{HOST.removeprefix("www.")}/" style="color:#f6c48a">線上商店</a>')
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>{meta_desc}{canon}{og_tags}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>{CSS}</style>{extra_head}
<script src="{jquery}"></script>{cdn}
<script src="/static/js/config.js"></script>
</head><body>
<header class="top"><a class="logo" href="/">晨光 MORNING LIGHT</a>
<nav><a href="/menu">菜單</a><a href="/products/house-blend">選購咖啡豆</a><a href="/blog">咖啡學堂</a><a href="/faq">常見問題</a><a href="/stores">門市</a><a href="/contact">聯絡我們</a></nav></header>
{body}
<footer><p>© 2025 {BRAND}｜台北市大安區晨光路 88 號｜營業時間 08:00–20:00</p>
<p>{social} <a href="/careers" style="color:#f6c48a">加入我們</a>　<a href="/subscribe" style="color:#f6c48a">訂閱電子報</a>　<a href="/events" style="color:#f6c48a">杯測活動</a></p></footer>
</body></html>"""


def org_jsonld() -> str:
    data = {
        "@context": "https://schema.org", "@type": "CafeOrCoffeeShop", "name": BRAND,
        "url": f"http://{HOST}/", "telephone": "+886-2-2700-0000",
        "address": {"@type": "PostalAddress", "streetAddress": "晨光路 88 號", "addressLocality": "台北市大安區", "addressCountry": "TW"},
        "openingHours": "Mo-Su 08:00-20:00",
    }
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'


def page_home() -> str:
    v = VERSION
    cards = "".join(
        f'<div class="card"><img src="/static/img/{slug}.svg"{" alt=" + chr(34) + name + chr(34) if v >= 2 else ""}>'
        f'<h3>{name}</h3><p>{desc}</p><p class="price">NT$ {price}</p><a href="/products/{slug}">查看商品</a></div>'
        for slug, name, price, desc, _ in PRODUCTS
    )
    # v1 首頁有兩個 H1、v2 起修正；v1 有一條壞掉的活動連結
    h1 = '<h1>每一天，從一杯好咖啡開始</h1>' + ('<h1>新鮮烘焙，48 小時內出貨</h1>' if v == 1 else "")
    promo = '<p><a class="btn" href="/promo/2025-autumn">秋季限定活動 →</a></p>' if v == 1 else ""
    generic = '<p>會員優惠詳情請<a href="/faq">點此</a>。</p>' if v == 1 else ""
    broken_script = "" if v >= 2 else "<script>window.addEventListener('load',function(){trackHero.init();});</script>"
    # v3 新的追蹤碼又引入一個執行期錯誤（新增問題）
    new_error = "<script>window.addEventListener('load',function(){analyticsQueue.push({page:'home'});});</script>" if v >= 3 else ""
    body = f"""<section class="hero">{h1}<p>{BRAND}自 2016 年起在台北大安區烘焙精品咖啡，嚴選單一產區生豆，每週小批次烘焙，下單後 48 小時內出貨。</p>
<a class="btn" href="/products/house-blend">選購招牌綜合豆</a>{promo}</section>
<main><h2>本週推薦</h2><div class="grid">{cards}</div>
<h2>為什麼選擇晨光</h2><p>我們與衣索比亞、哥倫比亞與台灣阿里山的小農直接合作，每一批生豆都經過杯測評分 84 分以上才進烘焙機。門市提供手沖、義式與冷萃三種萃取方式，也開設週末杯測與手沖課程。</p>
<p>訂購滿 NT$ 1,000 免運，宅配與超商取貨皆可；企業送禮可客製禮盒與卡片。<a href="/shop">前往線上選購</a></p>{generic}</main>{broken_script}{new_error}"""
    return layout(
        f"{BRAND}｜台北精品咖啡豆、手沖與禮盒",
        body,
        description="晨光咖啡烘焙所：台北大安區精品咖啡烘焙，提供單品咖啡豆、招牌綜合豆與濾掛禮盒，48 小時內出貨。",
        extra_head=org_jsonld() if v >= 2 else "",
    )


def page_about() -> str:
    v = VERSION
    second_h1 = "<h1>我們的故事</h1>" if v == 1 else "<h2>我們的故事</h2>"
    body = f"""<main><h1>關於{BRAND}</h1>{second_h1}
<p>{BRAND}由兩位前科技業工程師於 2016 年創立。我們相信好咖啡不需要複雜，只要新鮮的豆子、正確的烘焙與用心的沖煮。</p>
<p>烘焙廠位於新北市五股，使用 Giesen W6A 烘豆機，每週一、四烘焙，烘焙後靜置 48 小時再出貨。2023 年獲台灣咖啡大師賽烘焙組第三名。</p>
<img src="/static/img/roastery.svg" style="max-width:520px;border-radius:16px"></main>"""
    title = (f"關於我們 - {BRAND} - 台北精品咖啡烘焙 - 單品咖啡豆 - 手沖咖啡 - 咖啡禮盒 - 企業送禮 - 咖啡課程"
             if v == 1 else f"關於我們｜{BRAND}")
    return layout(title, body, description=None if v == 1 else "晨光咖啡烘焙所的品牌故事、烘焙理念與烘焙廠介紹。", path="/about")


def page_menu() -> str:
    rows = "".join(
        f"<tr><td>{n}</td><td>{h}</td><td>NT$ {p}</td><td>NT$ {p + 20}</td><td>{d}</td></tr>"
        for n, h, p, d in [
            ("美式咖啡", "熱／冰", 90, "招牌綜合豆，雙份濃縮"), ("拿鐵", "熱／冰", 130, "可換燕麥奶 +20"),
            ("手沖單品", "熱", 180, "依當週單品豆"), ("冷萃咖啡", "冰", 150, "12 小時低溫萃取"),
            ("焦糖瑪奇朵", "熱／冰", 150, "自製焦糖醬"), ("司康", "—", 85, "每日現烤，原味／伯爵"),
        ]
    )
    old_menu = '<p><a href="/menu/2024">去年的菜單</a></p>' if VERSION < 3 else ""
    body = f"""<main><h1>門市菜單</h1><p>以下價格為門市內用與外帶價格，大杯加 NT$ 20。</p>
<table class="menu-table"><tr><th>品項</th><th>溫度</th><th>中杯</th><th>大杯</th><th>說明</th></tr>{rows}</table>
<p class="notice">冷萃咖啡每日限量 40 杯，售完為止。</p>{old_menu}</main>"""
    return layout(f"門市菜單｜{BRAND}", body, description=None, path="/menu")


def product_jsonld(slug: str, name: str, price: int, broken: bool) -> str:
    data = {
        "@context": "https://schema.org", "@type": "Product", "name": name,
        "image": f"http://{HOST}/static/img/{slug}.svg", "brand": {"@type": "Brand", "name": BRAND},
        "offers": {"@type": "Offer", "priceCurrency": "TWD", "price": str(price), "availability": "https://schema.org/InStock"},
    }
    text = json.dumps(data, ensure_ascii=False)
    if broken:
        # 少一個右大括號：結構化資料語法錯誤（v1、v2；v3 修正）
        text = text[:-1]
    return f'<script type="application/ld+json">{text}</script>'


def page_product(slug: str) -> str:
    v = VERSION
    _, name, price, desc, _color = next(p for p in PRODUCTS if p[0] == slug)
    body = f"""<main><p><a href="/">首頁</a> › <a href="/menu">商品</a> › {name}</p>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:32px"><img src="/static/img/{slug}.svg"{' alt="' + name + '"' if v >= 2 else ''} style="width:100%;border-radius:16px">
<div><h1>{name}</h1><p class="price">NT$ {price}／半磅</p><p>{desc}</p>
<p><span class="tag">產地直送</span><span class="tag">每週烘焙</span></p>
<p>建議沖煮：粉水比 1:15、水溫 92°C、總時間 2 分 30 秒。開封後請於 30 天內飲用完畢。</p>
<a class="btn" href="/contact">加入購物車</a></div></div></main>"""
    broken = slug == "house-blend" and v < 3
    return layout(f"{name}｜{BRAND}", body, description=f"{name}：{desc}" if (v >= 2 or slug != "drip-bag-gift-box") else None,
                  extra_head=product_jsonld(slug, name, price, broken), path=f"/products/{slug}")


def page_blog() -> str:
    posts = list(POSTS) + ([NEW_POST] if VERSION >= 3 else [])
    items = "".join(f'<div class="card"><h3><a href="/blog/{s}">{t}</a></h3><p>{d}</p></div>' for s, t, d in posts)
    return layout(f"咖啡學堂｜{BRAND}", f"<main><h1>咖啡學堂</h1><div class='grid'>{items}</div></main>",
                  description="手沖、拉花與冷萃教學文章，從器材挑選到沖煮參數一次看懂。", path="/blog")


def page_post(slug: str) -> str:
    v = VERSION
    if slug == "hand-drip-guide":
        title = POSTS[0][1]
        content = """<p>手沖咖啡只需要四樣器材：濾杯、濾紙、細口壺與電子秤。新手建議從 V60 或 Kalita 波浪濾杯開始。</p>
<h2>粉水比例</h2><p>建議以 1:15 為起點，例如 15 公克咖啡粉搭配 225 毫升熱水。想要更濃郁可以調整到 1:13。</p>
<h2>水溫與研磨</h2><p>淺焙豆使用 92–94°C，深焙豆使用 86–88°C。研磨度約為砂糖顆粒大小。</p>
<h2>步驟</h2><ol><li>濾紙以熱水沖洗並預熱器材。</li><li>注入兩倍粉量的水悶蒸 30 秒。</li><li>分三段注水，總時間控制在 2 分 30 秒。</li></ol>
<p>根據我們 2024 年對 312 位門市顧客的調查，76% 的新手在掌握「悶蒸」這一步後，覺得咖啡明顯變得更甜。</p>"""
        if v < 3:
            content += '<p>完整的沖煮紀錄表可參考<a href="https://zh.wikipedia.org/wiki/%E6%99%A8%E5%85%89%E5%92%96%E5%95%A1%E7%83%98%E7%84%99%E6%89%80%E6%B2%96%E7%85%AE%E7%AD%86%E8%A8%98">我們的沖煮筆記</a>。</p>'
    elif slug == "latte-art-basics":
        title = POSTS[1][1]
        content = """<p>拉花的關鍵在於奶泡的質地：細緻、有光澤、沒有大氣泡。打發時讓蒸氣管口剛好在奶面下 1 公分。</p>
<h2>練習順序</h2><p>先練圓形（愛心的基礎），再練愛心、層次愛心、鬱金香與葉子。每天練習 10 杯，大約兩週可以穩定拉出愛心。</p>"""
    else:
        title = NEW_POST[1]
        # v3 新文章：圖片沒有 alt（新增問題）
        content = """<img src="/static/img/cold-brew.svg" style="max-width:520px;border-radius:16px">
<p>冷萃咖啡以冷水長時間浸泡，酸度低、口感圓潤。準備 100 公克中粗研磨的咖啡粉與 1 公升冷水，冷藏浸泡 12 小時後過濾即可。</p>
<p>冷萃原液可冷藏保存 5 天，飲用時以 1:1 加水或牛奶稀釋。</p>"""
    body = f"<main><article><h1>{title}</h1><p><span class='tag'>咖啡學堂</span>作者：晨光烘焙師 林小晨</p>{content}</article></main>"
    article_ld = ""
    if v >= 2:
        article_ld = '<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "Article", "headline": title,
            "author": {"@type": "Person", "name": "林小晨"}, "publisher": {"@type": "Organization", "name": BRAND},
        }, ensure_ascii=False) + "</script>"
    return layout(f"{title}｜{BRAND}", body, description=title if v >= 2 or slug != "latte-art-basics" else None,
                  extra_head=article_ld, path=f"/blog/{slug}")


FAQS = [
    ("訂單多久會出貨？", "我們每週一、四烘焙，烘焙後靜置 48 小時再出貨，一般在下單後 3 個工作天內送達。"),
    ("運費怎麼計算？", "訂購滿 NT$ 1,000 免運，未滿酌收 NT$ 80；超商取貨 NT$ 60。"),
    ("咖啡豆可以幫忙研磨嗎？", "可以，下單時備註手沖、義式或法式濾壓壺，我們會依器材研磨。"),
    ("可以開立公司發票嗎？", "可以，結帳時填寫統一編號與抬頭即可。"),
]


def page_faq() -> str:
    v = VERSION
    items = "".join(f"<dt>{q}</dt><dd>{a}</dd>" for q, a in FAQS)
    faq_ld = ""
    if v >= 2:
        faq_ld = '<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQS],
        }, ensure_ascii=False) + "</script>"
    return layout(f"常見問題｜{BRAND}", f"<main><h1>常見問題</h1><dl class='faq'>{items}</dl></main>",
                  description="訂單出貨、運費、研磨與發票等常見問題。", extra_head=faq_ld, path="/faq")


def page_stores() -> str:
    body = """<main><h1>門市資訊</h1><div class="grid">
<div class="card"><h3>大安旗艦店</h3><p>台北市大安區晨光路 88 號</p><p>每日 08:00–20:00</p></div>
<div class="card"><h3>松山烘焙工作室</h3><p>台北市松山區民生東路五段 168 號</p><p>週二至週日 10:00–18:00</p></div>
<div class="card"><h3>台中勤美店</h3><p>台中市西區公益路 120 號</p><p>每日 09:00–21:00</p></div></div></main>"""
    return layout(f"門市資訊｜{BRAND}", body, description="晨光咖啡烘焙所三間門市的地址與營業時間。", path="/stores")


def page_contact() -> str:
    v = VERSION
    # 表單欄位只有 placeholder、沒有 label；也沒有 CSRF token（每版都有，屬持續問題）
    body = f"""<main><h1>聯絡我們</h1>
<p>客服電話：(02) 2700-0000（週一至週五 09:00–18:00）　客服信箱：service@morninglight-coffee.example</p>
<form method="post" action="/contact">
<div class="row"><input name="name" placeholder="您的姓名"></div>
<div class="row"><input name="email" placeholder="Email"></div>
<div class="row"><select name="topic"><option>訂單問題</option><option>企業送禮</option><option>其他</option></select></div>
<div class="row"><textarea name="message" rows="5" placeholder="想對我們說的話"></textarea></div>
<button class="btn" type="submit">送出</button></form>
{"<p class='notice'>企業送禮請直接來電，可於三個工作天內提供報價。</p>" if v >= 2 else ""}</main>"""
    return layout(f"聯絡我們｜{BRAND}", body, description="客服電話、Email 與線上聯絡表單。", path="/contact")


def page_careers() -> str:
    body = """<main><h1>加入我們</h1><p>晨光正在招募門市咖啡師與烘焙助理，歡迎熱愛咖啡的你加入。</p>
<h2>門市咖啡師（大安旗艦店）</h2><p>月薪 NT$ 34,000 起，具一年以上義式吧台經驗佳。</p>
<p>履歷請寄店長 王大明：daming.wang.cafe@gmail.com，或直接來電 0912-345-678（下午兩點後）。</p></main>"""
    return layout(f"加入我們｜{BRAND}", body, description="晨光咖啡烘焙所職缺：門市咖啡師與烘焙助理。", path="/careers")


def page_subscribe() -> str:
    body = """<main><h1>訂閱電子報</h1><p>每月一封，第一時間收到新豆上架與課程資訊。</p>
<form method="post" action="/subscribe"><div class="row"><input type="email" name="email" placeholder="輸入 Email"></div>
<button class="btn" type="submit">訂閱</button></form></main>"""
    return layout(f"訂閱電子報｜{BRAND}", body, description="訂閱晨光咖啡電子報，收到新豆與課程消息。", path="/subscribe")


def page_events() -> str:
    body = """<main><h1>週末杯測活動</h1><p>每週六下午兩點於松山烘焙工作室舉辦杯測，每場 12 人，費用 NT$ 350（含當日豆 100 公克）。</p>
<p>報名請於活動前一天中午前完成，額滿為止。</p></main>"""
    return layout(f"杯測活動｜{BRAND}", body, description="晨光咖啡每週六杯測活動與報名方式。", path="/events")


def robots() -> str:
    return "User-agent: *\nDisallow: /admin/\nDisallow: /backup/\nSitemap: http://%s/sitemap.xml\n" % HOST


def sitemap() -> str:
    paths = ["/", "/about", "/menu", "/blog", "/faq", "/stores", "/contact", "/careers", "/subscribe", "/events"]
    paths += [f"/products/{p[0]}" for p in PRODUCTS] + [f"/blog/{p[0]}" for p in POSTS]
    if VERSION >= 3:
        paths.append(f"/blog/{NEW_POST[0]}")
    urls = "".join(f"<url><loc>http://{HOST}{p}</loc></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


LLMS = f"""# {BRAND}

> 台北大安區的精品咖啡烘焙所，提供單品咖啡豆、綜合豆、濾掛禮盒與咖啡課程。

## 主要頁面
- [商品：招牌綜合豆](http://{HOST}/products/house-blend)
- [常見問題](http://{HOST}/faq)
- [門市資訊](http://{HOST}/stores)
- [聯絡我們](http://{HOST}/contact)
"""

FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#2f1d14"/>'
           '<circle cx="32" cy="34" r="18" fill="#f6c48a"/><path d="M26 22c6 6 0 12 6 20" stroke="#2f1d14" stroke-width="4" fill="none"/></svg>')


class Handler(BaseHTTPRequestHandler):
    server_version = "Apache/2.4.29"
    sys_version = "(Ubuntu)"

    def log_message(self, fmt, *args):  # 安靜一點
        pass

    def _send(self, status: int, body: str | bytes, ctype: str = "text/html; charset=utf-8", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if VERSION < 3:
            self.send_header("X-Powered-By", "PHP/7.2.34")
        if VERSION >= 2:
            self.send_header("X-Content-Type-Options", "nosniff")
        if VERSION >= 3:
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if ctype.startswith("text/html"):
            cookie = "PHPSESSID=8f3c2a1b9d7e6f5a4c3b2a1d; path=/"
            if VERSION >= 3:
                cookie += "; HttpOnly"
            self.send_header("Set-Cookie", cookie)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0]
        host = (self.headers.get("Host") or HOST).split(":")[0].lower()
        bare = HOST.removeprefix("www.")
        if host == bare and VERSION >= 2:
            return self._send(301, "", extra={"Location": f"http://{HOST}{self.path}"})
        if host == f"shop.{bare}":
            return self._send(200, layout(f"線上商店｜{BRAND}", "<main><h1>晨光線上商店</h1><p>咖啡豆、濾掛與禮盒線上訂購。</p></main>",
                                          description="晨光咖啡線上商店：咖啡豆、濾掛與禮盒。", canonical=False))
        if path == "/shop":
            return self._send(301, "", extra={"Location": "/products/house-blend"})
        if path == "/static/img/line.svg":
            return self._send(200, svg_image("#06c755", "LINE"), "image/svg+xml")
        if path != "/" and path.endswith("/") and not path.startswith("/files"):
            path = path.rstrip("/")
        routes = {
            "/": page_home, "/about": page_about, "/menu": page_menu, "/blog": page_blog, "/faq": page_faq,
            "/stores": page_stores, "/contact": page_contact, "/careers": page_careers,
            "/subscribe": page_subscribe, "/events": page_events,
        }
        if path in routes:
            if path == "/events":
                time.sleep(3.6)  # 慢頁面
            return self._send(200, routes[path]())
        if path.startswith("/products/") and path[10:] in {p[0] for p in PRODUCTS}:
            return self._send(200, page_product(path[10:]))
        posts = {p[0] for p in POSTS} | ({NEW_POST[0]} if VERSION >= 3 else set())
        if path.startswith("/blog/") and path[6:] in posts:
            return self._send(200, page_post(path[6:]))
        if path == "/robots.txt":
            return self._send(200, robots(), "text/plain; charset=utf-8")
        if path == "/sitemap.xml":
            return self._send(200, sitemap(), "application/xml")
        if path == "/llms.txt" and VERSION >= 3:
            return self._send(200, LLMS, "text/plain; charset=utf-8")
        if path in ("/favicon.svg", "/favicon.ico"):
            return self._send(200, FAVICON, "image/svg+xml")
        if path.startswith("/static/img/") and path.endswith(".svg"):
            slug = path[12:-4]
            color = next((p[4] for p in PRODUCTS if p[0] == slug), "#b8733b")
            label = next((p[1] for p in PRODUCTS if p[0] == slug), {"roastery": "烘焙廠", "cold-brew": "冷萃咖啡", "og-cover": BRAND}.get(slug, BRAND))
            return self._send(200, svg_image(color, label), "image/svg+xml")
        if path == "/static/js/jquery-1.8.2.min.js":
            return self._send(200, "/*! jQuery v1.8.2 jquery.com | jquery.org/license */\nwindow.jQuery=window.$=function(){return{}};", "application/javascript")
        if path == "/static/js/jquery-3.7.1.min.js":
            return self._send(200, "/*! jQuery v3.7.1 | (c) OpenJS Foundation and other contributors | jquery.org/license */\nwindow.jQuery=window.$=function(){return{}};", "application/javascript")
        if path == "/static/js/config.js":
            # 前端設定檔裡寫死的金鑰（虛構值）：v1、v2 外洩，v3 移除
            if VERSION < 3:
                return self._send(200, 'window.APP_CONFIG = { mapEmbed: true, api_key: "mlc_demo_9f2c41ab77e0d3" };', "application/javascript")
            return self._send(200, "window.APP_CONFIG = { mapEmbed: true };", "application/javascript")
        if path == "/.env" and VERSION == 1:
            # 虛構的環境變數檔外洩（v1 才有）
            return self._send(200, "APP_ENV=production\nDB_HOST=10.0.0.12\nDB_PASSWORD=demo-only-not-real\nMAIL_PASSWORD=demo-only-not-real\n", "text/plain")
        if path.startswith("/files"):
            listing = "<html><head><title>Index of /files</title></head><body><h1>Index of /files</h1><ul><li><a href='menu-2024.pdf'>menu-2024.pdf</a></li><li><a href='price-list.xlsx'>price-list.xlsx</a></li></ul></body></html>"
            return self._send(200, listing)
        return self._send(404, layout(f"找不到頁面｜{BRAND}", "<main><h1>找不到這個頁面</h1><p>頁面可能已下架。<a href='/'>回首頁</a></p></main>", description=None))

    def do_POST(self):
        self._send(303, "", extra={"Location": "/contact"})


def main():
    global VERSION
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    VERSION = args.version
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
