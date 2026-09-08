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

from django.conf import settings
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
from apps.rebuild.services import (
    _extract_edits,
    _human_reply,
    apply_edits,
    ask_followup,
    run_rebuild,
)
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
        prompt = build_optimization_prompt(self.page, [low, critical], "<html></html>")
        self.assertLess(prompt.index("critical-one"), prompt.index("low-one"))

    def test_prompt_marks_page_html_as_untrusted_data(self):
        """被掃描站的 HTML 由對方完全控制，而收下它的 agent 有 shell。

        邊界宣告不是防護，但拿掉它連「誤把頁面文字當指令」都擋不住。
        """
        prompt = build_optimization_prompt(self.page, [], "<html></html>")
        self.assertIn("<untrusted-data>", prompt)
        self.assertIn("<page-html>", prompt)

    @override_settings(ARGUS_OPENCODE_MAX_SNAPSHOT_BYTES=50)
    def test_truncation_is_announced(self):
        """不告知截斷，agent 會自行補完它沒看過的部分，憑空生出原站沒有的內容。"""
        prompt = build_optimization_prompt(self.page, [], "x" * 500)
        self.assertIn("截斷", prompt)
        self.assertNotIn("x" * 100, prompt)


class _FakeClient:
    """替身：真的 client 會連外網並花錢，測試不得碰到它。"""

    DEFAULT_REPLY = (
        '好了\n```json\n{"edits": [{'
        '"find": "<title>t</title>",'
        ' "replace": "<title>示範頁｜完整標題</title>",'
        ' "why": "title 過短"'
        "}]}\n```"
    )

    def __init__(self, reply=None, error=None, cost=0.25, events=None):
        reply = self.DEFAULT_REPLY if reply is None else reply
        self.cost = cost
        self.events = events if events is not None else [
            {"type": "thinking", "text": "先看看缺什麼"},
            {"type": "tool", "name": "write", "detail": "out.html"},
            {"type": "text", "text": "好了"},
        ]
        self.reply = reply
        self.error = error
        self.aborted = []
        self.is_configured = True

    def create_session(self, directory):
        self.directory = directory
        self.created_directory = directory
        return "ses_fake"

    def prompt(self, session_id, text, agent, model=""):
        if self.error:
            raise self.error
        self.prompt_text = text
        return {"text": self.reply, "cost": self.cost, "model_id": "opencode/fake"}

    def stream(self, session_id, text, agent, model="", directory=""):
        self.session_used = session_id
        if self.error:
            raise self.error
        self.prompt_text = text
        yield from self.events
        yield {"type": "done"}

    def session_result(self, session_id):
        return {"text": self.reply, "cost": self.cost, "model_id": "opencode/fake"}

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

    def test_edits_are_applied_to_the_snapshot(self):
        """產出＝原稿套用修改清單，不是模型重新產生的整份文件。

        模型整份重寫會撞到單次輸出上限：實測 84KB 的頁面在 15,022 token
        就被截斷（finish='length'），連工具呼叫參數都沒吐完、什麼都沒交付。
        """
        rebuild = self._run(_FakeClient())
        path = settings.MEDIA_ROOT / rebuild.optimized_path
        html = path.read_text(encoding="utf-8")
        self.assertIn("示範頁｜完整標題", html)
        self.assertIn("<base href=", html, "原稿的其餘部分必須原封不動")

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

    def test_no_edits_is_a_failure(self):
        rebuild = self._run(_FakeClient(reply="我不知道"))
        self.assertEqual(rebuild.status, SiteRebuild.Status.FAILED)

    def test_edits_that_match_nothing_are_a_failure(self):
        """全部對不上代表這一輪沒有任何價值，不能收錢。"""
        rebuild = self._run(
            _FakeClient(reply='```json\n{"edits": [{"find": "不存在的字串", "replace": "x"}]}\n```')
        )
        self.assertEqual(rebuild.status, SiteRebuild.Status.FAILED)
        self.assertIn("對不上", rebuild.error)

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

    # --- 每輪思考流 -------------------------------------------------
    def _rebuild_with_thread(self):
        return SiteRebuild.objects.create(
            scan_job=self.scan_job,
            page=self.page,
            conversation=[
                {
                    "role": "agent",
                    "text": "第一輪答案",
                    "trace": [{"kind": "tool", "text": "read index.html"}],
                },
                {"role": "user", "text": "為什麼沒補 alt？"},
                {
                    "role": "agent",
                    "text": "第二輪答案",
                    "trace": [{"kind": "think", "text": "檢查圖片"}],
                },
            ],
        )

    def test_detail_never_ships_archived_traces(self):
        """detail 在執行期間每秒被 polling，20 輪思考流一起送等於每秒好幾 MB。"""
        rebuild = self._rebuild_with_thread()

        response = self.client.get(f"/api/rebuilds/{rebuild.id}/")

        self.assertEqual(response.status_code, 200)
        thread = response.data["conversation"]
        self.assertEqual([t["has_trace"] for t in thread], [True, False, True])
        for turn in thread:
            self.assertNotIn("trace", turn)
        self.assertNotIn("read index.html", str(response.data["conversation"]))

    def test_turn_trace_returns_that_turns_entries(self):
        rebuild = self._rebuild_with_thread()

        response = self.client.get(f"/api/rebuilds/{rebuild.id}/turn-trace/?index=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["trace"], [{"kind": "think", "text": "檢查圖片"}])

    def test_turn_trace_rejects_a_negative_index(self):
        """負索引在 Python 會從尾端取值，那會悄悄回傳最後一輪而不是報錯。"""
        rebuild = self._rebuild_with_thread()

        response = self.client.get(f"/api/rebuilds/{rebuild.id}/turn-trace/?index=-1")

        self.assertEqual(response.status_code, 404)

    def test_turn_trace_rejects_a_non_integer_index(self):
        rebuild = self._rebuild_with_thread()

        response = self.client.get(f"/api/rebuilds/{rebuild.id}/turn-trace/?index=abc")

        self.assertEqual(response.status_code, 400)

    def test_turn_trace_is_scoped_to_the_owner(self):
        """思考流含被掃描站的內容，不能靠猜 id 就拿得到。"""
        rebuild = self._rebuild_with_thread()
        self.client.force_authenticate(user=self.other)

        response = self.client.get(f"/api/rebuilds/{rebuild.id}/turn-trace/?index=0")

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

    def test_trace_holds_process_and_reply_is_separate(self):
        """思考流只放過程，結論放 reply。

        混在一起的話，回答會被埋在幾百則推理片段之間，使用者找不到重點——
        這是實際回報過的體感問題（「Agent 回覆和思考流都感覺怪怪的」）。
        """
        rebuild = self._run(_FakeClient())
        kinds = [e["kind"] for e in rebuild.trace]
        self.assertIn("thinking", kinds)
        self.assertIn("tool", kinds)
        self.assertNotIn("text", kinds, "回覆不該出現在思考流裡")
        self.assertTrue(rebuild.reply, "回覆要獨立存進 reply")

    def test_consecutive_fragments_of_the_same_kind_are_merged(self):
        """推理是逐字吐出來的，不合併會變成幾百則單字，前端沒法看。"""
        client = _FakeClient(events=[{"type": "thinking", "text": c} for c in "檢查標題"])
        rebuild = self._run(client)
        thinking = [e for e in rebuild.trace if e["kind"] == "thinking"]
        self.assertEqual(len(thinking), 1)
        self.assertEqual(thinking[0]["text"], "檢查標題")

    def test_long_reasoning_rolls_over_instead_of_freezing(self):
        """單則寫滿後要換下一則，不能把後續內容丟掉。

        真實事故：使用者看到思考流停在推理的前 1500 字、斷在句子中間，
        以為 agent 卡住了。實際上 agent 還在跑，只是每一則新 delta 都被
        重新截回上限、內容再也不增加。
        """
        client = _FakeClient(events=[{"type": "thinking", "text": "字" * 900} for _ in range(4)])
        rebuild = self._run(client)
        thinking = [e for e in rebuild.trace if e["kind"] == "thinking"]
        total = sum(len(e["text"]) for e in thinking)
        self.assertGreater(len(thinking), 1, "寫滿後應該換一則")
        self.assertEqual(total, 3600, "內容不得遺失")

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


class ApplyEditsTests(TestCase):
    """修改清單的套用規則。

    這是取代「模型重寫整份 HTML」的核心：模型只描述差異，套用由程式做。
    實測 84KB 的頁面整份重寫會在 15,022 output token 被截斷（finish='length'），
    連工具呼叫的參數都吐不完。
    """

    def test_applies_every_matching_edit(self):
        html, report = apply_edits(
            "<html><title>a</title><p>b</p></html>",
            [
                {"find": "<title>a</title>", "replace": "<title>A</title>", "why": "1"},
                {"find": "<p>b</p>", "replace": "<p>B</p>", "why": "2"},
            ],
        )
        self.assertIn("<title>A</title>", html)
        self.assertIn("<p>B</p>", html)
        self.assertEqual([r["applied"] for r in report], [1, 1])

    def test_unmatched_edit_is_skipped_not_fatal(self):
        """模型常有幾筆憑印象重打而對不上，其餘是好的。

        全有全無會讓一兩個字的偏差毀掉整次產出，而使用者已經付過錢了。
        """
        html, report = apply_edits(
            "<html><title>a</title></html>",
            [
                {"find": "不存在", "replace": "x", "why": "對不上"},
                {"find": "<title>a</title>", "replace": "<title>A</title>", "why": "好的"},
            ],
        )
        self.assertIn("<title>A</title>", html)
        self.assertEqual([r["applied"] for r in report], [0, 1])

    def test_repeated_string_is_replaced_everywhere(self):
        """例如把整站的 alt="." 一次改掉——這正是模型會提的那種修改。"""
        html, report = apply_edits(
            '<img alt="."><img alt="."><img alt=".">',
            [{"find": 'alt="."', "replace": 'alt=""', "why": "無意義 alt"}],
        )
        self.assertNotIn('alt="."', html)
        self.assertEqual(report[0]["applied"], 3)

    def test_report_does_not_leak_whole_page(self):
        """report 會回傳給前端；find 可能很長，不能整段帶出去。"""
        _, report = apply_edits("x" * 5000, [{"find": "x" * 5000, "replace": "y"}])
        self.assertLessEqual(len(report[0]["find"]), 120)


@override_settings(ARGUS_OPENCODE_ENABLED=True, ARGUS_OPENCODE_BASE_URL="http://oc:4096")
class FollowupTests(TestCase):
    """追問：在同一個 agent session 裡繼續對話。

    沿用原 session 才有意義——session 裡已有整份 HTML 與診斷清單的上下文，
    重開等於要使用者再付一次把 85KB 塞進 prompt 的錢，而且 agent 會失憶。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="ask", password="safe-test-password")
        self.scan_job = _make_scan(self.user)
        self.page = _make_page(self.scan_job)
        wallet = get_or_create_wallet(self.user)
        wallet.balance = 1000
        wallet.save(update_fields=["balance"])
        self.rebuild = SiteRebuild.objects.create(
            scan_job=self.scan_job,
            page=self.page,
            status=SiteRebuild.Status.SUCCEEDED,
            opencode_session_id="ses_existing",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_reply_is_stored_separately_from_the_trace(self):
        """結論不能混在推理片段裡——使用者回報過「找不到重點」。"""
        client = _FakeClient(
            events=[
                {"type": "thinking", "text": "想一下"},
                {"type": "text", "text": "因為那些圖是裝飾性的"},
            ]
        )
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            ask_followup(self.rebuild, "為什麼沒補 alt？")
        self.assertEqual(self.rebuild.reply, "因為那些圖是裝飾性的")
        self.assertNotIn(
            "因為那些圖是裝飾性的",
            " ".join(e["text"] for e in self.rebuild.trace),
            "回覆不該出現在思考流裡",
        )

    def test_followup_clears_the_previous_round_trace(self):
        """上一輪的推理是「產生優化版」的過程，跟這個問題無關。

        留著會讓使用者以為新的回應沒進來——實際回報過「思考過程也沒有清空」。
        對話本身保存在 conversation，不會遺失。
        """
        self.rebuild.trace = [{"kind": "thinking", "text": "上一輪的推理"}]
        self.rebuild.save(update_fields=["trace"])
        client = _FakeClient(events=[{"type": "thinking", "text": "這一輪的推理"}])
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            ask_followup(self.rebuild, "問題")
        joined = " ".join(e["text"] for e in self.rebuild.trace)
        self.assertNotIn("上一輪的推理", joined)
        self.assertIn("這一輪的推理", joined)

    def test_previous_round_trace_is_archived_onto_its_own_turn(self):
        """清空 live trace 不等於丟掉它——它要跟著自己那一輪進對話串。

        舊版只有一個全域 trace 欄位，追問就清空，過去每一輪的推理永遠消失，
        畫面上也只能把「最後一輪的思考」畫在對話串最上方，離它對應的答案很遠。
        """
        self.rebuild.reply = "初次分析：我補了 title。"
        self.rebuild.trace = [{"kind": "tool", "text": "read index.html"}]
        self.rebuild.save(update_fields=["reply", "trace"])

        client = _FakeClient(events=[{"type": "thinking", "text": "這一輪的推理"}])
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            ask_followup(self.rebuild, "還能改什麼？")

        thread = self.rebuild.conversation
        self.assertEqual([t["role"] for t in thread], ["agent", "user", "agent"])
        # 第 0 輪保住了「產生優化版」那次的工具呼叫
        self.assertEqual(thread[0]["trace"], [{"kind": "tool", "text": "read index.html"}])
        # 使用者的提問沒有思考流可言
        self.assertNotIn("trace", thread[1])
        # 這一輪的推理歸檔在這一輪
        self.assertIn("這一輪的推理", " ".join(e["text"] for e in thread[2]["trace"]))

    def test_failed_followup_still_archives_what_it_managed_to_think(self):
        """失敗那一輪的過程往往才是使用者最想看的——不能因為失敗就丟掉。

        **刻意只給兩個事件**，遠少於 _TRACE_FLUSH_EVERY（8）。串流是每 8 個事件才
        把 trace 落地一次，所以這是最容易掉資料的路徑：跑沒幾步就死掉的那一輪，
        使用者想問的正是「它到底想了什麼才卡住」，而那份推理如果只存在記憶體裡，
        例外一拋就沒了。
        """
        client = _FakeClient(
            events=[
                {"type": "thinking", "text": "先看看缺什麼"},
                {"type": "error", "text": "agent 掛了"},
            ]
        )
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            ask_followup(self.rebuild, "問題")

        last = self.rebuild.conversation[-1]
        self.assertIn("（失敗）", last["text"])
        self.assertIn("先看看缺什麼", " ".join(e["text"] for e in last["trace"]))

    def test_a_long_round_that_dies_persists_the_whole_trace(self):
        """跨過落地門檻後才中斷時，歸檔進對話串的過程要完整。

        這一項**不**足以證明「中斷時會落地」——那是上一個測試（只給兩個事件、
        遠不到落地門檻）的工作。這裡即使拿掉中斷落地也會過：第一次落地之後
        rebuild.trace 與 _run_streaming 內部的 entries 指向同一個 list，後續片段
        會直接出現在記憶體物件上，而歸檔正是從那個物件讀的。

        留著是為了鎖住端到端行為：哪天有人把歸檔改成從 DB 重讀，這裡會紅。
        """
        client = _FakeClient(
            events=[{"type": "thinking", "text": f"步驟{i}"} for i in range(10)]
            + [{"type": "error", "text": "agent 掛了"}]
        )
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            ask_followup(self.rebuild, "問題")

        stored = SiteRebuild.objects.get(pk=self.rebuild.pk)
        joined = " ".join(e["text"] for e in stored.conversation[-1]["trace"])
        self.assertIn("步驟0", joined)   # 第一次落地就寫進去的
        self.assertIn("步驟9", joined)   # 落地之後、中斷之前才產生的

    def test_archived_trace_keeps_tool_calls_when_it_must_be_trimmed(self):
        """歸檔有上限，但工具呼叫是「agent 到底動了什麼」的稽核軌跡，優先留。"""
        self.rebuild.reply = "初次分析"
        self.rebuild.trace = (
            [{"kind": "tool", "text": f"tool-{i}"} for i in range(5)]
            + [{"kind": "thinking", "text": f"think-{i}"} for i in range(200)]
        )
        self.rebuild.save(update_fields=["reply", "trace"])

        with patch("apps.rebuild.services.OpenCodeClient", return_value=_FakeClient()):
            ask_followup(self.rebuild, "問題")

        archived = self.rebuild.conversation[0]["trace"]
        self.assertLessEqual(len(archived), 60)
        tools = [e["text"] for e in archived if e["kind"] == "tool"]
        self.assertEqual(tools, [f"tool-{i}" for i in range(5)], "工具呼叫被裁掉了")

    def test_first_analysis_reply_is_preserved_into_the_thread(self):
        """追問會清空 reply。不先把初次分析的說明收進對話串的話，
        使用者一追問，那份「改了什麼、哪些沒處理」就永遠消失了。
        """
        self.rebuild.reply = "初次分析：我補了 title，CSP 需伺服器端處理。"
        self.rebuild.save(update_fields=["reply"])
        with patch("apps.rebuild.services.OpenCodeClient", return_value=_FakeClient()):
            ask_followup(self.rebuild, "還能改什麼？")
        roles = [t["role"] for t in self.rebuild.conversation]
        self.assertEqual(roles, ["agent", "user", "agent"])
        self.assertIn("初次分析", self.rebuild.conversation[0]["text"])

    def test_reply_is_not_duplicated_into_the_thread_twice(self):
        """reply 與對話串的最後一則會是同一段文字，前端只能畫一次。

        使用者實際看到「Agent 回覆下面還有 Agent 的回覆，有兩個」。
        """
        with patch("apps.rebuild.services.OpenCodeClient", return_value=_FakeClient()):
            ask_followup(self.rebuild, "問題")
        agent_turns = [t["text"] for t in self.rebuild.conversation if t["role"] == "agent"]
        self.assertEqual(agent_turns[-1], self.rebuild.reply)

    def test_conversation_records_both_sides(self):
        with patch("apps.rebuild.services.OpenCodeClient", return_value=_FakeClient()):
            ask_followup(self.rebuild, "再多修一點")
        roles = [t["role"] for t in self.rebuild.conversation]
        self.assertEqual(roles, ["user", "agent"])
        self.assertEqual(self.rebuild.conversation[0]["text"], "再多修一點")

    def test_uses_the_existing_session(self):
        client = _FakeClient()
        with patch("apps.rebuild.services.OpenCodeClient", return_value=client):
            ask_followup(self.rebuild, "問題")
        self.assertEqual(client.session_used, "ses_existing")
        self.assertIsNone(
            getattr(client, "created_directory", None), "不該另開新 session"
        )

    def test_followup_is_charged(self):
        """settle_rebuild_actual 是冪等的，第二輪會被跳過——追問等於免費，
        但它花的是真錢。所以走 charge_rebuild_usage 事後扣款。"""
        before = get_or_create_wallet(self.user).balance
        with patch(
            "apps.rebuild.services.OpenCodeClient", return_value=_FakeClient(cost=0.05)
        ):
            ask_followup(self.rebuild, "問題")
        self.assertLess(get_or_create_wallet(self.user).balance, before)

    def test_failure_does_not_mark_the_rebuild_failed(self):
        """優化版已經產出了，追問失敗不該讓它看起來像整個沒做成。"""
        with patch(
            "apps.rebuild.services.OpenCodeClient",
            return_value=_FakeClient(error=OpenCodeError("provider 掛了")),
        ):
            ask_followup(self.rebuild, "問題")
        self.assertEqual(self.rebuild.status, SiteRebuild.Status.SUCCEEDED)
        self.assertIn("失敗", self.rebuild.conversation[-1]["text"])

    def test_api_rejects_empty_question(self):
        response = self.client.post(f"/api/rebuilds/{self.rebuild.id}/ask/", {"question": "  "})
        self.assertEqual(response.status_code, 400)

    def test_api_rejects_while_running(self):
        self.rebuild.status = SiteRebuild.Status.OPTIMIZING
        self.rebuild.save(update_fields=["status"])
        response = self.client.post(f"/api/rebuilds/{self.rebuild.id}/ask/", {"question": "x"})
        self.assertEqual(response.status_code, 409)

    def test_api_rejects_when_balance_is_too_low(self):
        """餘額為 0 的人必須在 agent 花掉真錢之前被擋下。"""
        wallet = get_or_create_wallet(self.user)
        wallet.balance = 0
        wallet.save(update_fields=["balance"])
        with patch("apps.rebuild.views.ask_rebuild_agent.delay") as delay:
            response = self.client.post(
                f"/api/rebuilds/{self.rebuild.id}/ask/", {"question": "x"}
            )
        self.assertEqual(response.status_code, 402)
        delay.assert_not_called()


class EditSchemaToleranceTests(TestCase):
    """模型不一定照 prompt 的欄位名走。

    實測看過它自己改用 {"selector","issue","old","new"}——只認 find/replace
    的話那批會整個被丟掉，使用者付了錢卻拿到「沒有提出任何修改」。
    """

    def test_accepts_old_new_aliases(self):
        edits = _extract_edits(
            '```json\n{"edits": [{"old": "<a>", "new": "<b>", "issue": "壞了"}]}\n```'
        )
        self.assertEqual(edits[0]["find"], "<a>")
        self.assertEqual(edits[0]["replace"], "<b>")
        self.assertEqual(edits[0]["why"], "壞了")

    def test_accepts_canonical_names(self):
        edits = _extract_edits(
            '```json\n{"edits": [{"find": "<a>", "replace": "<b>", "why": "r"}]}\n```'
        )
        self.assertEqual(edits[0]["find"], "<a>")

    def test_entries_without_any_find_key_are_dropped(self):
        self.assertEqual(_extract_edits('```json\n{"edits": [{"why": "只有說明"}]}\n```'), [])

    def test_bare_json_without_fence_still_parses(self):
        """模型偶爾忘記加圍欄。"""
        edits = _extract_edits('好了 {"edits": [{"find": "x", "replace": "y"}]} 完成')
        self.assertEqual(edits[0]["find"], "x")


class HumanReplyTests(TestCase):
    """交給使用者看的回覆不能是一坨 JSON。

    真實回報：「現在分析 Agent 的回復只有 Json 沒有任何說明，對於一個成熟的
    項目這太怪了」。JSON 是給程式吃的，修改內容另有 edit_report 呈現。
    """

    def test_json_block_is_stripped(self):
        text = '我補了 title，CSP 需要伺服器端處理。\n\n```json\n{"edits": []}\n```'
        self.assertEqual(_human_reply(text), "我補了 title，CSP 需要伺服器端處理。")

    def test_any_fenced_block_is_stripped(self):
        self.assertEqual(_human_reply("說明\n\n```html\n<p>x</p>\n```"), "說明")

    def test_prose_without_fences_is_untouched(self):
        self.assertEqual(_human_reply("只有說明沒有區塊"), "只有說明沒有區塊")

    def test_reply_that_is_only_json_becomes_empty(self):
        """只有 JSON 沒有說明時回空字串——前端會顯示「這一輪沒有文字回覆」，
        比顯示一坨 JSON 誠實。"""
        self.assertEqual(_human_reply('```json\n{"edits": []}\n```'), "")
