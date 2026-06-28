"""exposure_scanner 純函式單元測試。以靶機 CEKB 真實內容為輸入。"""
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

    def test_sitemap_parse_handles_garbage(self):
        self.assertEqual(exp.parse_sitemap_urls("not xml"), [])


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
