"""網站特徵（fingerprint）準確率資料集（ADR-0004 階段 1、roadmap P1 Smart Scan）。

每個案例是一個小網站在爬取階段會留下的資料（頁面 HTML、回應標頭、狀態碼、被動攔截的
XHR／fetch 端點），`expected` 是人工讀過內容後標註的特徵。標註依據：

- cms／edge／auth_scheme：有特有路徑、標頭或 401 驗證要求才標；沒有就是 None
- frameworks：只標有特有標記的（`/_next/static/`、`ng-version`…），「用了 React」但看不出來的不標
- has_login／has_upload：頁面上有實際顯示的密碼欄位／檔案欄位才標 True；沒看到標 None（不是 False）
- has_api：瀏覽器在爬取時呼叫了 API 路徑的端點，或頁面宣告了 REST API 才標 True

「容易誤判的案例」（tag decoy）：教學文章正文提到 `/wp-content/`、`<template>` 裡的密碼欄位、
只有 Email 的電子報表單、XHR 載入 HTML 片段——這些都不該被當成特徵。

保留集（tag holdout）不要拿來調規則；新增案例先標註、再跑 `manage.py fingerprint_benchmark`，
不要為了讓規則通過而改標註。
"""

from __future__ import annotations

from dataclasses import dataclass, field

DECOY = "decoy"
HOLDOUT = "holdout"


@dataclass(frozen=True)
class FingerprintCase:
    name: str
    pages: tuple[dict, ...]
    expected: dict
    endpoints: tuple[str, ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)


def page(url: str, body: str, headers: dict | None = None, status: int = 200) -> dict:
    html = f"<!doctype html><html><head><title>t</title></head><body>{body}</body></html>"
    if "<head>" in body:
        html = body
    return {
        "url": url, "final_url": url, "status_code": status, "html": html,
        "rendered_dom": html, "headers": headers or {}, "blocked_reason": "",
    }


NONE = {
    "cms": None, "frameworks": (), "edge": None, "has_login": None, "has_api": None,
    "has_upload": None, "auth_scheme": None,
}


def expect(**kwargs) -> dict:
    return {**NONE, **kwargs}


B = "https://example.com"

GOLD_CASES: tuple[FingerprintCase, ...] = (
    FingerprintCase(
        "wordpress-blog",
        (
            page(f"{B}/", """<!doctype html><html><head>
                <meta name="generator" content="WordPress 6.6.2">
                <link rel="https://api.w.org/" href="https://example.com/wp-json/">
                <link rel="stylesheet" href="/wp-content/themes/astra/style.css">
                </head><body><h1>部落格</h1></body></html>""",
                 {"server": "nginx", "x-powered-by": "PHP/8.2"}),
            page(f"{B}/about/", '<img src="/wp-content/uploads/2024/01/a.jpg"><p>關於</p>'),
        ),
        expect(cms="WordPress", frameworks=("PHP",), has_api=True),
    ),
    FingerprintCase(
        "wordpress-woocommerce-login",
        (
            page(f"{B}/", '<script src="/wp-includes/js/jquery/jquery.min.js"></script>'
                          "<h1>商店</h1>"),
            page(f"{B}/my-account/", """<script src="/wp-content/plugins/woocommerce/a.js"></script>
                <form method="post"><input type="text" name="username">
                <input type="password" name="password"><button>登入</button></form>"""),
        ),
        expect(cms="WordPress", has_login=True, has_api=True),
        endpoints=(f"{B}/wp-json/wc/store/v1/cart", f"{B}/?wc-ajax=get_refreshed_fragments"),
    ),
    FingerprintCase(
        "nextjs-marketing",
        (
            page(f"{B}/", """<!doctype html><html><head>
                <link rel="preload" href="/_next/static/css/app.css" as="style"></head><body>
                <div id="__next"><h1>產品</h1></div>
                <script id="__NEXT_DATA__" type="application/json">{"page":"/"}</script>
                </body></html>""", {"x-vercel-id": "hkg1::abc", "server": "Vercel"}),
            page(f"{B}/pricing",
                 '<script src="/_next/static/chunks/main.js"></script><h1>價格</h1>'),
        ),
        expect(frameworks=("Next.js",), edge="Vercel"),
    ),
    FingerprintCase(
        "nextjs-app-api",
        (
            page(f"{B}/", '<script src="/_next/static/chunks/app.js"></script><div>儀表板</div>'),
            page(f"{B}/login", """<script src="/_next/static/chunks/login.js"></script>
                <form><input type="email" name="email"><input type="password" name="pw"></form>"""),
        ),
        expect(frameworks=("Next.js",), has_login=True, has_api=True),
        endpoints=(f"{B}/api/session", f"{B}/api/projects?page=1", f"{B}/api/me"),
    ),
    FingerprintCase(
        "static-brochure",
        (
            page(f"{B}/", "<h1>晨光咖啡</h1><p>每天現烘。</p><a href='/menu.html'>菜單</a>",
                 {"server": "nginx/1.24.0"}),
            page(f"{B}/menu.html", "<h2>菜單</h2><ul><li>拿鐵</li></ul>"),
            page(f"{B}/contact.html", "<p>電話 02-1234-5678</p>"),
        ),
        expect(),
    ),
    FingerprintCase(
        "spa-api-heavy",
        (
            page(f"{B}/", """<div id="root"></div><script src="/assets/index-a1b2.js"></script>""",
                 {"server": "cloudflare", "cf-ray": "8a1b2c3d4e5f-TPE"}),
        ),
        expect(edge="Cloudflare", has_api=True),
        endpoints=(
            f"{B}/api/v1/products", f"{B}/api/v1/categories", f"{B}/graphql",
            f"{B}/api/v1/cart",
        ),
    ),
    FingerprintCase(
        "graphql-only",
        (page(f"{B}/", '<div id="app"></div><script src="/static/js/main.js"></script>'),),
        expect(has_api=True),
        endpoints=(f"{B}/graphql",),
    ),
    FingerprintCase(
        "login-portal",
        (
            page(f"{B}/", "<h1>會員中心</h1><a href='/signin'>登入</a>"),
            page(f"{B}/signin", """<form action="/signin" method="post">
                <label>帳號<input name="account"></label>
                <label>密碼<input type="password" name="password"
                  autocomplete="current-password"></label>
                </form>"""),
            page(f"{B}/forgot", "<form><input type='email' name='email'></form>"),
        ),
        expect(has_login=True),
    ),
    FingerprintCase(
        "cloudflare-protected",
        (
            page(f"{B}/", "<h1>公司簡介</h1>", {"server": "cloudflare", "cf-ray": "8a-TPE"}),
            page(f"{B}/news", "<h2>最新消息</h2>", {"server": "cloudflare", "cf-ray": "8b-TPE"}),
        ),
        expect(edge="Cloudflare"),
    ),
    FingerprintCase(
        "cloudfront-static",
        (page(f"{B}/", "<h1>Docs</h1>", {"x-amz-cf-id": "abc==", "via": "1.1 x.cloudfront.net"}),),
        expect(edge="Amazon CloudFront"),
    ),
    FingerprintCase(
        "drupal-gov",
        (
            page(f"{B}/", """<!doctype html><html><head>
                <meta name="Generator" content="Drupal 10 (https://www.drupal.org)">
                <link rel="stylesheet" href="/sites/default/files/css/css_a.css"></head>
                <body><div data-drupal-selector="edit-search">搜尋</div></body></html>"""),
        ),
        expect(cms="Drupal"),
    ),
    FingerprintCase(
        "joomla-school",
        (
            page(f"{B}/", """<!doctype html><html><head>
                <meta name="generator" content="Joomla! - Open Source Content Management">
                <script src="/media/system/js/core.js"></script></head><body>學校</body></html>"""),
        ),
        expect(cms="Joomla"),
    ),
    FingerprintCase(
        "shopify-store",
        (page(f"{B}/", '<link href="//cdn.shopify.com/s/files/1/theme.css" rel="stylesheet">'
                       "<h1>店</h1>"),),
        expect(cms="Shopify", has_api=True),
        endpoints=(f"{B}/cart.js", f"{B}/products/mug.json"),
    ),
    FingerprintCase(
        "upload-form",
        (
            page(f"{B}/", "<h1>徵才</h1><a href='/apply'>應徵</a>"),
            page(f"{B}/apply", """<form enctype="multipart/form-data" method="post">
                <input name="name"><input type="file" name="resume" accept=".pdf"></form>"""),
        ),
        expect(has_upload=True),
    ),
    FingerprintCase(
        "basic-auth-staging",
        (
            page(f"{B}/", "<h1>公開首頁</h1>"),
            page(f"{B}/staging/", "", {"www-authenticate": 'Basic realm="staging"'}, status=401),
        ),
        expect(auth_scheme="basic"),
    ),
    FingerprintCase(
        "nuxt-site",
        (page(f"{B}/", '<div id="__nuxt"></div><script src="/_nuxt/entry.js"></script>'),),
        expect(frameworks=("Nuxt",)),
    ),
    FingerprintCase(
        "angular-app",
        (page(f"{B}/", '<app-root ng-version="17.3.0"><span>載入中</span></app-root>'),),
        expect(frameworks=("Angular",)),
    ),
    # ── 容易誤判的案例 ──
    FingerprintCase(
        "tutorial-mentions-wp-paths",
        (
            page(f"{B}/blog/wp-migration", """<h1>如何從 WordPress 搬家</h1>
                <p>把 /wp-content/uploads/ 整個資料夾複製過來，再檢查 /wp-includes/ 的版本。</p>
                <pre><code>rsync -a /var/www/wp-content/ backup/</code></pre>"""),
        ),
        expect(),
        tags=(DECOY,),
    ),
    FingerprintCase(
        "template-hidden-password",
        (
            page(f"{B}/", """<h1>首頁</h1><template id="tpl-login">
                <input type="password" name="pw"></template>"""),
        ),
        expect(),
        tags=(DECOY,),
    ),
    FingerprintCase(
        "newsletter-only",
        (page(f"{B}/", "<form><input type='email' name='email' placeholder='訂閱電子報'>"
                       "<button>訂閱</button></form>"),),
        expect(),
        tags=(DECOY,),
    ),
    FingerprintCase(
        "xhr-html-fragments",
        (page(f"{B}/", "<div id='list'></div><script src='/js/app.js'></script>"),),
        expect(),
        endpoints=(f"{B}/partials/list.html", f"{B}/fragments/footer"),
        tags=(DECOY,),
    ),
    FingerprintCase(
        "embedded-shopify-buy-button",
        (
            page(f"{B}/", """<link rel="stylesheet" href="/wp-content/themes/x/style.css">
                <link rel="stylesheet" href="/wp-content/plugins/y/a.css">
                <script src="https://cdn.shopify.com/buy-button/v2.js"></script>"""),
        ),
        expect(cms="WordPress"),
        tags=(DECOY,),
    ),
    FingerprintCase(
        "error-pages-only-signals",
        (
            page(f"{B}/", "<h1>首頁</h1>"),
            page(f"{B}/admin/", '<form><input type="password" name="pw"></form>', status=403),
        ),
        expect(),
        tags=(DECOY,),
    ),
)

# 保留集：寫完規則後才標註，不拿來調整規則
HOLDOUT_CASES: tuple[FingerprintCase, ...] = (
    FingerprintCase(
        "holdout-wp-headless-api",
        (page(f"{B}/", '<link rel="https://api.w.org/" href="/wp-json/"><h1>新聞</h1>'),),
        expect(cms="WordPress", has_api=True),
        endpoints=(f"{B}/wp-json/wp/v2/posts?per_page=10",),
        tags=(HOLDOUT,),
    ),
    FingerprintCase(
        "holdout-fastly-gatsby",
        (
            page(f"{B}/", '<div id="___gatsby"><h1>文件</h1></div>',
                 {"x-served-by": "cache-tpe1234-TPE", "x-fastly-request-id": "abc"}),
        ),
        expect(frameworks=("Gatsby",), edge="Fastly"),
        tags=(HOLDOUT,),
    ),
    FingerprintCase(
        "holdout-member-upload",
        (
            page(f"{B}/login", '<input type="text" name="u"><input type=password name=p>'),
            page(f"{B}/profile", '<input type=file name=avatar accept="image/*">'),
        ),
        expect(has_login=True, has_upload=True, has_api=True),
        endpoints=(f"{B}/api/profile",),
        tags=(HOLDOUT,),
    ),
    FingerprintCase(
        "holdout-express-bearer",
        (
            page(f"{B}/", "<h1>API 文件</h1>", {"x-powered-by": "Express"}),
            page(f"{B}/v1/", "", {"www-authenticate": 'Bearer realm="api"'}, status=401),
        ),
        expect(frameworks=("Express",), auth_scheme="bearer"),
        tags=(HOLDOUT,),
    ),
    FingerprintCase(
        "holdout-plain-static-with-json-config",
        (page(f"{B}/", "<h1>活動</h1><script src='/js/main.js'></script>"),),
        expect(has_api=True),
        endpoints=(f"{B}/data/events.json",),
        tags=(HOLDOUT,),
    ),
)

ALL_CASES = GOLD_CASES + HOLDOUT_CASES
