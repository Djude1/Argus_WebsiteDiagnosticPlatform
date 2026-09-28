"""MCP 接入：協定、每次呼叫的權益檢查、工具沿用既有的授權／計費／退款路徑、管理 API。"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import signing
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import CoinTransaction, SubscriptionPlan, UserSubscription
from apps.billing.services import get_or_create_wallet, grant_subscription, settle_subscription
from apps.mcp_access.keys import create_api_key
from apps.mcp_access.models import McpApiKey, McpCallLog
from apps.mcp_access.tools import REPORT_LINK_SALT
from apps.scans.models import ScanJob

User = get_user_model()
URL = "/api/mcp/"


def subscribe(user, code="sub-pro"):
    grant_subscription(user, SubscriptionPlan.objects.get(code=code), 1, source="admin_grant")
    settle_subscription(user)


class McpTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mcp-user", email="mcp-user@example.com", password="safe-test-password"
        )
        subscribe(self.user)
        self.key, self.raw = create_api_key(self.user, "test")

    def rpc(self, method, params=None, *, msg_id=1, key=None, **headers):
        body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if msg_id is not None:
            body["id"] = msg_id
        auth = key if key is not None else self.raw
        if auth:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {auth}"
        return self.client.post(URL, data=json.dumps(body), content_type="application/json",
                                **headers)

    def call(self, tool, arguments=None):
        response = self.rpc("tools/call", {"name": tool, "arguments": arguments or {}})
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()["result"]
        return result, result["content"][0]["text"]


class ProtocolTests(McpTestBase):
    def test_initialize_negotiates_version_and_logs_client(self):
        response = self.rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "claude-code", "version": "2.1.0"},
        })
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "argus")
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.last_used_at)
        self.assertEqual(self.key.last_client, "claude-code 2.1.0")
        log = McpCallLog.objects.get(method="initialize")
        self.assertFalse(log.counted)

    def test_unknown_version_falls_back_to_latest(self):
        result = self.rpc("initialize", {"protocolVersion": "1999-01-01"}).json()["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_notification_returns_202(self):
        response = self.rpc("notifications/initialized", msg_id=None)
        self.assertEqual(response.status_code, 202)

    def test_tools_list_is_free_and_complete(self):
        tools = self.rpc("tools/list").json()["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertTrue({"create_scan", "get_scan", "get_scan_report", "cancel_scan",
                         "list_verified_domains", "estimate_scan"} <= names)
        create = next(t for t in tools if t["name"] == "create_scan")
        self.assertIn("confirm_authorization", create["inputSchema"]["required"])
        self.assertFalse(create["annotations"]["readOnlyHint"])
        self.assertEqual(McpCallLog.objects.filter(counted=True).count(), 0)

    def test_unknown_method_and_tool(self):
        self.assertEqual(self.rpc("resources/list").json()["error"]["code"], -32601)
        response = self.rpc("tools/call", {"name": "drop_database"})
        self.assertEqual(response.json()["error"]["code"], -32602)

    def test_get_is_not_allowed(self):
        response = self.client.get(URL, HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "POST")

    def test_invalid_json(self):
        response = self.client.post(URL, data="{nope", content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32700)

    def test_foreign_origin_rejected(self):
        response = self.rpc("ping", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, 403)

    def test_unsupported_protocol_header_rejected(self):
        response = self.rpc("ping", HTTP_MCP_PROTOCOL_VERSION="1999-01-01")
        self.assertEqual(response.status_code, 400)

    def test_batch(self):
        body = [
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ]
        response = self.client.post(URL, data=json.dumps(body), content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.json(), [{"jsonrpc": "2.0", "id": 1, "result": {}}])


class EntitlementTests(McpTestBase):
    def test_missing_or_invalid_key_is_401(self):
        response = self.rpc("ping", key="")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Bearer", response["WWW-Authenticate"])
        self.assertEqual(self.rpc("ping", key="argus_mcp_wrong").status_code, 401)

    def test_jwt_or_session_is_not_accepted(self):
        self.client.force_login(self.user)
        self.assertEqual(self.rpc("ping", key="").status_code, 401)

    def test_revoked_key_is_rejected_immediately(self):
        self.key.revoked_at = timezone.now()
        self.key.save()
        self.assertEqual(self.rpc("ping").status_code, 401)

    def test_no_subscription_is_403(self):
        other = User.objects.create_user(username="nosub", password="safe-test-password")
        _, raw = create_api_key(other, "k")
        response = self.rpc("initialize", key=raw)
        self.assertEqual(response.status_code, 403)
        self.assertIn("訂閱", response.json()["error"]["message"])

    def test_expired_subscription_is_checked_on_every_call(self):
        self.assertEqual(self.rpc("ping").status_code, 200)
        UserSubscription.objects.filter(user=self.user).update(
            status=UserSubscription.Status.EXPIRED,
            current_period_end=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(self.rpc("ping").status_code, 403)

    def test_cancelled_subscription_keeps_access_until_period_end(self):
        UserSubscription.objects.filter(user=self.user).update(
            status=UserSubscription.Status.CANCELLED, cancelled_at=timezone.now()
        )
        self.assertEqual(self.rpc("ping").status_code, 200)

    def test_inactive_user_rejected(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.rpc("ping").status_code, 403)

    @override_settings(ARGUS_MCP_PLAN_QUOTAS={"sub-pro": 2})
    def test_monthly_quota(self):
        self.call("get_account_status")
        result, _ = self.call("list_scans")
        self.assertFalse(result["isError"])
        result, text = self.call("list_scans")
        self.assertTrue(result["isError"])
        self.assertIn("額度", text)
        self.assertEqual(McpCallLog.objects.filter(counted=True).count(), 2)
        self.assertTrue(McpCallLog.objects.filter(outcome="quota_exceeded").exists())

    @override_settings(ARGUS_MCP_RATE_PER_MINUTE=1)
    def test_request_level_limit_covers_non_tool_methods(self):
        from django.core.cache import cache

        cache.clear()
        statuses = [self.rpc("ping").status_code for _ in range(5)]
        self.assertEqual(statuses[:4], [200] * 4)
        self.assertEqual(statuses[4], 429)

    @override_settings(ARGUS_MCP_RATE_PER_MINUTE=1)
    def test_rate_limit(self):
        from django.core.cache import cache

        cache.clear()
        self.assertFalse(self.call("list_scans")[0]["isError"])
        result, text = self.call("list_scans")
        self.assertTrue(result["isError"])
        self.assertIn("頻繁", text)


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class ToolTests(McpTestBase):
    def create(self, **kw):
        args = {"url": "https://example.com/", "confirm_authorization": True,
                "max_pages": 3, "categories": ["seo", "security"]}
        args.update(kw)
        with mock.patch("apps.scans.serializers.assert_public_http_url",
                        side_effect=lambda u: u):
            return self.call("create_scan", args)

    def test_create_scan_requires_consent(self):
        result, text = self.create(confirm_authorization=False)
        self.assertTrue(result["isError"])
        self.assertIn("confirm_authorization", text)
        self.assertEqual(ScanJob.objects.count(), 0)

    def test_create_scan_holds_coins_and_records_consent(self):
        before = get_or_create_wallet(self.user).balance
        result, _ = self.create()
        self.assertFalse(result["isError"])
        data = result["structuredContent"]
        scan = ScanJob.objects.get(id=data["scan_id"])
        self.assertEqual(scan.user, self.user)
        self.assertEqual(scan.categories, ["seo", "security"])
        self.assertEqual(get_or_create_wallet(self.user).balance, before - 3 * 2 * 2)
        self.assertTrue(CoinTransaction.objects.filter(scan_job=scan, kind="scan_hold").exists())
        self.assertEqual(scan.authorization_consent.authorized_domain, "example.com")
        log = McpCallLog.objects.get(tool="create_scan", counted=True)
        self.assertEqual(log.scan_job, scan)

    def test_active_scan_requires_verified_domain(self):
        result, text = self.create(scan_mode="active")
        self.assertTrue(result["isError"])
        self.assertIn("網域所有權驗證", text)

    def test_insufficient_coin(self):
        wallet = get_or_create_wallet(self.user)
        wallet.balance = 1
        wallet.save()  # 測試資料準備；正式流程一律走 billing.services
        result, text = self.create()
        self.assertTrue(result["isError"])
        self.assertIn("coin 不足", text)

    @override_settings(ARGUS_AUTO_QUEUE_SCANS=True, CELERY_TASK_ALWAYS_EAGER=False)
    def test_dispatch_failure_marks_failed_and_refunds(self):
        before = get_or_create_wallet(self.user).balance
        with mock.patch("apps.scans.views.run_scan_job.delay", side_effect=OSError("broker")):
            result, text = self.create()
        self.assertTrue(result["isError"])
        self.assertIn("退回", text)
        scan = ScanJob.objects.get()
        self.assertEqual(scan.status, ScanJob.Status.FAILED)
        self.assertEqual(get_or_create_wallet(self.user).balance, before)

    def test_cancel_scan_refunds_in_full(self):
        before = get_or_create_wallet(self.user).balance
        scan_id = self.create()[0]["structuredContent"]["scan_id"]
        result, _ = self.call("cancel_scan", {"scan_id": scan_id})
        self.assertFalse(result["isError"])
        self.assertEqual(ScanJob.objects.get(id=scan_id).status, ScanJob.Status.CANCELLED)
        self.assertEqual(get_or_create_wallet(self.user).balance, before)
        result, text = self.call("cancel_scan", {"scan_id": scan_id})
        self.assertTrue(result["isError"])

    def test_cannot_see_other_users_scans(self):
        other = User.objects.create_user(username="other", password="safe-test-password")
        scan = ScanJob.objects.create(
            user=other, original_url="https://x.com/", normalized_url="https://x.com/",
            origin="https://x.com", status=ScanJob.Status.COMPLETED,
        )
        for tool in ("get_scan", "get_scan_findings", "get_scan_report", "cancel_scan"):
            result, text = self.call(tool, {"scan_id": scan.id})
            self.assertTrue(result["isError"], tool)
            self.assertIn("找不到", text)
        self.assertEqual(self.call("list_scans")[0]["structuredContent"]["scans"], [])

    def test_get_scan_progress_percent(self):
        scan = ScanJob.objects.create(
            user=self.user, original_url="https://e.com/", normalized_url="https://e.com/",
            origin="https://e.com", status=ScanJob.Status.SCANNING,
            progress={"phase": "scanning", "steps": ["crawl", "analyze_seo", "scoring"],
                      "step": "analyze_seo", "step_done": 1, "step_total": 2},
        )
        data = self.call("get_scan", {"scan_id": scan.id})[0]["structuredContent"]
        self.assertEqual(data["progress"]["overall_percent"], 50)

    def test_estimate_scan(self):
        data = self.call("estimate_scan", {"max_pages": 4, "categories": ["geo"]})[0]
        self.assertEqual(data["structuredContent"]["estimated_max_cost"], 8)
        result, text = self.call("estimate_scan", {"categories": ["nope"]})
        self.assertTrue(result["isError"])


class ReportLinkTests(McpTestBase):
    def setUp(self):
        super().setUp()
        self.scan = ScanJob.objects.create(
            user=self.user, original_url="https://e.com/", normalized_url="https://e.com/",
            origin="https://e.com", status=ScanJob.Status.COMPLETED,
        )

    def test_report_link_downloads_and_rejects_tampering(self):
        data = self.call("get_scan_report", {"scan_id": self.scan.id})[0]["structuredContent"]
        self.assertTrue(data["report_number"].startswith("ARGUS-"))
        path = data["download_url"].replace("http://testserver", "")
        with mock.patch("apps.scans.views.ensure_report_file") as ensure, \
                mock.patch("apps.scans.views.report_file_response",
                           return_value=HttpResponse(b"docx")):
            self.assertEqual(self.client.get(path).status_code, 200)
            ensure.assert_called_once()
        self.assertEqual(self.client.get(path[:-2] + "x/").status_code, 404)

    def test_link_for_other_user_is_invalid(self):
        token = signing.TimestampSigner(salt=REPORT_LINK_SALT).sign(f"{self.scan.id}:999")
        self.assertEqual(self.client.get(f"/api/mcp/reports/{token}/").status_code, 404)

    def test_incomplete_scan_has_no_report(self):
        self.scan.status = ScanJob.Status.SCANNING
        self.scan.save()
        result, _ = self.call("get_scan_report", {"scan_id": self.scan.id})
        self.assertTrue(result["isError"])


class ManagementApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="web-user", password="safe-test-password")
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_non_subscriber_sees_locked_overview_and_cannot_create_key(self):
        data = self.api.get("/api/mcp-access/overview/").json()
        self.assertFalse(data["entitlement"]["allowed"])
        self.assertEqual(data["endpoint_url"], "http://testserver/api/mcp/")
        self.assertEqual(self.api.post("/api/mcp-access/keys/", {"name": "x"}).status_code, 403)

    @override_settings(ARGUS_MCP_PUBLIC_BASE_URL="https://argus.example.com")
    def test_public_base_url_override(self):
        data = self.api.get("/api/mcp-access/overview/").json()
        self.assertEqual(data["endpoint_url"], "https://argus.example.com/api/mcp/")

    @override_settings(ARGUS_MCP_MAX_KEYS=2)
    def test_create_list_revoke(self):
        subscribe(self.user)
        response = self.api.post("/api/mcp-access/keys/", {"name": "Claude Code"})
        self.assertEqual(response.status_code, 201)
        secret = response.json()["secret"]
        self.assertTrue(secret.startswith("argus_mcp_"))
        stored = McpApiKey.objects.get(user=self.user)
        self.assertNotIn(secret, stored.key_hash)
        self.api.post("/api/mcp-access/keys/", {"name": "Codex"})
        self.assertEqual(self.api.post("/api/mcp-access/keys/", {"name": "3"}).status_code, 409)
        overview = self.api.get("/api/mcp-access/overview/").json()
        self.assertEqual(len(overview["keys"]), 2)
        self.assertNotIn("secret", json.dumps(overview))
        revoke = self.api.post(f"/api/mcp-access/keys/{stored.id}/revoke/")
        self.assertFalse(revoke.json()["key"]["is_active"])
        # 撤銷後可再建立
        self.assertEqual(self.api.post("/api/mcp-access/keys/", {"name": "3"}).status_code, 201)

    def test_cannot_revoke_others_key(self):
        other = User.objects.create_user(username="o2", password="safe-test-password")
        key, _ = create_api_key(other, "x")
        self.assertEqual(self.api.post(f"/api/mcp-access/keys/{key.id}/revoke/").status_code, 404)

    def test_connection_check(self):
        subscribe(self.user)
        key, raw = create_api_key(self.user, "x")
        since = timezone.now().isoformat()
        data = self.api.get("/api/mcp-access/connection/", {"since": since}).json()
        self.assertFalse(data["connected"])
        self.client.post(URL, data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        }), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        data = self.api.get("/api/mcp-access/connection/",
                            {"since": since, "key_id": key.id}).json()
        self.assertTrue(data["connected"])
        self.assertFalse(data["tool_called"])
