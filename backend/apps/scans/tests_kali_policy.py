from __future__ import annotations

import hashlib
import ipaddress
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from apps.scans.cancellation import ScanCancelled
from apps.scans.models import ScanJob
from apps.scans.security.kali_policy import reserve_sqlmap_targets


@override_settings(
    ARGUS_KALI_ENABLED=True,
    ARGUS_KALI_BACKEND="kubernetes",
    ARGUS_KALI_MAX_TARGETS=3,
    ARGUS_KALI_SCAN_DEADLINE_SECONDS=900,
    ARGUS_KALI_STATE_TTL_SECONDS=86400,
)
class KaliPolicyTests(APITestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="kali_policy_user",
            password="safe-test-password",
        )
        self.client.force_authenticate(self.user)
        dns_patch = mock.patch(
            "apps.scans.services._resolve_host_ips",
            return_value=[ipaddress.ip_address("93.184.216.34")],
        )
        dns_patch.start()
        self.addCleanup(dns_patch.stop)

        self.redis = mock.Mock()
        redis_patch = mock.patch(
            "apps.scans.security.kali_policy.get_kali_redis",
            return_value=self.redis,
        )
        self.get_redis = redis_patch.start()
        self.addCleanup(redis_patch.stop)

    def _make_scan(
        self,
        *,
        origin: str = "https://example.com",
        mode: str = ScanJob.ScanMode.ACTIVE,
        authorized: bool = True,
    ) -> ScanJob:
        return ScanJob.objects.create(
            user=self.user,
            original_url=f"{origin}/",
            normalized_url=f"{origin}/",
            origin=origin,
            status=ScanJob.Status.QUEUED,
            scan_mode=mode,
            active_testing_authorized=authorized,
        )

    def test_global_switch_and_backend_are_checked_before_scan_lookup(self):
        with override_settings(ARGUS_KALI_ENABLED=False):
            outcome = reserve_sqlmap_targets(
                999_999,
                ["https://example.com/?id=1"],
                max_count=1,
            )
        self.assertEqual(outcome.blocked_reason, "kali_disabled")

        with override_settings(ARGUS_KALI_BACKEND="disabled"):
            outcome = reserve_sqlmap_targets(
                999_999,
                ["https://example.com/?id=1"],
                max_count=1,
            )
        self.assertEqual(outcome.blocked_reason, "backend_misconfigured")
        self.get_redis.assert_not_called()

    def test_missing_scan_is_rejected_before_redis(self):
        outcome = reserve_sqlmap_targets(
            999_999,
            ["https://example.com/?id=1"],
            max_count=1,
        )

        self.assertEqual(outcome.blocked_reason, "scan_not_found")
        self.get_redis.assert_not_called()

    def test_cancel_is_propagated_before_redis_reservation(self):
        scan = self._make_scan(mode=ScanJob.ScanMode.PASSIVE, authorized=False)
        response = self.client.post(reverse("scan-cancel", kwargs={"pk": scan.pk}))
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.CANCELLED)

        with self.assertRaises(ScanCancelled):
            reserve_sqlmap_targets(
                scan.id,
                ["https://example.com/?id=1"],
                max_count=1,
            )
        self.get_redis.assert_not_called()

    def test_active_mode_is_checked_before_authorization(self):
        passive_scan = self._make_scan(
            mode=ScanJob.ScanMode.PASSIVE,
            authorized=False,
        )
        outcome = reserve_sqlmap_targets(
            passive_scan.id,
            ["https://example.com/?id=1"],
            max_count=1,
        )
        self.assertEqual(outcome.blocked_reason, "scan_mode_not_active")

        active_scan = self._make_scan(authorized=False)
        outcome = reserve_sqlmap_targets(
            active_scan.id,
            ["https://example.com/?id=1"],
            max_count=1,
        )
        self.assertEqual(outcome.blocked_reason, "active_testing_unauthorized")
        self.get_redis.assert_not_called()

    def test_rejects_invalid_private_cross_origin_and_queryless_targets(self):
        scan = self._make_scan()
        cases = (
            ("ftp://example.com/?id=1", "invalid_target_url"),
            ("https://127.0.0.1/?id=1", "target_not_public"),
            ("https://other.example/?id=1", "cross_origin_forbidden"),
            ("https://example.com/products", "no_query_parameter"),
        )

        for target, reason in cases:
            with self.subTest(target=target):
                outcome = reserve_sqlmap_targets(scan.id, [target], max_count=1)
                self.assertEqual(outcome.blocked_reason, reason)
        self.get_redis.assert_not_called()

    def test_reservation_uses_two_scan_keys_and_only_sha256_fingerprints(self):
        scan = self._make_scan()
        urls = [
            "https://example.com/products?id=secret-value",
            "https://example.com/search?q=other-value",
        ]
        normalized = tuple(urls)
        fingerprints = tuple(
            hashlib.sha256(url.encode("utf-8")).hexdigest() for url in normalized
        )
        self.redis.eval.return_value = [0, 1]

        outcome = reserve_sqlmap_targets(scan.id, urls, max_count=2)

        self.assertEqual(
            [(target.index, target.url, target.fingerprint) for target in outcome.targets],
            [
                (0, normalized[0], fingerprints[0]),
                (1, normalized[1], fingerprints[1]),
            ],
        )
        args = self.redis.eval.call_args.args
        self.assertEqual(args[1], 2)
        self.assertEqual(args[2], f"argus:kali:scan:{scan.id}:targets")
        self.assertEqual(args[3], f"argus:kali:scan:{scan.id}:started")
        self.assertEqual(args[4:7], (900, 3, 86400))
        self.assertEqual(args[7:], fingerprints)
        for url in urls:
            self.assertNotIn(url, repr(self.redis.eval.call_args))

    def test_max_count_limits_candidates_before_reservation(self):
        scan = self._make_scan()
        self.redis.eval.return_value = [0]

        outcome = reserve_sqlmap_targets(
            scan.id,
            [
                "https://example.com/?first=1",
                "https://example.com/?second=2",
            ],
            max_count=1,
        )

        self.assertEqual(len(outcome.targets), 1)
        self.assertEqual(outcome.targets[0].index, 0)
        self.assertEqual(len(self.redis.eval.call_args.args[7:]), 1)

    def test_empty_admission_distinguishes_dedupe_from_exhausted_budget(self):
        scan = self._make_scan()
        self.redis.eval.return_value = []
        self.redis.sismember.return_value = True

        outcome = reserve_sqlmap_targets(
            scan.id,
            ["https://example.com/?id=1"],
            max_count=1,
        )
        self.assertEqual(outcome.blocked_reason, "target_already_tested")

        self.redis.reset_mock()
        self.redis.eval.return_value = []
        self.redis.sismember.return_value = False
        outcome = reserve_sqlmap_targets(
            scan.id,
            ["https://example.com/?id=2"],
            max_count=1,
        )
        self.assertEqual(outcome.blocked_reason, "scan_budget_exhausted")

    def test_lua_deadline_sentinel_is_mapped(self):
        scan = self._make_scan()
        self.redis.eval.return_value = [-1]

        outcome = reserve_sqlmap_targets(
            scan.id,
            ["https://example.com/?id=1"],
            max_count=1,
        )

        self.assertEqual(outcome.blocked_reason, "scan_deadline_exceeded")


class GetKaliRedisClientTests(SimpleTestCase):
    @override_settings(ARGUS_KALI_REDIS_URL="redis://kali.example:6379/0")
    def test_from_url_passes_connect_and_socket_timeouts(self):
        from apps.scans.security.kali_policy import get_kali_redis

        with mock.patch(
            "apps.scans.security.kali_policy.Redis.from_url"
        ) as from_url:
            get_kali_redis()

        from_url.assert_called_once_with(
            "redis://kali.example:6379/0",
            socket_connect_timeout=5,
            socket_timeout=5,
        )
