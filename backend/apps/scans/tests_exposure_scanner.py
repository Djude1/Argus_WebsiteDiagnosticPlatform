"""exposure_scanner 純函式單元測試。以靶機 CEKB 真實內容為輸入。"""
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from apps.scans.security import exposure_scanner as exp

# 靶機 robots.txt 片段（真實）
ROBOTS = """
User-agent: *
Disallow: /admin/
Disallow: /api/debug/users.json
Disallow: /.git/config
Disallow: /.env
Disallow: /assets/staff.csv
Disallow: /backup.sql
Disallow: /actuator/heapdump
Disallow: /
"""

ENV_BODY = (
    "DATABASE_URL=mongodb://cekb_admin:R3dArch1ve2024@10.0.7.13:27017/cekb_prod\n"
    "STRIPE_API_KEY=sk_live_FAKE_51JhMx9KZvP2lXqA8bC3dE4fG\n"
    "ADMIN_PASSWORD=SuperSecret2024!\n"
)

USERS_JSON_BODY = (
    '{"users":[{"name":"林靜雯","email":"a.lin@cekb.local",'
    '"password_plain":"L1nJ1ngwun2024!","national_id":"A123456789",'
    '"phone":"0912-345-678"}]}'
)


class TestRobotsParsing(SimpleTestCase):
    def test_parse_disallow_skips_root_and_comments(self):
        paths = exp.parse_robots_disallow(ROBOTS)
        self.assertIn("/.env", paths)
        self.assertIn("/api/debug/users.json", paths)
        self.assertNotIn("/", paths)


class TestBuildTargets(SimpleTestCase):
    def test_builtin_paths_included_and_same_origin(self):
        targets = exp.build_probe_targets("https://htb.example")
        self.assertIn("https://htb.example/.env", targets)
        self.assertIn("https://htb.example/.git/config", targets)
        # 全部 same-origin
        self.assertTrue(all(t.startswith("https://htb.example/") for t in targets))

    def test_robots_disallow_merged_and_deduped(self):
        disallow = exp.parse_robots_disallow(ROBOTS)
        targets = exp.build_probe_targets("https://htb.example", robots_disallow=disallow)
        self.assertIn("https://htb.example/api/debug/users.json", targets)
        # .env 同時在內建字典與 robots，不應重複
        self.assertEqual(targets.count("https://htb.example/.env"), 1)

    def test_api_docs_probed_under_observed_api_prefixes(self):
        # 實測站台 2026-10-16：規格在代理前綴底下的 v3/api-docs，只探根目錄找不到
        prefixes = exp.api_prefixes(
            ["/api_proxy/news/list", "/api_proxy/member", "/api/v1/users/me", "/_next/data/x.json",
             "/graphql"]
        )
        self.assertEqual(prefixes, ["/api_proxy/", "/api/", "/api/v1/", "/graphql/"])
        targets = exp.build_probe_targets("https://htb.example", api_path_prefixes=prefixes)
        self.assertIn("https://htb.example/api_proxy/v3/api-docs", targets)
        self.assertIn("https://htb.example/api/v1/openapi.json", targets)
        self.assertIn("https://htb.example/v3/api-docs", targets)
        self.assertEqual(
            exp.classify_exposure("https://htb.example/api_proxy/v3/api-docs")["rule_id"],
            "exposure-file-apidoc",
        )

    def test_single_segment_api_base_becomes_prefix(self):
        # JS 裡 rewrite base 常是裸字串 /api_proxy（拼接後的路徑在別處），單段也要當前綴；
        # 一般單段頁面路徑（/about）不當前綴
        self.assertEqual(exp.api_prefixes(["/api_proxy"]), ["/api_proxy/"])
        self.assertEqual(exp.api_prefixes(["/graphql"]), ["/graphql/"])
        self.assertEqual(exp.api_prefixes(["/about", "/member", "/course"]), [])

    def test_api_prefixes_capped(self):
        paths = [f"/svc{i}/x" for i in range(20)]
        self.assertEqual(len(exp.api_prefixes(paths)), exp.MAX_API_PREFIXES)

    def test_capped(self):
        big = [f"/x{i}" for i in range(500)]
        targets = exp.build_probe_targets("https://htb.example", robots_disallow=big)
        self.assertLessEqual(len(targets), exp.MAX_PROBE_TARGETS)


class TestClassify(SimpleTestCase):
    def test_env_is_critical(self):
        info = exp.classify_exposure("https://htb.example/.env")
        self.assertEqual(info["file_type"], "env")
        self.assertEqual(info["severity"], "critical")

    def test_git_config(self):
        self.assertEqual(
            exp.classify_exposure("https://htb.example/.git/config")["file_type"], "git"
        )

    def test_actuator(self):
        self.assertEqual(
            exp.classify_exposure("https://htb.example/actuator/heapdump")["file_type"],
            "actuator",
        )

    def test_normal_page_not_classified(self):
        self.assertIsNone(exp.classify_exposure("https://htb.example/about"))


class TestAnalyzeProbeResults(SimpleTestCase):
    def test_env_with_secrets_is_critical(self):
        results = [{"url": "https://htb.example/.env", "status": 200,
                    "content_type": "text/plain", "body": ENV_BODY}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["severity"], "critical")
        self.assertIn("環境變數檔", f["title"])
        # 連線字串密碼遮罩，不外洩明文
        self.assertNotIn("R3dArch1ve2024", f["evidence"])
        self.assertIn("疑似秘鑰", f["evidence"])

    def test_users_json_pii_bumps_severity(self):
        results = [{"url": "https://htb.example/api/debug/users.json", "status": 200,
                    "content_type": "application/json", "body": USERS_JSON_BODY}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(len(findings), 1)
        self.assertIn(findings[0]["severity"], ("high", "critical"))
        self.assertIn("個資", findings[0]["evidence"])
        self.assertNotIn("a.lin@cekb.local", findings[0]["evidence"])
        self.assertNotIn("0912-345-678", findings[0]["evidence"])
        self.assertNotIn("A123456789", findings[0]["evidence"])

    def test_apidoc_with_internal_ip_bumps_to_high(self):
        # OpenAPI 規格的 servers 寫內網位址（虛構值）→ 內部網路拓樸外洩，中→高
        body = ('{"openapi":"3.0","servers":[{"url":"http://10.1.2.3:8080"}],'
                '"paths":{"/x":{}}}')
        results = [{"url": "https://htb.example/gateway/v3/api-docs", "status": 200,
                    "content_type": "application/json", "body": body}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["severity"], "high")  # 基礎 medium 被內網 IP 提升
        self.assertIn("內部網路位址外洩", f["evidence"])
        self.assertIn("10.1.2.3", f["description"])
        # 報告只取證據前 300 字：內網位址判讀要排在內容片段之前
        ev = f["evidence"]
        self.assertLess(ev.index("內部網路位址外洩"), ev.index("檔案內容片段"))
        self.assertLess(f["evidence"].index("內部網路位址外洩"), 300)
        # 主動探測已實際取得檔案：判定依據不能沿用「範本比對未經重現」
        assessment = f["evidence_json"]["assessment"]
        self.assertIn("未測試文件列出的 API 是否缺乏授權", assessment["missing"])
        self.assertIn("servers", f["remediation"])

    def test_apidoc_with_public_ip_stays_medium(self):
        # 公網 IP 不是內網外洩，維持基礎 medium
        body = '{"openapi":"3.0","servers":[{"url":"https://8.8.8.8"}],"paths":{}}'
        results = [{"url": "https://htb.example/gateway/v3/api-docs", "status": 200,
                    "content_type": "application/json", "body": body}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_securitytxt_contact_email_stays_info(self):
        # security.txt 的聯絡 email 是檔案刻意公開的回報窗口，不因它升到 high（維持基礎 info）
        body = ("Contact: mailto:security@htb.example\n"
                "Encryption: https://htb.example/pgp.asc\nPreferred-Languages: en\n")
        results = [{"url": "https://htb.example/.well-known/security.txt", "status": 200,
                    "content_type": "text/plain", "body": body}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "info")

    def test_securitytxt_with_other_pii_still_bumps(self):
        # 但 security.txt 裡出現手機／身分證等「非 email」個資，仍要升級
        body = ("Contact: mailto:security@htb.example\n"
                "# 測試帳號聯絡 0912-345-678 身分證 A123456789\n")
        results = [{"url": "https://htb.example/.well-known/security.txt", "status": 200,
                    "content_type": "text/plain", "body": body}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(findings[0]["severity"], "high")

    def test_404_ignored(self):
        results = [{"url": "https://htb.example/.env", "status": 404, "body": ""}]
        self.assertEqual(exp.analyze_probe_results(results), [])

    def test_directory_listing_detected(self):
        results = [{"url": "https://htb.example/uploads/", "status": 200,
                    "body": "<html><title>Index of /uploads</title>..."}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "exposure-dir-listing")


SPA_SHELL = (
    "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">"
    "<title>CEKB</title></head><body><div id=\"root\"></div></body></html>"
)


class TestSoft404(SimpleTestCase):
    def test_is_soft_404_matches_baseline(self):
        self.assertTrue(exp._is_soft_404(SPA_SHELL, [exp._norm_body(SPA_SHELL)]))

    def test_is_soft_404_false_for_real_file(self):
        real = "DATABASE_URL=mongodb://u:p@h/db\nJWT_SECRET=abc"
        self.assertFalse(exp._is_soft_404(real, [exp._norm_body(SPA_SHELL)]))

    def test_soft_404_flagged_result_skipped(self):
        results = [{"url": "https://htb.example/.env", "status": 200,
                    "body": "DATABASE_URL=mongodb://u:pw@h/db", "soft_404": True}]
        self.assertEqual(exp.analyze_probe_results(results), [])

    def test_non_html_type_returning_html_skipped(self):
        # /.env 回 SPA HTML（soft-404 fallback，baseline 沒抓到時的內容啟發式保險）
        results = [{"url": "https://htb.example/.env", "status": 200, "body": SPA_SHELL}]
        self.assertEqual(exp.analyze_probe_results(results), [])

    def test_admin_html_still_reported(self):
        # admin 屬 HTML-expected 型態，回 HTML 不應被內容啟發式誤殺（只靠 baseline 濾 soft-404）
        results = [{"url": "https://htb.example/admin/", "status": 200,
                    "body": "<html><body>CEKB 管理後台登入</body></html>"}]
        findings = exp.analyze_probe_results(results)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "exposure-admin-panel")


class TestRobotsDisclosure(SimpleTestCase):
    def test_discloses_when_many_sensitive(self):
        disallow = exp.parse_robots_disallow(ROBOTS)
        findings = exp.analyze_robots_disclosure(disallow)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "exposure-robots-disclosure")

    def test_no_finding_when_few(self):
        self.assertEqual(exp.analyze_robots_disclosure(["/private"]), [])


class TestProbePacing(SimpleTestCase):
    async def test_baselines_and_probe_share_one_rate_limiter(self):
        response = MagicMock(status=404, ok=False, headers={})
        request = MagicMock()
        request.get = AsyncMock(return_value=response)
        context = MagicMock(request=request)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=playwright)
        manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("playwright.async_api.async_playwright", return_value=manager),
            patch(
                "apps.scans.security.exposure_scanner.build_probe_targets",
                return_value=["https://example.com/.env"],
            ),
            patch(
                "apps.scans.security.exposure_scanner.assert_public_http_url",
                side_effect=lambda value: value,
            ),
            patch("apps.scans.security.exposure_scanner.is_cancelled", return_value=False),
            patch("apps.scans.security.exposure_scanner.time.perf_counter", return_value=100.0),
            patch(
                "apps.scans.security.exposure_scanner.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep,
        ):
            await exp.probe_paths(
                "https://example.com/",
                "https://example.com",
                1,
                robots_disallow=[],
            )

        self.assertEqual(request.get.await_count, 3)
        self.assertEqual(sleep.await_count, 2)
