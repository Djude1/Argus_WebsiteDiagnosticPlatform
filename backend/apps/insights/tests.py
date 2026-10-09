from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.insights.analyzers import analyze_email, score_url_risk


class InsightsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("apps.insights.analyzers.socket.getaddrinfo")
    @patch("apps.insights.analyzers.requests.get")
    def test_speed_test_returns_lightweight_metrics(self, mock_get, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (None, None, None, "", ("93.184.216.34", 0)),
        ]
        response = Mock()
        response.status_code = 200
        response.url = "https://example.com/"
        response.headers = {
            "content-type": "text/html",
            "content-encoding": "br",
            "cache-control": "public, max-age=3600",
        }
        response.encoding = "utf-8"
        response.content = (
            b"<html><head><title>Example</title>"
            b"<script src='/app.js' defer></script></head>"
            b"<body><img src='/hero.png' loading='lazy'></body></html>"
        )
        mock_get.return_value = response

        res = self.client.post(
            "/api/insights/speed-test/",
            {"url": "https://example.com", "authorization_confirmed": True},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status_code"], 200)
        self.assertGreaterEqual(res.data["score"], 80)
        self.assertEqual(res.data["metrics"]["html_title"], "Example")

    def test_speed_test_requires_authorization_confirmation(self):
        res = self.client.post(
            "/api/insights/speed-test/",
            {"url": "https://example.com", "authorization_confirmed": False},
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("authorization_confirmed", res.data)

    @patch("apps.insights.analyzers.socket.getaddrinfo")
    @patch("apps.insights.analyzers.requests.get")
    def test_speed_test_blocks_redirect_to_internal_host(self, mock_get, mock_getaddrinfo):
        """公開 URL 若 302 轉址到內網（如雲端 metadata），必須被 SSRF 防護擋下。"""

        def fake_getaddrinfo(host, *args, **kwargs):
            if host == "evil.example":  # redirect 目標解析到 link-local 內網
                return [(None, None, None, "", ("169.254.169.254", 0))]
            return [(None, None, None, "", ("93.184.216.34", 0))]  # 原始公開主機

        mock_getaddrinfo.side_effect = fake_getaddrinfo
        redirect = Mock()
        redirect.status_code = 302
        redirect.headers = {"Location": "http://evil.example/latest/meta-data/"}
        mock_get.return_value = redirect

        res = self.client.post(
            "/api/insights/speed-test/",
            {"url": "https://example.com", "authorization_confirmed": True},
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("url", res.data)
        # 只應發出第一個（原始）請求，不應真的去抓內網
        self.assertEqual(mock_get.call_count, 1)

    def test_phishing_url_flags_suspicious_features(self):
        res = self.client.post(
            "/api/insights/phishing-url/",
            {"url": "http://paypal-secure-login.example.net/verify/account?token=abc"},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.data["risk_score"], 45)
        self.assertIn(res.data["risk_level"], {"medium", "high"})
        self.assertTrue(res.data["features"])

    def test_phishing_email_flags_auth_and_link_risk(self):
        raw_email = """From: PayPal <notice@paypal.example>
Reply-To: support@evil.example
Return-Path: <bounce@evil.example>
Authentication-Results: mx.example; spf=fail smtp.mailfrom=evil.example; dmarc=fail
Subject: Urgent verify now

請立即驗證帳號：https://paypal-secure-login.example.net/verify/account
"""
        res = self.client.post(
            "/api/insights/phishing-email/",
            {"raw_email": raw_email},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.data["risk_score"], 45)
        titles = {item["title"] for item in res.data["features"]}
        self.assertIn("郵件驗證失敗", titles)


class InsightsAnalyzerTests(TestCase):
    def test_url_classifier_keeps_low_risk_plain_https_url_low(self):
        report = score_url_risk("https://example.com/articles/security-guide")

        self.assertLess(report["risk_score"], 45)
        self.assertIn(report["risk_level"], {"minimal", "low"})

    def test_email_classifier_handles_plain_email_without_links(self):
        report = analyze_email(
            "From: hello@example.com\nSubject: Hello\n\n這是一封一般通知信。"
        )

        self.assertLess(report["risk_score"], 45)
        self.assertEqual(report["url_count"], 0)


def _mock_html_response():
    response = Mock()
    response.status_code = 200
    response.url = "https://example.com/"
    response.headers = {"content-type": "text/html"}
    response.encoding = "utf-8"
    response.content = b"<html><head><title>Example</title></head><body></body></html>"
    return response


PSI_REPORT = {"source": "pagespeed_insights", "lab": {"scores": {"performance": 88}}, "field": {}}


PUBLIC_DNS = [(None, None, None, "", ("93.184.216.34", 0))]


@patch("apps.insights.analyzers.socket.getaddrinfo", return_value=PUBLIC_DNS)
@patch("apps.insights.analyzers.requests.get", return_value=_mock_html_response())
class SpeedTestPageSpeedTests(TestCase):
    """快速檢查頁測速接 Google PageSpeed Insights：背景量測＋輪詢（pagespeed_jobs）。"""

    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def _speed_test(self):
        return self.client.post(
            "/api/insights/speed-test/",
            {"url": "https://example.com", "authorization_confirmed": True},
            format="json",
        )

    @override_settings(ARGUS_PAGESPEED_API_KEY="", ARGUS_PAGESPEED_ENABLED=False)
    def test_without_key_reports_unavailable(self, _get, _dns):
        res = self._speed_test()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["pagespeed"], {"status": "unavailable"})
        self.assertIn("PageSpeed Insights / Lighthouse", res.json()["core_web_vitals_note"])

    @override_settings(ARGUS_PAGESPEED_API_KEY="test-key", ARGUS_PAGESPEED_ENABLED=True)
    def test_queues_job_then_poll_returns_result_and_url_is_cached(self, _get, _dns):
        with patch("apps.insights.tasks.run_public_pagespeed.delay") as delay:
            res = self._speed_test()
        self.assertEqual(res.status_code, 200)
        psi = res.json()["pagespeed"]
        self.assertEqual(psi["status"], "pending")
        delay.assert_called_once_with(psi["job"], "https://example.com/")
        self.assertIn("Google PageSpeed Insights", res.json()["core_web_vitals_note"])

        poll = self.client.get(f"/api/insights/speed-test/pagespeed/{psi['job']}/")
        self.assertEqual(poll.json(), {"status": "pending"})

        from apps.insights import pagespeed_jobs

        with patch("apps.scans.pagespeed.fetch", return_value=PSI_REPORT):
            pagespeed_jobs.run(psi["job"], "https://example.com/")
        poll = self.client.get(f"/api/insights/speed-test/pagespeed/{psi['job']}/")
        self.assertEqual(poll.json(), {"status": "done", "report": PSI_REPORT})

        # 同網址 10 分鐘內再測：直接回快取，不再呼叫 Google
        with patch("apps.insights.tasks.run_public_pagespeed.delay") as delay:
            again = self._speed_test()
        delay.assert_not_called()
        self.assertEqual(again.json()["pagespeed"]["status"], "done")
        self.assertTrue(again.json()["pagespeed"]["cached"])

    @override_settings(ARGUS_PAGESPEED_API_KEY="test-key", ARGUS_PAGESPEED_ENABLED=True)
    def test_same_pending_url_reuses_one_job_and_global_window_limits_dispatches(self, _get, _dns):
        from apps.insights import pagespeed_jobs

        with patch("apps.insights.tasks.run_public_pagespeed.delay") as delay:
            first = pagespeed_jobs.start("https://example.com/")
            same_url = pagespeed_jobs.start("https://example.com/")
            other_url = pagespeed_jobs.start("https://example.org/")

        self.assertEqual(first["status"], "pending")
        self.assertEqual(same_url, first)
        self.assertEqual(other_url["status"], "failed")
        delay.assert_called_once_with(first["job"], "https://example.com/")

    @override_settings(ARGUS_PAGESPEED_API_KEY="test-key", ARGUS_PAGESPEED_ENABLED=True)
    def test_worker_revalidates_public_url_before_calling_pagespeed(self, _get, _dns):
        from apps.insights import pagespeed_jobs
        from apps.insights.analyzers import PublicHostError

        with (
            patch(
                "apps.insights.analyzers.assert_public_url",
                side_effect=PublicHostError("免費公開分析不允許 localhost 或內網位址。"),
            ) as validate,
            patch("apps.scans.pagespeed.fetch") as fetch,
        ):
            pagespeed_jobs.run("c" * 24, "http://localhost/")

        validate.assert_called_once_with("http://localhost/")
        fetch.assert_not_called()
        self.assertEqual(
            pagespeed_jobs.get("c" * 24),
            {"status": "failed", "reason": "免費公開分析不允許 localhost 或內網位址。"},
        )

    @override_settings(ARGUS_PAGESPEED_API_KEY="test-key", ARGUS_PAGESPEED_ENABLED=True)
    def test_failure_reason_is_reported_and_not_cached(self, _get, _dns):
        from apps.insights import pagespeed_jobs
        from apps.scans.pagespeed import PageSpeedError

        quota = PageSpeedError("PageSpeed Insights 配額用完")
        with patch("apps.scans.pagespeed.fetch", side_effect=quota):
            pagespeed_jobs.run("a" * 24, "https://example.com/")
        poll = self.client.get(f"/api/insights/speed-test/pagespeed/{'a' * 24}/")
        self.assertEqual(poll.json(), {"status": "failed", "reason": "PageSpeed Insights 配額用完"})
        self.assertIsNone(cache.get(pagespeed_jobs._url_key("https://example.com/")))

    def test_poll_unknown_or_malformed_job_is_404(self, _get, _dns):
        base = "/api/insights/speed-test/pagespeed/"
        self.assertEqual(self.client.get(f"{base}{'b' * 24}/").status_code, 404)
        self.assertEqual(self.client.get(f"{base}short/").status_code, 404)
