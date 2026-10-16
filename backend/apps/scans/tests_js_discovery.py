"""JS bundle 靜態端點發現與靜態資源過濾（crawler，2026-10-16）。

繞過 Cloudflare 的確定性發現：爬蟲載入頁面時瀏覽器已抓下同源 JS，直接讀內容抽 API 路徑。
端點與 IP 皆為虛構測試值，不是任何真實站台的資料。
"""

from django.test import SimpleTestCase

from apps.scans.crawler import extract_api_paths_from_js, is_static_asset_path


class StaticAssetFilterTests(SimpleTestCase):
    def test_static_assets_detected(self):
        for path in (
            "/_next/static/css/a.css", "/_next/static/chunks/x.js", "/assets/app.js",
            "/static/logo.png", "/fonts/x.woff2", "/img/hero.webp", "/bundle.js.map",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_static_asset_path(path))

    def test_api_paths_not_treated_as_static(self):
        for path in ("/api_proxy/v3/api-docs", "/api/v1/users", "/backend/report", "/graphql"):
            with self.subTest(path=path):
                self.assertFalse(is_static_asset_path(path))


class ExtractApiPathsFromJsTests(SimpleTestCase):
    def test_rewrite_base_and_api_paths_extracted(self):
        # 模擬打包產物：rewrite base 是裸字串，拼接路徑在別處；混入頁面與靜態路徑
        js = (
            'self.__BM={"/about":["static/chunks/about.js"],"/member":["m.js"]};'
            'var base="/gateway";fetch(base+"/news");axios.get("/api/v1/users");'
            'const d="/backend/report/download";load("/_next/static/css/a.css");'
            'link("/about");img("/logo.svg");'
        )
        paths = extract_api_paths_from_js(js)
        self.assertIn("/gateway", paths)
        self.assertIn("/api/v1/users", paths)
        self.assertIn("/backend/report/download", paths)
        # 頁面路徑與靜態資源不列入
        self.assertNotIn("/about", paths)
        self.assertNotIn("/logo.svg", paths)
        self.assertFalse(any(p.startswith("/_next/") for p in paths))

    def test_nextjs_rewrite_param_form_extracted(self):
        # 真實站的形式是 Next.js rewrite 規則 source:"/<base>/:path*"，不是裸字串；
        # 之前的正則吃不下 :param → 完全抽不到（2026-10-16 實站漏抓的直接原因）
        js = '{"beforeFiles":[{"source":"/gateway/:path*","destination":"https://x/backend/:path*"}]}'
        paths = extract_api_paths_from_js(js)
        self.assertIn("/gateway", paths)
        # 動態參數不留在抽出的路徑裡
        self.assertFalse(any(":" in p or "*" in p for p in paths))

    def test_wildcard_and_fully_dynamic_handled(self):
        # /api/* → /api；整段動態 /:locale/x 的第一段就是參數 → 不產生路徑
        self.assertIn("/api", extract_api_paths_from_js('rewrite("/api/*")'))
        self.assertEqual(extract_api_paths_from_js('"/:locale/home"'), set())

    def test_empty_and_garbage_safe(self):
        self.assertEqual(extract_api_paths_from_js(""), set())
        self.assertEqual(extract_api_paths_from_js("const x=1;var y='hello world';"), set())
