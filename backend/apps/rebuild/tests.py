"""網頁複刻與優化的行為契約。

這個功能有兩個容易寫錯、而且錯了不會立刻被發現的地方，測試主要盯這兩點：

1. **複刻不該依賴 agent**：優化失敗時複刻仍必須落地。若把兩段綁在一起，
   agent 一掛使用者就什麼都拿不到。
2. **產出是第三方 HTML**：下載一定要 as_attachment + CSP sandbox，否則等於
   在 Argus 自己的網域上託管任意第三方 script。
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.rebuild.client import OpenCodeError
from apps.rebuild.models import SiteRebuild
from apps.rebuild.prompts import build_optimization_prompt
from apps.rebuild.services import run_rebuild
from apps.rebuild.snapshot import build_snapshot_html
from apps.scans.models import Finding, Page, ScanJob

User = get_user_model()


def _make_scan(user, url="https://example.com/"):
    return ScanJob.objects.create(
        user=user,
        original_url=url,
        normalized_url=url,
        origin="example.com",
        status=ScanJob.Status.COMPLETED,
        completed_at=timezone.now(),
    )


def _make_page(scan_job, dom="<html><head><title>t</title></head><body>hi</body></html>"):
    return Page.objects.create(
        scan_job=scan_job,
        url="https://example.com/",
        final_url="https://example.com/",
        origin="example.com",
        status_code=200,
        rendered_dom=dom,
    )


class SnapshotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="snap", password="safe-test-password")
        self.scan_job = _make_scan(self.user)

    def test_base_tag_is_injected_into_head(self):
        """沒有 <base>，複刻檔裡的相對路徑會相對於 Argus 解析 → 整頁沒樣式。"""
        page = _make_page(self.scan_job)
        html = build_snapshot_html(page)
        self.assertIn('<base href="https://example.com/">', html)
        self.assertLess(html.index("<base"), html.index("<title>"))

    def test_existing_base_is_not_duplicated(self):
        page = _make_page(
            self.scan_job,
            dom='<html><head><base href="https://cdn.example.com/"></head><body>x</body></html>',
        )
        self.assertEqual(build_snapshot_html(page).count("<base"), 1)

    def test_dom_without_head_still_gets_a_base(self):
        page = _make_page(self.scan_job, dom="<html><body>no head</body></html>")
        self.assertIn("<base href=", build_snapshot_html(page))

    def test_falls_back_to_raw_html_when_dom_missing(self):
        """爬蟲逾時會只留下 html、沒有 rendered_dom，這時仍要能複刻。"""
        page = _make_page(self.scan_job, dom="")
        page.html = "<html><head></head><body>raw</body></html>"
        page.save(update_fields=["html"])
        self.assertIn("raw", build_snapshot_html(page))

    def test_empty_page_raises(self):
        page = _make_page(self.scan_job, dom="")
        with self.assertRaises(ValueError):
            build_snapshot_html(page)


class PromptTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="prompt", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)

    def _finding(self, severity, title):
        return Finding.objects.create(
            scan_job=self.scan_job,
            page=self.page,
            category=Finding.Category.SEO,
            severity=severity,
            title=title,
            description="d",
            remediation="r",
            rule_id=title,
            ai_handoff_prompt="p",
        )

    def test_findings_are_ordered_by_severity(self):
        low = self._finding(Finding.Severity.LOW, "low-one")
        critical = self._finding(Finding.Severity.CRITICAL, "critical-one")
        prompt = build_optimization_prompt(self.page, [low, critical], "<html></html>", "out.html")
        self.assertLess(prompt.index("critical-one"), prompt.index("low-one"))

    def test_prompt_marks_page_html_as_untrusted_data(self):
        """被掃描站的 HTML 由對方完全控制，而收下它的 agent 有 shell。

        邊界宣告不是防護，但拿掉它連「誤把頁面文字當指令」都擋不住。
        """
        prompt = build_optimization_prompt(self.page, [], "<html></html>", "out.html")
        self.assertIn("<untrusted-data>", prompt)
        self.assertIn("<page-html>", prompt)

    @override_settings(ARGUS_OPENCODE_MAX_SNAPSHOT_BYTES=50)
    def test_truncation_is_announced(self):
        """不告知截斷，agent 會自行補完它沒看過的部分，憑空生出原站沒有的內容。"""
        prompt = build_optimization_prompt(self.page, [], "x" * 500, "out.html")
        self.assertIn("截斷", prompt)
        self.assertNotIn("x" * 100, prompt)


class _FakeClient:
    """替身：真的 client 會連外網並花錢，測試不得碰到它。"""

    def __init__(self, reply="done", file_content="<html>optimized</html>", error=None):
        self.reply = reply
        self.file_content = file_content
        self.error = error
        self.aborted = []
        self.read_path = ""
        self.is_configured = True

    def create_session(self, directory):
        self.directory = directory
        return "ses_fake"

    def prompt(self, session_id, text, agent, model=""):
        if self.error:
            raise self.error
        self.prompt_text = text
        return {"text": self.reply, "cost": 0.25, "model_id": "opencode/fake"}

    def read_file(self, directory, path):
        self.read_path = path
        return self.file_content

    def abort(self, session_id):
        self.aborted.append(session_id)


@override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc:4096")
class RunRebuildTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="run", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        self.rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)

    def _run(self, client):
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            return run_rebuild(self.rebuild)

    def test_success_writes_both_files(self):
        rebuild = self._run(_FakeClient())
        self.assertEqual(rebuild.status, SiteRebuild.Status.SUCCEEDED)
        self.assertTrue(rebuild.snapshot_path)
        self.assertTrue(rebuild.optimized_path)

    def test_each_rebuild_writes_to_its_own_path(self):
        """共用一個檔名的話，同時跑兩個掃描會互相覆蓋 optimized.html。

        cwd 是固定的（agent 主機上必須存在的既有目錄），隔離只能靠輸出路徑。
        """
        client = _FakeClient()
        self._run(client)
        self.assertIn(
            f"scan-{self.scan_job.id}-page-{self.page.id}", client.read_path
        )

    def test_session_cwd_is_the_configured_workspace(self):
        """cwd 換成不存在的目錄，opencode 會在送 prompt 時回 500（實測 1.18.29）。"""
        client = _FakeClient()
        with self.settings(ARGUS_OPENCODE_WORKSPACE="/tmp/opencode"):
            self._run(client)
        self.assertEqual(client.directory, "/tmp/opencode")

    def test_agent_failure_still_leaves_the_snapshot(self):
        rebuild = self._run(_FakeClient(error=OpenCodeError("provider 掛了")))
        self.assertEqual(rebuild.status, SiteRebuild.Status.FAILED)
        self.assertTrue(rebuild.snapshot_path, "優化失敗不該連複刻都拿不到")
        self.assertIn("provider", rebuild.error)

    def test_failure_aborts_the_session(self):
        """不 abort 會在 agent server 上留下跑不停的 session，繼續燒錢。"""
        client = _FakeClient(error=OpenCodeError("boom"))
        self._run(client)
        self.assertEqual(client.aborted, ["ses_fake"])

    def test_falls_back_to_html_fence_when_no_file_written(self):
        client = _FakeClient(
            reply="好了\n```html\n<html>fenced</html>\n```", file_content=None
        )
        rebuild = self._run(client)
        self.assertEqual(rebuild.status, SiteRebuild.Status.SUCCEEDED)

    def test_no_output_at_all_is_a_failure(self):
        rebuild = self._run(_FakeClient(reply="我不知道", file_content=None))
        self.assertEqual(rebuild.status, SiteRebuild.Status.FAILED)

    @override_settings(ARGUS_OPENCODE_ENABLED=False)
    def test_disabled_still_produces_the_snapshot(self):
        rebuild = run_rebuild(self.rebuild)
        self.assertTrue(rebuild.snapshot_path)
        self.assertEqual(rebuild.optimized_path, "")


class RebuildApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api", password="safe-test-password")
        self.other = User.objects.create_user(username="other", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_enqueues_the_task(self):
        with patch("apps.rebuild.views.run_site_rebuild.delay") as delay:
            response = self.client.post("/api/rebuilds/", {"page": self.page.id})
        self.assertEqual(response.status_code, 201)
        delay.assert_called_once()

    def test_cannot_rebuild_another_users_page(self):
        """scan_job 由 page 反查，不吃呼叫端傳的值——否則可掛別人的頁面。"""
        other_scan = _make_scan(self.other, url="https://victim.example/")
        other_page = _make_page(other_scan)
        response = self.client.post("/api/rebuilds/", {"page": other_page.id})
        self.assertEqual(response.status_code, 404)

    def test_download_is_attachment_and_sandboxed(self):
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        with patch("apps.rebuild.services.OpenCodeClient", return_value=_FakeClient()), \
                override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc"):
            run_rebuild(rebuild)

        response = self.client.get(f"/api/rebuilds/{rebuild.id}/download/?variant=optimized")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("sandbox", response["Content-Security-Policy"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_missing_variant_returns_404(self):
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        response = self.client.get(f"/api/rebuilds/{rebuild.id}/download/?variant=optimized")
        self.assertEqual(response.status_code, 404)

    def test_listing_hides_other_users_rebuilds(self):
        other_scan = _make_scan(self.other, url="https://victim.example/")
        SiteRebuild.objects.create(scan_job=other_scan, page=_make_page(other_scan))
        mine = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        response = self.client.get("/api/rebuilds/")
        ids = [row["id"] for row in response.json()["results"]]
        self.assertEqual(ids, [mine.id])
