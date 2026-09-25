from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admin_api.models import AdminAuditLog
from apps.billing.models import CoinTransaction, CoinWallet
from apps.billing.services import purchase_plan
from apps.reviews.models import PlatformReview, ReviewReport, ReviewResponse
from apps.scans.models import ScanJob


def _make_user(username, *, staff=False, **extra):
    defaults = {
        "email": f"{username}@example.com",
        "password": "safe-test-password",
        "is_staff": staff,
    }
    defaults.update(extra)
    return get_user_model().objects.create_user(username=username, **defaults)


def _make_scan(user, **kwargs):
    return ScanJob.objects.create(
        user=user,
        original_url=kwargs.pop("url", "https://example.com/"),
        normalized_url=kwargs.pop("nurl", "https://example.com/"),
        origin=kwargs.pop("origin", "https://example.com"),
        **kwargs,
    )


class AdminPermissionTests(APITestCase):
    def test_non_staff_user_blocked(self):
        normal = _make_user("normal")
        self.client.force_authenticate(normal)
        for name in ["admin-overview", "admin-users", "admin-transactions"]:
            response = self.client.get(reverse(name))
            self.assertEqual(
                response.status_code, status.HTTP_403_FORBIDDEN,
                msg=f"endpoint {name} 應該 403 阻擋非 staff",
            )

    def test_anonymous_blocked(self):
        response = self.client.get(reverse("admin-overview"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_staff_user_allowed(self):
        admin = _make_user("admin1", staff=True)
        self.client.force_authenticate(admin)
        response = self.client.get(reverse("admin-overview"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class OverviewTests(APITestCase):
    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)

    def test_overview_returns_totals_and_recent_lists(self):
        u = _make_user("u1")
        from apps.billing.models import PricingPlan
        plan = PricingPlan.objects.get(code="starter")
        purchase_plan(u, plan)
        _make_scan(u)

        response = self.client.get(reverse("admin-overview"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        totals = response.data["totals"]
        self.assertGreaterEqual(totals["users"], 2)
        self.assertGreaterEqual(totals["scans"], 1)
        self.assertGreaterEqual(totals["revenue_ntd"], 100)
        self.assertIn("recent_purchases", response.data)
        self.assertIn("recent_scans", response.data)


class UsersEndpointTests(APITestCase):
    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.alice = _make_user("alice")
        self.bob = _make_user("bob")

    def test_list_users_search_by_email(self):
        response = self.client.get(reverse("admin-users"), {"q": "alice"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in response.data["users"]]
        self.assertIn("alice", usernames)
        self.assertNotIn("bob", usernames)

    def test_user_detail_includes_wallet_and_transactions(self):
        response = self.client.get(
            reverse("admin-user-detail", args=[self.alice.id]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "alice")
        self.assertEqual(response.data["wallet"]["balance"], 200)
        # signal 發放的月贈點交易
        self.assertEqual(len(response.data["recent_transactions"]), 1)

    def test_adjust_coin_adds_and_records_admin_actor(self):
        response = self.client.post(
            reverse("admin-adjust-coin", args=[self.alice.id]),
            {"delta": 500, "note": "退費 #scan1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["wallet_balance"], 700)
        # 確認交易紀錄 admin_actor 為當前 admin
        tx = CoinTransaction.objects.filter(
            wallet__user=self.alice,
            kind=CoinTransaction.Kind.ADMIN_ADJUST,
        ).get()
        self.assertEqual(tx.admin_actor, self.admin)
        self.assertEqual(tx.note, "退費 #scan1")

    def test_adjust_coin_negative_clamped_to_zero(self):
        response = self.client.post(
            reverse("admin-adjust-coin", args=[self.alice.id]),
            {"delta": -500},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # 原 200，扣 -500 → 餘額夾到 0
        self.assertEqual(response.data["wallet_balance"], 0)

    def test_adjust_coin_zero_rejected(self):
        response = self.client.post(
            reverse("admin-adjust-coin", args=[self.alice.id]),
            {"delta": 0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TransactionsEndpointTests(APITestCase):
    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.user = _make_user("buyer")
        from apps.billing.models import PricingPlan
        purchase_plan(self.user, PricingPlan.objects.get(code="standard"))

    def test_list_all_transactions(self):
        response = self.client.get(reverse("admin-transactions"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kinds = {t["kind"] for t in response.data["transactions"]}
        self.assertIn(CoinTransaction.Kind.PURCHASE, kinds)

    def test_filter_by_kind(self):
        response = self.client.get(
            reverse("admin-transactions"),
            {"kind": CoinTransaction.Kind.PURCHASE},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kinds = {t["kind"] for t in response.data["transactions"]}
        self.assertEqual(kinds, {CoinTransaction.Kind.PURCHASE})


class ReviewsEndpointTests(APITestCase):
    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.user = _make_user("reviewer")
        self.review = PlatformReview.objects.create(
            user=self.user, rating=4, comment="不錯",
        )

    def test_list_reviews_marks_pending(self):
        response = self.client.get(reverse("admin-reviews"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pending_count"], 1)
        self.assertTrue(response.data["reviews"][0]["is_pending"])
        self.assertIsNone(response.data["reviews"][0]["response"])

    def test_review_list_query_count_does_not_grow_per_review(self):
        with CaptureQueriesContext(connection) as one_review_queries:
            self.client.get(reverse("admin-reviews"))

        for index in range(10):
            user = _make_user(f"reviewer-{index}")
            PlatformReview.objects.create(user=user, rating=4, comment="測試")
        with CaptureQueriesContext(connection) as many_review_queries:
            response = self.client.get(reverse("admin-reviews"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(one_review_queries), len(many_review_queries))

    def test_reply_creates_single_official_response(self):
        response = self.client.post(
            reverse("admin-reply-review", args=[self.review.id]),
            {"reply": "謝謝你的回饋！"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        official = ReviewResponse.objects.get(review=self.review)
        self.assertEqual(official.author, self.admin)
        self.assertEqual(official.body, "謝謝你的回饋！")
        self.assertFalse(response.data["is_pending"])

    def test_reply_updates_instead_of_creating_a_thread(self):
        ReviewResponse.objects.create(
            review=self.review,
            author=self.admin,
            body="舊回覆",
        )
        self.client.post(
            reverse("admin-reply-review", args=[self.review.id]),
            {"reply": "更新後回覆"},
            format="json",
        )
        self.assertEqual(ReviewResponse.objects.filter(review=self.review).count(), 1)
        self.assertEqual(
            ReviewResponse.objects.get(review=self.review).body,
            "更新後回覆",
        )

    def test_admin_reply_cannot_override_user_rating(self):
        response = self.client.post(
            reverse("admin-reply-review", args=[self.review.id]),
            {"reply": "已協助處理", "rating": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 4)

    def test_reply_requires_at_least_reply_or_rating(self):
        response = self.client.post(
            reverse("admin-reply-review", args=[self.review.id]),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reply_creates_audit_log_entry(self):
        from apps.admin_api.models import AdminAuditLog
        self.client.post(
            reverse("admin-reply-review", args=[self.review.id]),
            {"reply": "已收到"},
            format="json",
        )
        log = AdminAuditLog.objects.get(action=AdminAuditLog.Action.REVIEW_REPLY)
        self.assertEqual(log.admin_actor, self.admin)
        self.assertEqual(log.target_user, self.user)

    def test_reply_can_be_deleted_explicitly(self):
        ReviewResponse.objects.create(
            review=self.review,
            author=self.admin,
            body="準備刪除的回覆",
        )
        response = self.client.delete(
            reverse("admin-reply-review", args=[self.review.id]),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ReviewResponse.objects.filter(review=self.review).exists())

    def test_moderation_hides_review_and_resolves_reports(self):
        reporter = _make_user("reporter")
        report = ReviewReport.objects.create(
            review=self.review,
            reporter=reporter,
            reason=ReviewReport.Reason.PRIVACY,
        )
        response = self.client.patch(
            reverse("admin-moderate-review", args=[self.review.id]),
            {"status": PlatformReview.Status.HIDDEN},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.review.refresh_from_db()
        report.refresh_from_db()
        self.assertEqual(self.review.status, PlatformReview.Status.HIDDEN)
        self.assertEqual(report.status, ReviewReport.Status.RESOLVED)
        self.assertEqual(report.resolved_by, self.admin)

    def test_moderation_does_not_resolve_official_response_reports(self):
        reporter = _make_user("response-reporter")
        official_response = ReviewResponse.objects.create(
            review=self.review,
            author=self.admin,
            body="Official response",
        )
        parent_report = ReviewReport.objects.create(
            review=self.review,
            reporter=reporter,
            reason=ReviewReport.Reason.PRIVACY,
        )
        response_report = ReviewReport.objects.create(
            review=self.review,
            response=official_response,
            reporter=reporter,
            reason=ReviewReport.Reason.ABUSE,
        )

        listing = self.client.get(reverse("admin-reviews"))
        item = listing.data["reviews"][0]
        self.assertEqual(item["pending_report_count"], 1)
        self.assertEqual(item["response_pending_report_count"], 1)

        response = self.client.patch(
            reverse("admin-moderate-review", args=[self.review.id]),
            {"status": PlatformReview.Status.HIDDEN},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        parent_report.refresh_from_db()
        response_report.refresh_from_db()
        self.assertEqual(parent_report.status, ReviewReport.Status.RESOLVED)
        self.assertEqual(response_report.status, ReviewReport.Status.PENDING)


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class ScansEndpointTests(APITestCase):
    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.user = _make_user("scanner")
        self.scan = _make_scan(self.user, origin="https://abc.com")

    def test_list_scans_returns_username_and_counts(self):
        response = self.client.get(reverse("admin-scans"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["scans"][0]
        self.assertEqual(item["username"], "scanner")
        self.assertEqual(item["origin"], "https://abc.com")
        self.assertIn("findings_count", item)

    def test_list_scans_search_by_origin(self):
        _make_scan(self.user, origin="https://xyz.com")
        response = self.client.get(reverse("admin-scans"), {"q": "xyz"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        origins = [s["origin"] for s in response.data["scans"]]
        self.assertEqual(origins, ["https://xyz.com"])

    def test_scan_detail_returns_warning_summary(self):
        self.scan.warning_summary = {"blocked_urls": ["x"]}
        self.scan.save()
        response = self.client.get(
            reverse("admin-scan-detail", args=[self.scan.id]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["warning_summary"]["blocked_urls"], ["x"])


class CmsCrudTests(APITestCase):
    """admin_api 的 CMS CRUD endpoints（features / team / releases / plans）。"""

    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)

    def test_features_list_returns_items(self):
        response = self.client.get("/api/admin/cms/features/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("items", response.data)
        # seed migration 至少 6 個
        self.assertGreaterEqual(len(response.data["items"]), 6)

    def test_features_create_and_audit(self):
        from apps.admin_api.models import AdminAuditLog
        from apps.content.models import ProjectFeature
        response = self.client.post(
            "/api/admin/cms/features/",
            {
                "icon": "🔥",
                "title": "新功能",
                "description": "測試新增",
                "sort_order": 99,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ProjectFeature.objects.filter(title="新功能").exists())
        # 寫了 audit log
        self.assertTrue(AdminAuditLog.objects.filter(admin_actor=self.admin).exists())

    def test_features_update(self):
        from apps.content.models import ProjectFeature
        f = ProjectFeature.objects.create(title="待改", description="x", sort_order=10)
        response = self.client.put(
            f"/api/admin/cms/features/{f.id}/",
            {
                "icon": "✨",
                "title": "改完",
                "description": "y",
                "sort_order": 11,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f.refresh_from_db()
        self.assertEqual(f.title, "改完")

    def test_features_delete(self):
        from apps.content.models import ProjectFeature
        f = ProjectFeature.objects.create(title="要刪", description="x")
        response = self.client.delete(f"/api/admin/cms/features/{f.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ProjectFeature.objects.filter(id=f.id).exists())

    def test_plans_crud(self):
        from apps.billing.models import PricingPlan
        # 新增
        response = self.client.post(
            "/api/admin/cms/plans/",
            {
                "code": "trial", "name": "試用", "price_ntd": 50,
                "coin_amount": 50, "sort_order": 0, "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan = PricingPlan.objects.get(code="trial")
        # 改價
        self.client.put(
            f"/api/admin/cms/plans/{plan.id}/",
            {
                "code": "trial", "name": "試用", "price_ntd": 80,
                "coin_amount": 100, "sort_order": 0, "is_active": True,
            },
            format="json",
        )
        plan.refresh_from_db()
        self.assertEqual(plan.price_ntd, 80)
        self.assertEqual(plan.coin_amount, 100)

    def test_non_staff_blocked(self):
        normal = _make_user("normal_user")
        self.client.force_authenticate(normal)
        response = self.client.get("/api/admin/cms/features/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MeEndpointTests(APITestCase):
    def test_me_returns_is_staff_flag(self):
        admin = _make_user("admin", staff=True)
        self.client.force_authenticate(admin)
        response = self.client.get(reverse("admin-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_staff"])

    def test_me_works_for_normal_user(self):
        normal = _make_user("normal")
        self.client.force_authenticate(normal)
        response = self.client.get(reverse("admin-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_staff"])


def _make_agent_session(user, *, provider="minimax", model="abab", tokens=1000, scan=None):
    from apps.scans.models import AgentSession
    if scan is None:
        scan = _make_scan(user)
    return AgentSession.objects.create(
        scan_job=scan,
        provider=provider,
        model=model,
        status=AgentSession.Status.COMPLETED,
        total_tokens=tokens,
    )


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class AIUsageTests(APITestCase):
    """admin overview / dashboard / user_detail 的 AI 使用量欄位。"""

    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.alice = _make_user("alice")
        self.bob = _make_user("bob")
        _make_agent_session(self.alice, provider="minimax", tokens=5000)
        _make_agent_session(self.alice, provider="glm", tokens=3000)
        _make_agent_session(self.bob, provider="minimax", tokens=2000)

    def test_overview_includes_ai_token_totals(self):
        response = self.client.get(reverse("admin-overview"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        totals = response.data["totals"]
        self.assertEqual(totals["ai_tokens_total"], 10000)
        self.assertEqual(totals["ai_sessions_total"], 3)

    def test_user_detail_includes_ai_usage_breakdown(self):
        response = self.client.get(
            reverse("admin-user-detail", args=[self.alice.id]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ai = response.data["ai_usage"]
        self.assertEqual(ai["total_tokens"], 8000)
        self.assertEqual(ai["total_sessions"], 2)
        providers = {row["provider"] for row in ai["by_provider"]}
        self.assertEqual(providers, {"minimax", "glm"})

    def test_user_detail_ai_usage_does_not_leak_others(self):
        # bob 的 detail 不該包含 alice 的 tokens
        response = self.client.get(
            reverse("admin-user-detail", args=[self.bob.id]),
        )
        self.assertEqual(response.data["ai_usage"]["total_tokens"], 2000)
        self.assertEqual(response.data["ai_usage"]["total_sessions"], 1)

    def test_dashboard_returns_14_day_series(self):
        response = self.client.get(reverse("admin-dashboard"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["series"]), 14)
        # 所有 keys 一致
        for row in response.data["series"]:
            self.assertIn("date", row)
            self.assertIn("orders", row)
            self.assertIn("revenue_ntd", row)
            self.assertIn("ai_tokens", row)
            self.assertIn("scans", row)

    def test_dashboard_provider_breakdown_sorted_by_tokens(self):
        response = self.client.get(reverse("admin-dashboard"))
        breakdown = response.data["provider_breakdown"]
        providers = [r["provider"] for r in breakdown]
        # minimax 共 7000 tokens > glm 3000 → minimax 應該在前
        self.assertEqual(providers[0], "minimax")
        minimax_tokens = sum(r["tokens"] for r in breakdown if r["provider"] == "minimax")
        self.assertEqual(minimax_tokens, 7000)

    def test_dashboard_top_ai_users_includes_only_users_with_usage(self):
        response = self.client.get(reverse("admin-dashboard"))
        top = response.data["top_ai_users"]
        usernames = [u["username"] for u in top]
        # alice (8000) 應排在 bob (2000) 之前；admin 沒用 AI 不應出現
        self.assertEqual(usernames[0], "alice")
        self.assertIn("bob", usernames)
        self.assertNotIn("admin", usernames)
        self.assertEqual(top[0]["ai_tokens"], 8000)

    def test_dashboard_non_staff_blocked(self):
        normal = _make_user("normal")
        self.client.force_authenticate(normal)
        response = self.client.get(reverse("admin-dashboard"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class UserLoginEventsTests(APITestCase):
    """GET /api/admin/users/<id>/login-events/：最近 50 筆、serializer whitelist。"""

    def setUp(self):
        self.admin = _make_user("admin_le", staff=True)
        self.alice = _make_user("alice_le")

    def test_non_staff_blocked(self):
        self.client.force_authenticate(self.alice)
        response = self.client.get(
            reverse("admin-user-login-events", args=[self.alice.id]),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_returns_latest_events_with_whitelist_fields(self):
        from apps.accounts.models import LoginEvent
        LoginEvent.objects.create(
            user=self.alice,
            method=LoginEvent.Method.PASSWORD,
            ip_address="203.0.113.10",
            user_agent="ArgusTestAgent/1.0",
        )
        LoginEvent.objects.create(
            user=self.alice,
            method=LoginEvent.Method.GOOGLE,
            ip_address=None,
            user_agent="",
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get(
            reverse("admin-user-login-events", args=[self.alice.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        events = response.data["events"]
        self.assertEqual(len(events), 2)
        # 最新在前；whitelist 只含 method/ip/user_agent/created_at（與 label）
        self.assertEqual(events[0]["method"], LoginEvent.Method.GOOGLE)
        self.assertEqual(
            set(events[0].keys()),
            {"method", "method_label", "ip_address", "user_agent", "created_at"},
        )
        self.assertEqual(events[1]["ip_address"], "203.0.113.10")
        self.assertEqual(events[1]["user_agent"], "ArgusTestAgent/1.0")

    def test_unknown_user_returns_404(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("admin-user-login-events", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminSubscriptionTests(APITestCase):
    """後台訂閱調整：grant / cancel 走 billing.services 並寫 AdminAuditLog。"""

    def setUp(self):
        self.admin = _make_user("admin_sub", staff=True)
        self.client.force_authenticate(self.admin)
        self.alice = _make_user("alice_sub")
        from apps.billing.models import SubscriptionPlan
        self.plan = SubscriptionPlan.objects.create(
            code="sub-admin-test",
            name="後台測試方案",
            monthly_price_ntd=299,
            monthly_coins=400,
            features=["每月 400 點"],
            sort_order=99,
        )

    def test_non_staff_blocked(self):
        self.client.force_authenticate(self.alice)
        response = self.client.post(
            reverse("admin-user-subscription", args=[self.alice.id]),
            {"action": "grant", "plan_code": "sub-admin-test", "periods": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_grant_creates_subscription_and_audits(self):
        response = self.client.post(
            reverse("admin-user-subscription", args=[self.alice.id]),
            {"action": "grant", "plan_code": "sub-admin-test", "periods": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        sub = response.data["subscription"]
        self.assertEqual(sub["status"], "active")
        self.assertEqual(sub["periods_remaining"], 1)  # 2 期中已結算首期
        self.assertEqual(sub["plan_code"], "sub-admin-test")
        from apps.billing.models import CoinTransaction, UserSubscription
        self.assertTrue(
            CoinTransaction.objects.filter(
                wallet__user=self.alice,
                kind=CoinTransaction.Kind.SUBSCRIPTION_GRANT,
                amount=400,
            ).exists(),
        )
        self.assertEqual(
            UserSubscription.objects.get(user=self.alice).source,
            UserSubscription.Source.ADMIN_GRANT,
        )
        # 稽核：grant 在 services 內寫入 AdminAuditLog
        log = AdminAuditLog.objects.filter(
            action=AdminAuditLog.Action.SUBSCRIPTION_ADJUST,
            target_user=self.alice,
        ).get()
        self.assertEqual(log.payload["operation"], "grant")
        self.assertEqual(log.payload["periods"], 2)
        self.assertEqual(log.admin_actor, self.admin)

    def test_grant_requires_plan_code(self):
        response = self.client.post(
            reverse("admin-user-subscription", args=[self.alice.id]),
            {"action": "grant", "periods": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_audits_and_returns_state(self):
        self.client.post(
            reverse("admin-user-subscription", args=[self.alice.id]),
            {"action": "grant", "plan_code": "sub-admin-test", "periods": 1},
            format="json",
        )

        response = self.client.post(
            reverse("admin-user-subscription", args=[self.alice.id]),
            {"action": "cancel"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subscription"]["status"], "cancelled")
        log = AdminAuditLog.objects.filter(
            action=AdminAuditLog.Action.SUBSCRIPTION_ADJUST,
            target_user=self.alice,
            payload__operation="cancel",
        ).get()
        self.assertEqual(log.admin_actor, self.admin)

    def test_get_returns_null_without_subscription(self):
        response = self.client.get(
            reverse("admin-user-subscription", args=[self.alice.id])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["subscription"])

    def test_get_returns_current_subscription(self):
        self.client.post(
            reverse("admin-user-subscription", args=[self.alice.id]),
            {"action": "grant", "plan_code": "sub-admin-test", "periods": 2},
            format="json",
        )
        response = self.client.get(
            reverse("admin-user-subscription", args=[self.alice.id])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub = response.data["subscription"]
        self.assertEqual(sub["plan_code"], "sub-admin-test")
        # 開通 2 期後 view 會立即結算首月（贈點入帳），剩餘期數為 1
        self.assertEqual(sub["periods_remaining"], 1)

    def test_cancel_without_subscription_returns_404(self):
        response = self.client.post(
            reverse("admin-user-subscription", args=[self.alice.id]),
            {"action": "cancel"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_subscription_plans_endpoint_lists_plans(self):
        response = self.client.get(reverse("admin-subscription-plans"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [p["code"] for p in response.data["plans"]]
        self.assertIn("sub-admin-test", codes)
        # seed migration 建立的內建方案也應列出
        self.assertIn("sub-lite", codes)
        self.assertIn("sub-pro", codes)
        self.assertIn("sub-team", codes)


class OrderingTests(APITestCase):
    """後台列表的 `ordering` 白名單排序。

    排序必須在資料庫層做：分頁是 server side（PAGE_SIZE=25），若只排當頁
    會讓管理員以為看到的是全域最大／最小的幾筆。
    """

    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.owner = _make_user("owner")
        # 刻意用非時間順序的分數，確保排序結果不是剛好等於預設的 -created_at
        self.low = _make_scan(self.owner, origin="https://low.example", overall_score=10)
        self.high = _make_scan(self.owner, origin="https://high.example", overall_score=90)
        self.mid = _make_scan(self.owner, origin="https://mid.example", overall_score=50)

    def _scores(self, params):
        response = self.client.get(reverse("admin-scans"), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [s["overall_score"] for s in response.data["scans"]]

    def test_default_ordering_is_newest_first(self):
        response = self.client.get(reverse("admin-scans"))
        origins = [s["origin"] for s in response.data["scans"]]
        self.assertEqual(origins[0], "https://mid.example")

    def test_ascending_ordering_by_whitelisted_field(self):
        self.assertEqual(self._scores({"ordering": "overall_score"}), [10, 50, 90])

    def test_descending_ordering_with_minus_prefix(self):
        self.assertEqual(self._scores({"ordering": "-overall_score"}), [90, 50, 10])

    def test_unknown_field_falls_back_to_default_instead_of_erroring(self):
        # 白名單外的欄位不該回 500，也不該讓任意欄位洩漏到 ORM
        response = self.client.get(reverse("admin-scans"), {"ordering": "user__password"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        origins = [s["origin"] for s in response.data["scans"]]
        self.assertEqual(origins[0], "https://mid.example")

    def test_users_ordering_traverses_wallet_relation(self):
        response = self.client.get(reverse("admin-users"), {"ordering": "balance"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balances = [u["balance"] for u in response.data["users"]]
        self.assertEqual(balances, sorted(balances))


class TriageTests(APITestCase):
    """後台首頁的待辦統計。

    首頁的價值在於回答「現在有什麼要處理」，所以這些數字必須正確——
    誤報會讓管理員追不存在的問題，漏報則讓卡住的掃描沒人發現。
    """

    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.owner = _make_user("owner")

    def _triage(self):
        response = self.client.get(reverse("admin-overview"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["triage"]

    def test_recent_queued_scan_is_not_counted_as_stuck(self):
        _make_scan(self.owner, status=ScanJob.Status.QUEUED)
        triage = self._triage()
        self.assertEqual(triage["scans_stuck"], 0)
        self.assertIsNone(triage["scans_stuck_oldest_at"])

    def test_queued_scan_past_threshold_is_stuck(self):
        from datetime import timedelta

        from django.utils import timezone

        scan = _make_scan(self.owner, status=ScanJob.Status.QUEUED)
        # created_at 有 auto_now_add，只能建立後直接改寫
        overdue = timezone.now() - timedelta(minutes=30)
        ScanJob.objects.filter(pk=scan.pk).update(created_at=overdue)

        triage = self._triage()
        self.assertEqual(triage["scans_stuck"], 1)
        self.assertIsNotNone(triage["scans_stuck_oldest_at"])

    def test_in_progress_excludes_queued_and_terminal_states(self):
        _make_scan(self.owner, status=ScanJob.Status.QUEUED)
        _make_scan(self.owner, status=ScanJob.Status.CRAWLING)
        _make_scan(self.owner, status=ScanJob.Status.SCANNING)
        _make_scan(self.owner, status=ScanJob.Status.AGENT_TESTING)
        _make_scan(self.owner, status=ScanJob.Status.COMPLETED)
        _make_scan(self.owner, status=ScanJob.Status.CANCELLED)

        self.assertEqual(self._triage()["scans_in_progress"], 3)

    def test_triage_contract_matches_frontend_usage(self):
        """待辦中心用到的欄位一個都不能少。

        前端 AdminOverviewPage 直接取用這些鍵；少一個不會噴錯，只會靜靜顯示
        undefined，所以用測試把契約鎖住。
        """
        triage = self._triage()
        for key in (
            "scans_stuck",
            "scans_stuck_threshold_min",
            "scans_stuck_oldest_at",
            "scans_failed_today",
            "scans_in_progress",
            "reviews_pending",
            "reports_pending",
            "scans_today",
        ):
            self.assertIn(key, triage, f"triage 缺少 {key}")

    def test_failed_today_counts_only_today(self):
        from datetime import timedelta

        from django.utils import timezone

        today = _make_scan(self.owner, status=ScanJob.Status.FAILED)
        old = _make_scan(self.owner, status=ScanJob.Status.FAILED)
        ScanJob.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=3),
        )
        self.assertEqual(self._triage()["scans_failed_today"], 1)
        self.assertIsNotNone(today.pk)


class UserScansTests(APITestCase):
    """使用者詳情的掃描紀錄，與掃描列表的精確使用者篩選。

    服務的是客服流程：使用者回報「掃描失敗但被扣點」時，要能從使用者一路
    看到他的掃描，而不必切頁再搜一次網址。
    """

    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.alice = _make_user("alice")
        self.bob = _make_user("bob")
        _make_scan(self.alice, origin="https://alice-one.example")
        _make_scan(self.alice, origin="https://alice-two.example")
        _make_scan(self.bob, origin="https://bob.example")

    def test_user_detail_includes_recent_scans_and_total(self):
        response = self.client.get(reverse("admin-user-detail", args=[self.alice.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        origins = [s["origin"] for s in response.data["recent_scans"]]
        self.assertEqual(len(origins), 2)
        self.assertNotIn("https://bob.example", origins)
        self.assertEqual(response.data["scans_total"], 2)

    def test_user_with_no_scans_gets_empty_list_not_missing_key(self):
        carol = _make_user("carol")
        response = self.client.get(reverse("admin-user-detail", args=[carol.id]))
        self.assertEqual(response.data["recent_scans"], [])
        self.assertEqual(response.data["scans_total"], 0)

    def test_scans_list_user_filter_is_exact_not_fuzzy(self):
        response = self.client.get(reverse("admin-scans"), {"user": self.alice.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        origins = [s["origin"] for s in response.data["scans"]]
        self.assertEqual(len(origins), 2)
        self.assertNotIn("https://bob.example", origins)


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class ScanControlTests(APITestCase):
    """管理員的掃描處置：終止與重排。

    重排不重複扣點（2026-09-25 產品決策）。由於失敗／取消的掃描在 tasks.py
    一律已自動退款，重排實際上是免費重跑，因此每次都必須留下稽核軌跡。
    """

    def setUp(self):
        self.admin = _make_user("admin", staff=True)
        self.client.force_authenticate(self.admin)
        self.owner = _make_user("owner")

    def test_cancel_in_progress_scan(self):
        scan = _make_scan(self.owner, status=ScanJob.Status.CRAWLING)
        response = self.client.post(reverse("admin-scan-cancel", args=[scan.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.CANCELLED)

    def test_scan_serializer_exposes_user_id_for_admin_navigation(self):
        """掃描詳情要能跳到使用者頁調整點數，缺 user_id 會讓連結靜默消失。"""
        scan = _make_scan(self.owner, status=ScanJob.Status.COMPLETED)
        response = self.client.get(reverse("admin-scan-detail", args=[scan.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["scan"]["user_id"], self.owner.id)

    def test_cannot_cancel_completed_scan(self):
        scan = _make_scan(self.owner, status=ScanJob.Status.COMPLETED)
        response = self.client.post(reverse("admin-scan-cancel", args=[scan.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.COMPLETED)

    def test_cancel_writes_audit_log(self):
        scan = _make_scan(self.owner, status=ScanJob.Status.QUEUED)
        self.client.post(reverse("admin-scan-cancel", args=[scan.id]))
        log = AdminAuditLog.objects.filter(
            action=AdminAuditLog.Action.SCAN_CONTROL,
        ).latest("created_at")
        self.assertEqual(log.payload["operation"], "cancel")
        self.assertEqual(log.target_user, self.owner)

    def test_requeue_failed_scan_does_not_charge(self):
        scan = _make_scan(self.owner, status=ScanJob.Status.FAILED)
        wallet = CoinWallet.objects.get(user=self.owner)
        before = wallet.balance

        with patch("apps.admin_api.views.run_scan_job.delay") as dispatch:
            response = self.client.post(reverse("admin-scan-requeue", args=[scan.id]))
            dispatch.assert_called_once_with(scan.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["charged"], 0)
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.QUEUED)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, before, "重排不得扣款")

    def test_cannot_requeue_completed_scan(self):
        """completed 可重排等於提供免費的重新掃描，必須擋下。"""
        scan = _make_scan(self.owner, status=ScanJob.Status.COMPLETED)
        response = self.client.post(reverse("admin-scan-requeue", args=[scan.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requeue_restores_status_when_dispatch_fails(self):
        """派工失敗不能把掃描留在假的 queued，否則它會永遠卡住。"""
        scan = _make_scan(self.owner, status=ScanJob.Status.FAILED)
        with patch(
            "apps.admin_api.views.run_scan_job.delay",
            side_effect=RuntimeError("broker down"),
        ):
            response = self.client.post(reverse("admin-scan-requeue", args=[scan.id]))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.FAILED)

    def test_requeue_writes_audit_log_because_it_is_free(self):
        scan = _make_scan(self.owner, status=ScanJob.Status.CANCELLED)
        with patch("apps.admin_api.views.run_scan_job.delay"):
            self.client.post(reverse("admin-scan-requeue", args=[scan.id]))
        log = AdminAuditLog.objects.filter(
            action=AdminAuditLog.Action.SCAN_CONTROL,
        ).latest("created_at")
        self.assertEqual(log.payload["operation"], "requeue")
        self.assertEqual(log.payload["charged"], 0)
