"""SPA fallback 回預先渲染的公開頁（config/urls.py spa_page，frontend/scripts/prerender.mjs）。"""

import tempfile
from pathlib import Path
from unittest import mock

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=True)
class PrerenderedPageFallbackTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dist = Path(tmp.name)
        root_html = "<main>首頁預先渲染 {% 不是模板 %}</main>"
        (dist / "root.html").write_text(root_html, encoding="utf-8")
        (dist / "terms.html").write_text("<main>服務條款預先渲染</main>", encoding="utf-8")
        patcher = mock.patch("config.urls.FRONTEND_DIST", dist)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_root_serves_root_html_without_template_rendering(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "首頁預先渲染 {% 不是模板 %}")

    def test_public_page_serves_its_prerendered_html(self):
        self.assertContains(self.client.get("/terms"), "服務條款預先渲染")

    def test_other_paths_fall_back_to_index_html(self):
        with mock.patch("config.urls.TemplateView.as_view") as as_view:
            as_view.return_value = lambda request: HttpResponse("index")
            for path in ("/projects", "/scans/1", "/../root", "/Terms"):
                self.assertEqual(self.client.get(path).content, b"index", path)
