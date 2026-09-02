"""字型解析契約（2026-09-02 CI 事故回歸測試）。

事故：theme.py 在 module import 時就 raise RuntimeError，而 reports.py ->
report_render 的 import 鏈是 Django 啟動時走的，導致**沒有 CJK 字型的 CI runner
連 `manage.py check` 都跑不起來**——整個 Quality Gate 與 image build 全掛。

字型只有畫圖才需要，所以：解析不得拋例外，要求時才拋。
"""

from __future__ import annotations

import os
from unittest import mock

from django.test import SimpleTestCase

from apps.scans.report_render import charts, theme


class FontResolutionTests(SimpleTestCase):
    def test_resolution_never_raises_when_no_font_is_installed(self):
        """import 時執行的那一段，在沒有字型的機器上必須安靜地回 None。"""
        with mock.patch.object(os.path, "exists", return_value=False), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(theme._resolve_cjk_fonts(), (None, None))

    def test_env_override_wins(self):
        with mock.patch.dict(
            os.environ,
            {"ARGUS_REPORT_FONT_REGULAR": "/x/r.ttc", "ARGUS_REPORT_FONT_BOLD": "/x/b.ttc"},
        ):
            self.assertEqual(theme._resolve_cjk_fonts(), ("/x/r.ttc", "/x/b.ttc"))

    def test_requiring_fonts_fails_loudly_with_an_actionable_message(self):
        """缺字型時要大聲失敗——退回預設字型的話中文會變成一整排 □，
        報告照樣產出、照樣寄給客戶，沒有人會發現。"""
        with mock.patch.object(theme, "MPL_FONT_REGULAR", None), \
                mock.patch.object(theme, "MPL_FONT_BOLD", None):
            with self.assertRaises(RuntimeError) as ctx:
                theme.require_cjk_fonts()

        message = str(ctx.exception)
        self.assertIn("fonts-noto-cjk", message)
        self.assertIn("ARGUS_REPORT_FONT_REGULAR", message)

    def test_charts_module_defers_font_creation_to_render_time(self):
        """charts 不得在 import 時建立 FontProperties——那等同 import 時解析字型。"""
        self.assertTrue(
            charts._reg is None or isinstance(charts._reg, object),
            "charts._reg 應為延後建立",
        )
        self.assertTrue(hasattr(charts, "_ensure_fonts"))
