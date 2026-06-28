from unittest.mock import Mock, patch

from django.test import TestCase
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
