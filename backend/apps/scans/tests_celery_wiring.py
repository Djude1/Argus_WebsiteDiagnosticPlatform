from unittest.mock import patch

import config
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APITestCase

from apps.billing.models import CoinTransaction, CoinWallet
from apps.scans.models import ScanJob
from apps.scans.tasks import fail_scan_job_before_start, run_scan_job
from apps.scans.views import ScanJobViewSet


class CeleryWiringTests(SimpleTestCase):
    def test_django_config_loads_project_celery_app(self):
        from config.celery import app as celery_app

        self.assertIs(config.celery_app, celery_app)
        self.assertIs(run_scan_job.app, celery_app)

    def test_scan_viewset_requires_authentication_explicitly(self):
        self.assertEqual(ScanJobViewSet.permission_classes, [IsAuthenticated])


@override_settings(ARGUS_AUTO_QUEUE_SCANS=True)
class ScanQueueFailureTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="queue-failure-user",
            email="queue-failure@example.com",
            password="safe-test-password",
        )
        CoinWallet.objects.filter(user=self.user).update(balance=200)
        self.client.force_authenticate(self.user)

    @patch(
        "apps.scans.views.run_scan_job.delay",
        side_effect=RuntimeError("private broker failure detail"),
    )
    def test_enqueue_failure_marks_scan_failed_and_refunds_hold(self, _delay):
        response = self.client.post(
            reverse("scan-list"),
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertNotIn("private broker failure detail", str(response.data))

        scan_job = ScanJob.objects.get()
        self.assertEqual(scan_job.status, ScanJob.Status.FAILED)
        self.assertIsNotNone(scan_job.completed_at)
        self.assertEqual(scan_job.error_message, "掃描任務排程失敗。")

        wallet = CoinWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 200)
        transactions = list(
            CoinTransaction.objects.filter(scan_job=scan_job)
            .order_by("id")
            .values_list("kind", "amount")
        )
        self.assertEqual(
            transactions,
            [
                (CoinTransaction.Kind.SCAN_HOLD, -10),
                (CoinTransaction.Kind.SCAN_REFUND, 10),
            ],
        )
        self.assertFalse(fail_scan_job_before_start(scan_job.id))
        self.assertEqual(
            CoinTransaction.objects.filter(scan_job=scan_job).count(),
            2,
        )

    @patch("apps.scans.views.run_scan_job.delay")
    def test_enqueue_unknown_result_does_not_claim_refund(self, delay):
        def accepted_then_disconnected(scan_job_id):
            ScanJob.objects.filter(id=scan_job_id).update(
                status=ScanJob.Status.CRAWLING,
            )
            raise RuntimeError("private broker failure detail")

        delay.side_effect = accepted_then_disconnected
        response = self.client.post(
            reverse("scan-list"),
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], ScanJob.Status.CRAWLING)
        self.assertNotIn("private broker failure detail", str(response.data))
        scan_job = ScanJob.objects.get()
        self.assertEqual(
            list(
                CoinTransaction.objects.filter(scan_job=scan_job).values_list(
                    "kind", "amount"
                )
            ),
            [(CoinTransaction.Kind.SCAN_HOLD, -10)],
        )
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 190)

    @patch("apps.scans.views.run_scan_job.delay")
    def test_worker_failure_does_not_persist_raw_exception(self, delay):
        delay.return_value = None
        response = self.client.post(
            reverse("scan-list"),
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 1,
            },
            format="json",
        )
        scan_job = ScanJob.objects.get(id=response.data["id"])
        private_marker = "private-runtime-secret-marker"

        with patch(
            "apps.scans.tasks.assert_public_http_url",
            side_effect=RuntimeError(private_marker),
        ):
            with self.assertRaisesRegex(RuntimeError, "^掃描執行失敗。$") as raised:
                run_scan_job.run(scan_job.id)

        self.assertNotIn(private_marker, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        scan_job.refresh_from_db()
        self.assertEqual(scan_job.status, ScanJob.Status.FAILED)
        self.assertEqual(scan_job.error_message, "掃描執行失敗。")
        self.assertNotIn(private_marker, str(scan_job.scan_log))
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 200)
