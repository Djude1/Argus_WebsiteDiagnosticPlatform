from __future__ import annotations

import hashlib
import ipaddress
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings

from apps.scans.models import ScanJob
from apps.scans.security.kali_policy import get_kali_redis, reserve_sqlmap_targets

KALI_TEST_REDIS_URL = os.getenv("KALI_TEST_REDIS_URL")


@skipUnless(KALI_TEST_REDIS_URL, "需要隔離 Redis test DB")
@override_settings(
    ARGUS_KALI_ENABLED=True,
    ARGUS_KALI_BACKEND="kubernetes",
    ARGUS_KALI_MAX_TARGETS=3,
)
class KaliPolicyRedisRaceTests(TransactionTestCase):
    def setUp(self) -> None:
        self.redis_settings = override_settings(
            ARGUS_KALI_REDIS_URL=KALI_TEST_REDIS_URL,
        )
        self.redis_settings.enable()
        self.redis = get_kali_redis()
        selected_db = int(self.redis.connection_pool.connection_kwargs.get("db", 0))
        if selected_db == 0:
            raise AssertionError("KALI_TEST_REDIS_URL 必須指定非 0 的隔離 Redis DB")
        self.redis.flushdb()

        self.user = get_user_model().objects.create_user(
            username="kali_policy_race_user",
            password="safe-test-password",
        )
        self.scan = ScanJob.objects.create(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
            status=ScanJob.Status.QUEUED,
            scan_mode=ScanJob.ScanMode.ACTIVE,
            active_testing_authorized=True,
        )
        self.dns_patch = mock.patch(
            "apps.scans.services._resolve_host_ips",
            return_value=[ipaddress.ip_address("93.184.216.34")],
        )
        self.dns_patch.start()

    def tearDown(self) -> None:
        self.dns_patch.stop()
        self.redis.flushdb()
        self.redis.close()
        self.redis_settings.disable()
        super().tearDown()

    def _reserve_after_barrier(self, barrier: threading.Barrier):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return reserve_sqlmap_targets(
                self.scan.id,
                ["https://example.com/?id=shared-value"],
                max_count=1,
            )
        finally:
            close_old_connections()

    def test_two_workers_reserve_same_target_once(self):
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self._reserve_after_barrier, barrier)
                for _ in range(2)
            ]
        outcomes = [item.result() for item in futures]

        allowed = sum(bool(outcome.targets) for outcome in outcomes)
        self.assertEqual(allowed, 1)
        self.assertCountEqual(
            [outcome.blocked_reason for outcome in outcomes],
            ["", "target_already_tested"],
        )
        fingerprint = hashlib.sha256(
            b"https://example.com/?id=shared-value"
        ).hexdigest()
        key = f"argus:kali:scan:{self.scan.id}:targets"
        self.assertEqual(self.redis.smembers(key), {fingerprint.encode("ascii")})
