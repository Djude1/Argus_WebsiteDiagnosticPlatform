"""網站專案圖示（favicon.py）：候選網址、格式轉換、SSRF 與轉址檢查、更新規則。"""

from __future__ import annotations

import base64
import io
from datetime import timedelta
from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from PIL import Image

from apps.scans import favicon
from apps.scans.models import SiteProject

User = get_user_model()


def _png(size=(128, 128)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, (12, 74, 110, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _ico() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (48, 48), (200, 30, 30, 255)).save(
        buffer, format="ICO", sizes=[(16, 16), (48, 48)]
    )
    return buffer.getvalue()


class IconCandidateTests(SimpleTestCase):
    def test_declared_icons_ranked_and_fallback_kept(self):
        # 最多 MAX_CANDIDATES 個，/favicon.ico 一定留作後備
        html = (
            '<link rel="apple-touch-icon" href="/apple.png">'
            '<link rel="icon" href="/small.ico">'
            '<link rel="icon" type="image/png" sizes="32x32" href="/icon-32.png">'
        )
        self.assertEqual(
            favicon.icon_candidates(html, "https://example.com/about"),
            [
                "https://example.com/icon-32.png",
                "https://example.com/small.ico",
                "https://example.com/favicon.ico",
            ],
        )

    def test_no_declared_icon_uses_favicon_ico(self):
        self.assertEqual(
            favicon.icon_candidates("<p>沒有圖示</p>", "https://example.com/"),
            ["https://example.com/favicon.ico"],
        )

    def test_non_http_href_ignored(self):
        html = (
            '<link rel="icon" href="data:image/png;base64,AAAA">'
            '<link rel="shortcut icon" href="/f.ico">'
        )
        self.assertEqual(
            favicon.icon_candidates(html, "https://example.com/"),
            ["https://example.com/f.ico", "https://example.com/favicon.ico"],
        )


class DataUrlTests(SimpleTestCase):
    def _decoded(self, data_url: str) -> Image.Image:
        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))

    def test_png_downscaled(self):
        image = self._decoded(favicon.to_data_url("image/png", _png()))
        self.assertEqual(image.size, (favicon.ICON_SIZE, favicon.ICON_SIZE))

    def test_ico_uses_largest_frame(self):
        image = self._decoded(favicon.to_data_url("image/x-icon", _ico()))
        self.assertEqual(image.size, (48, 48))

    def test_svg_kept_when_small(self):
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">'
            b'<rect width="8" height="8"/></svg>'
        )
        self.assertTrue(
            favicon.to_data_url("image/svg+xml", svg).startswith("data:image/svg+xml;base64,")
        )
        self.assertEqual(favicon.to_data_url("image/svg+xml", b"<svg>" + b" " * 30_000), "")

    def test_html_error_page_rejected(self):
        self.assertEqual(favicon.to_data_url("text/html", b"<html>404</html>"), "")
        self.assertEqual(favicon.to_data_url("image/png", b"not an image"), "")


@patch("apps.scans.favicon.assert_public_http_url", side_effect=lambda url: url)
class FetchTests(SimpleTestCase):
    def _client(self, handler):
        real = httpx.Client

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real(*args, **kwargs)

        return patch("apps.scans.favicon.httpx.Client", side_effect=factory)

    def test_redirect_rechecked_each_hop(self, mock_assert):
        def handler(request):
            if request.url.path == "/favicon.ico":
                return httpx.Response(301, headers={"location": "https://cdn.example.com/f.png"})
            return httpx.Response(200, headers={"content-type": "image/png"}, content=_png())

        with self._client(handler):
            data_url = favicon.discover_favicon("", "https://example.com/")
        self.assertTrue(data_url.startswith("data:image/png"))
        checked = [call.args[0] for call in mock_assert.call_args_list]
        self.assertEqual(
            checked, ["https://example.com/favicon.ico", "https://cdn.example.com/f.png"]
        )

    def test_oversized_body_rejected(self, _assert):
        def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "image/png"},
                content=b"0" * (favicon.MAX_ICON_BYTES + 1),
            )

        with self._client(handler):
            self.assertEqual(favicon.discover_favicon("", "https://example.com/"), "")

    def test_ssrf_rejection_moves_to_next_candidate(self, mock_assert):
        mock_assert.side_effect = lambda url: (
            (_ for _ in ()).throw(ValueError("private")) if "internal" in url else url
        )

        def handler(request):
            return httpx.Response(200, headers={"content-type": "image/png"}, content=_png())

        html = '<link rel="icon" sizes="32x32" href="http://internal.example/x.png">'
        with self._client(handler):
            data_url = favicon.discover_favicon(html, "https://example.com/")
        self.assertTrue(data_url.startswith("data:image/png"))


class RefreshTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="fav", password="safe-test-password")
        self.project = SiteProject.objects.create(
            user=user,
            name="example",
            origin="https://example.com",
            start_url="https://example.com/",
        )

    def test_needs_refresh_window(self):
        self.assertTrue(favicon.needs_refresh(self.project))
        self.project.favicon_checked_at = timezone.now() - timedelta(days=1)
        self.assertFalse(favicon.needs_refresh(self.project))
        self.project.favicon_checked_at = timezone.now() - timedelta(
            days=favicon.REFRESH_AFTER_DAYS + 1
        )
        self.assertTrue(favicon.needs_refresh(self.project))

    def test_failure_keeps_previous_icon(self):
        self.project.favicon = "data:image/png;base64,OLD"
        self.project.save()
        with patch("apps.scans.favicon.discover_favicon", return_value=""):
            favicon.refresh_project_favicon(self.project, "", "https://example.com/")
        self.project.refresh_from_db()
        self.assertEqual(self.project.favicon, "data:image/png;base64,OLD")
        self.assertIsNotNone(self.project.favicon_checked_at)
