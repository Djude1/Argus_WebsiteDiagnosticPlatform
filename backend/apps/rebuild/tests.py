"""網頁複刻與優化的行為契約。

這個功能有兩個容易寫錯、而且錯了不會立刻被發現的地方，測試主要盯這兩點：

1. **複刻不該依賴 agent**：優化失敗時複刻仍必須落地。若把兩段綁在一起，
   agent 一掛使用者就什麼都拿不到。
2. **產出是第三方 HTML**：下載一定要 as_attachment + CSP sandbox，否則等於
   在 Argus 自己的網域上託管任意第三方 script。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.services import (
    estimate_rebuild_hold,
    get_or_create_wallet,
    hold_for_rebuild,
    refund_rebuild,
    settle_rebuild_actual,
)
from apps.rebuild.client import OpenCodeError
from apps.rebuild.models import SiteRebuild
from apps.rebuild.prompts import build_optimization_prompt
from apps.rebuild.services import output_relpath, run_rebuild
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

    def __init__(self, reply="done", file_content="<html>optimized</html>", error=None,
                 found_path=None, found_content=None, cost=0.25, events=None):
        self.cost = cost
        self.events = events if events is not None else [
            {"type": "thinking", "text": "先看看缺什麼"},
            {"type": "tool", "name": "write", "detail": "out.html"},
            {"type": "text", "text": "好了"},
        ]
        self.reply = reply
        self.file_content = file_content
        self.error = error
        # 模擬「agent 把檔案寫到別的地方」：指定路徑讀不到，但 find 找得到
        self.found_path = found_path
        self.found_content = found_content
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
        return {"text": self.reply, "cost": self.cost, "model_id": "opencode/fake"}

    def stream(self, session_id, text, agent, model="", directory=""):
        if self.error:
            raise self.error
        self.prompt_text = text
        yield from self.events
        yield {"type": "done"}

    def session_result(self, session_id):
        return {"text": self.reply, "cost": self.cost, "model_id": "opencode/fake"}

    def read_file(self, directory, path):
        self.read_path = path
        return self.found_content if path == self.found_path else self.file_content

    def find_file(self, directory, filename):
        return self.found_path

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
        """共用一個檔名的話，兩次複刻會互相覆蓋，也會讓 find 後備撈到舊檔。

        cwd 是固定的（agent 主機上必須存在的既有目錄），隔離只能靠檔名。
        """
        client = _FakeClient()
        self._run(client)
        self.assertIn(f"argus-rebuild-{self.rebuild.pk}-", client.read_path)

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


class RebuildBillingTests(TestCase):
    """複刻的計費行為。

    重點只有一個：**沒拿到優化版就不該付錢**。所以失敗一律退，而且退款要
    綁在這一次複刻上，不能把同一掃描其他複刻的預扣一起退掉。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="pay", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        wallet = get_or_create_wallet(self.user)
        wallet.balance = 1000
        wallet.save(update_fields=["balance"])
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _balance(self) -> int:
        return get_or_create_wallet(self.user).balance

    def test_create_holds_coins(self):
        with patch("apps.rebuild.views.run_site_rebuild.delay"):
            response = self.client.post("/api/rebuilds/", {"page": self.page.id})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self._balance(), 1000 - estimate_rebuild_hold())

    def test_insufficient_balance_is_rejected_before_any_agent_call(self):
        """餘額不足必須在排任務**之前**擋下，否則 agent 已經花掉真錢了。"""
        wallet = get_or_create_wallet(self.user)
        wallet.balance = 0
        wallet.save(update_fields=["balance"])
        with patch("apps.rebuild.views.run_site_rebuild.delay") as delay:
            response = self.client.post("/api/rebuilds/", {"page": self.page.id})
        self.assertEqual(response.status_code, 402)
        delay.assert_not_called()
        self.assertFalse(SiteRebuild.objects.exists(), "被擋下就不該留下孤兒紀錄")

    @override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc")
    def test_failure_refunds_in_full(self):
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, rebuild)
        held = self._balance()
        with patch(
            "apps.rebuild.services.OpenCodeClient",
            return_value=_FakeClient(error=OpenCodeError("provider 掛了")),
        ):
            run_rebuild(rebuild)
        self.assertEqual(rebuild.status, SiteRebuild.Status.FAILED)
        self.assertEqual(self._balance(), held + estimate_rebuild_hold())

    @override_settings(
        ARGUS_OPENCODE_ENABLED=True,
        ARGUS_OPENCODE_BASE_URL="http://oc",
        ARGUS_COIN_PER_USD=100,
        ARGUS_COIN_REBUILD_HOLD=30,
    )
    def test_success_charges_actual_usage_and_refunds_the_rest(self):
        """預扣是額度不是價格：$0.05 × 100 = 5 點，其餘 25 點要退。"""
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, rebuild)
        after_hold = self._balance()
        with patch(
            "apps.rebuild.services.OpenCodeClient", return_value=_FakeClient(cost=0.05)
        ):
            run_rebuild(rebuild)
        self.assertEqual(rebuild.status, SiteRebuild.Status.SUCCEEDED)
        self.assertEqual(self._balance(), after_hold + 25)
        self.assertEqual(rebuild.coins_charged, 5)

    @override_settings(
        ARGUS_OPENCODE_ENABLED=True,
        ARGUS_OPENCODE_BASE_URL="http://oc",
        ARGUS_COIN_PER_USD=100,
        ARGUS_COIN_REBUILD_HOLD=30,
    )
    def test_usage_above_the_hold_is_capped_not_chased(self):
        """實際用量超過預扣時只收預扣額。

        追扣等於在使用者沒同意、也沒再檢查餘額的情況下二次扣款，
        可能把餘額扣成負數。
        """
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, rebuild)
        after_hold = self._balance()
        with patch(
            "apps.rebuild.services.OpenCodeClient", return_value=_FakeClient(cost=9.99)
        ):
            run_rebuild(rebuild)
        self.assertEqual(self._balance(), after_hold, "不得再多扣")
        self.assertEqual(rebuild.coins_charged, 30)

    @override_settings(
        ARGUS_OPENCODE_ENABLED=True,
        ARGUS_OPENCODE_BASE_URL="http://oc",
        ARGUS_COIN_PER_USD=100,
        ARGUS_COIN_REBUILD_MIN=1,
    )
    def test_free_model_still_costs_the_minimum(self):
        """agent 用免費模型時 USD 成本是 0，但 worker 與儲存成本不會消失。"""
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, rebuild)
        after_hold = self._balance()
        with patch(
            "apps.rebuild.services.OpenCodeClient", return_value=_FakeClient(cost=0)
        ):
            run_rebuild(rebuild)
        self.assertEqual(rebuild.coins_charged, 1)
        self.assertEqual(self._balance(), after_hold + estimate_rebuild_hold() - 1)

    def test_settlement_is_idempotent(self):
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, rebuild)
        rebuild.cost_usd = Decimal("0.05")
        rebuild.save(update_fields=["cost_usd"])
        settle_rebuild_actual(self.user, rebuild)
        once = self._balance()
        settle_rebuild_actual(self.user, rebuild)
        self.assertEqual(self._balance(), once)

    @override_settings(ARGUS_OPENCODE_ENABLED=False)
    def test_disabled_optimization_is_refunded(self):
        """只拿到不花錢的原樣快照，等於優化沒交付，不能收錢。"""
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, rebuild)
        held = self._balance()
        run_rebuild(rebuild)
        self.assertEqual(self._balance(), held + estimate_rebuild_hold())

    def test_refund_is_idempotent(self):
        """worker 與其他路徑可能各退一次，第二次不能再加錢。"""
        rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, rebuild)
        refund_rebuild(self.user, rebuild, reason="失敗")
        after_first = self._balance()
        refund_rebuild(self.user, rebuild, reason="失敗")
        self.assertEqual(self._balance(), after_first)

    def test_refund_does_not_touch_sibling_rebuilds(self):
        """同一掃描的另一次複刻若還在跑，它的預扣不能被這次的退款帶走。"""
        first = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        second = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        hold_for_rebuild(self.user, first)
        hold_for_rebuild(self.user, second)
        both_held = self._balance()

        refund_rebuild(self.user, first, reason="失敗")

        self.assertEqual(self._balance(), both_held + estimate_rebuild_hold())

    def test_cost_endpoint_reports_hold_and_balance(self):
        """回傳的是預扣上限。欄位名不能叫 cost——那會讓前端把額度當成價格顯示。"""
        response = self.client.get("/api/rebuilds/cost/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hold"], estimate_rebuild_hold())
        self.assertEqual(response.json()["balance"], 1000)


@override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc:4096")
class MisplacedOutputTests(TestCase):
    """agent 沒把檔案寫在指定位置時的取回行為。

    這不是假設的情況：實測 agent 自己建了 `argus/scan-1-page-1/` 子目錄再把
    檔案放進去，回覆裡還宣稱已經寫好。只信指定路徑的話會誤判成「未產出」，
    使用者白等一輪、還要重扣一次點數。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="misplaced", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        self.rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)

    def test_recovers_file_written_to_a_subdirectory(self):
        client = _FakeClient(
            file_content=None,
            found_path="argus/scan-1-page-1/argus-rebuild-1-optimized.html",
            found_content="<html>recovered</html>",
        )
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            rebuild = run_rebuild(self.rebuild)
        self.assertEqual(rebuild.status, SiteRebuild.Status.SUCCEEDED)

    def test_output_filename_is_unique_per_attempt(self):
        """用 scan/page 命名的話，重跑會撞名，find 可能撈到上一次的舊檔。"""
        second = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)
        self.assertNotEqual(output_relpath(self.rebuild), output_relpath(second))


@override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc:4096")
class OutputValidationTests(TestCase):
    """交付前必須確認拿到的是一份網頁。

    真實事故：工作目錄裡留著一個同名殘檔，內容是別人測試寫入權限時留下的
    一行純文字（`test sudo tee access`）。agent 那一輪其實沒寫成功，但舊程式
    只檢查「非空」，就把那 20 bytes 當成「優化後的網頁」讓使用者下載。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="valid", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        self.rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)

    def _run(self, client):
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            return run_rebuild(self.rebuild)

    def test_non_html_file_is_rejected(self):
        rebuild = self._run(_FakeClient(file_content="test sudo tee access"))
        self.assertEqual(rebuild.status, SiteRebuild.Status.FAILED)
        self.assertEqual(rebuild.optimized_path, "", "非網頁內容不得被寫成產出")

    def test_non_html_file_does_not_block_the_fence_fallback(self):
        """殘檔擋在前面時，仍要能從回覆裡撈到真正的產出。"""
        rebuild = self._run(
            _FakeClient(
                file_content="test sudo tee access",
                reply="好了\n```html\n<html><body>real</body></html>\n```",
            )
        )
        self.assertEqual(rebuild.status, SiteRebuild.Status.SUCCEEDED)

    def test_non_html_fence_is_also_rejected(self):
        rebuild = self._run(
            _FakeClient(file_content=None, reply="```\n我沒辦法完成\n```")
        )
        self.assertEqual(rebuild.status, SiteRebuild.Status.FAILED)

    def test_accepts_a_normal_document(self):
        rebuild = self._run(
            _FakeClient(file_content="<!DOCTYPE html><html><body>ok</body></html>")
        )
        self.assertEqual(rebuild.status, SiteRebuild.Status.SUCCEEDED)


@override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc:4096")
class TraceTests(TestCase):
    """agent 的思考過程要能即時呈現給使用者。

    這個功能的價值在「看得到它在做什麼」——優化是黑箱又要收費，沒有過程
    使用者無法判斷結果是否可信。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="trace", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        self.rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)

    def _run(self, client):
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            return run_rebuild(self.rebuild)

    def test_trace_records_thinking_tools_and_text(self):
        rebuild = self._run(_FakeClient())
        kinds = [e["kind"] for e in rebuild.trace]
        self.assertIn("thinking", kinds)
        self.assertIn("tool", kinds)
        self.assertIn("text", kinds)

    def test_consecutive_fragments_of_the_same_kind_are_merged(self):
        """推理是逐字吐出來的，不合併會變成幾百則單字，前端沒法看。"""
        client = _FakeClient(events=[{"type": "thinking", "text": c} for c in "檢查標題"])
        rebuild = self._run(client)
        thinking = [e for e in rebuild.trace if e["kind"] == "thinking"]
        self.assertEqual(len(thinking), 1)
        self.assertEqual(thinking[0]["text"], "檢查標題")

    def test_trace_is_capped(self):
        """沒有上限的話，話多的模型能把單列撐到幾 MB，而列表每次 polling 都讀它。"""
        client = _FakeClient(
            events=[{"type": "tool", "name": f"t{i}", "detail": ""} for i in range(500)]
        )
        rebuild = self._run(client)
        self.assertLessEqual(len(rebuild.trace), 120)

    def test_trace_is_visible_on_the_detail_endpoint(self):
        self._run(_FakeClient())
        client = APIClient()
        client.force_authenticate(user=self.user)
        row = client.get(f"/api/rebuilds/{self.rebuild.id}/").json()
        self.assertTrue(row["trace"], "專屬頁面要靠這個欄位呈現過程")

    def test_list_does_not_carry_the_trace(self):
        """列表被每秒 polling；帶著思考流等於每次都把上百 KB 一起撈出來。"""
        self._run(_FakeClient())
        client = APIClient()
        client.force_authenticate(user=self.user)
        row = client.get("/api/rebuilds/").json()["results"][0]
        self.assertNotIn("trace", row)


@override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc:4096")
class FindingScopeTests(TestCase):
    """送進 prompt 的 findings 必須與前端頁籤看到的一致。

    真實事故：使用者拿到的「優化版」與原稿一模一樣。原因是只取了
    `page.findings`——站台層級的 finding（page=NULL）全被漏掉，那一頁剛好
    沒有頁面層級的 finding，prompt 就變成「沒有偵測到問題，請原樣輸出」，
    agent 照做。前端的頁籤過濾是「這一頁的 + 全站的」，兩邊必須對齊。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="scope", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        self.rebuild = SiteRebuild.objects.create(scan_job=self.scan_job, page=self.page)

    def _finding(self, title, page):
        Finding.objects.create(
            scan_job=self.scan_job, page=page, category=Finding.Category.SEO,
            severity=Finding.Severity.HIGH, title=title, description="d",
            remediation="r", rule_id=title, ai_handoff_prompt="p",
        )

    def _prompt_for(self):
        client = _FakeClient()
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            run_rebuild(self.rebuild)
        return client.prompt_text

    def test_site_wide_findings_are_included(self):
        self._finding("站台級問題", None)
        self.assertIn("站台級問題", self._prompt_for())

    def test_page_findings_are_included(self):
        self._finding("本頁問題", self.page)
        self.assertIn("本頁問題", self._prompt_for())

    def test_other_pages_findings_are_excluded(self):
        other = Page.objects.create(
            scan_job=self.scan_job, url="https://example.com/other",
            final_url="https://example.com/other", origin="example.com",
            status_code=200, rendered_dom="<html><body>x</body></html>",
        )
        self._finding("別頁問題", other)
        self.assertNotIn("別頁問題", self._prompt_for())
