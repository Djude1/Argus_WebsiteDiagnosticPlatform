from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import CoinTransaction
from apps.billing.services import purchase_plan
from apps.reviews.models import PlatformReview
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
        # 新欄位：last_message_is_user 為 True 表示等待 admin 回覆
        self.assertTrue(response.data["reviews"][0]["last_message_is_user"])
        self.assertFalse(response.data["reviews"][0]["has_admin_reply"])

    def test_reply_creates_admin_review_message(self):
        from apps.reviews.models import ReviewMessage
        response = self.client.post(
            reverse("admin-reply-review", args=[self.review.id]),
            {"reply": "謝謝你的回饋！"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        msg = ReviewMessage.objects.get(review=self.review)
        self.assertTrue(msg.is_admin)
        self.assertEqual(msg.author, self.admin)
        self.assertEqual(msg.body, "謝謝你的回饋！")

    def test_reply_can_also_override_rating(self):
        response = self.client.post(
            reverse("admin-reply-review", args=[self.review.id]),
            {"reply": "已協助處理", "rating": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 5)

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
