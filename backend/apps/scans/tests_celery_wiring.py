import subprocess
import sys
from io import StringIO
from threading import Event
from unittest.mock import patch

import config
from django.contrib.auth import get_user_model
from django.core import checks
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APITestCase

from apps.billing.models import CoinTransaction, CoinWallet
from apps.scans.models import ScanJob
from apps.scans.tasks import (
    _new_event_loop_with_retry,
    fail_scan_job_before_start,
    reconcile_local_scan_process_exit,
    run_scan_job,
)
from apps.scans.views import (
    _EAGER_SCAN_SLOT,
    ScanJobViewSet,
    _run_eager_scan_in_background,
    _submit_eager_scan,
)


class CeleryWiringTests(SimpleTestCase):
    def test_django_config_loads_project_celery_app(self):
        from config.celery import app as celery_app

        self.assertIs(config.celery_app, celery_app)
        self.assertIs(run_scan_job.app, celery_app)

    def test_scan_viewset_requires_authentication_explicitly(self):
        self.assertEqual(ScanJobViewSet.permission_classes, [IsAuthenticated])

    @override_settings(DEBUG=False, CELERY_TASK_ALWAYS_EAGER=True)
    def test_eager_configuration_is_rejected_outside_debug(self):
        errors = checks.run_checks(include_deployment_checks=True)

        self.assertIn("scans.E001", {error.id for error in errors})

    @patch("apps.scans.tasks.time.sleep")
    @patch("apps.scans.tasks.asyncio.new_event_loop")
    @patch("apps.scans.tasks.sys.platform", "win32")
    def test_windows_event_loop_creation_retries_winerror_10013(
        self,
        new_event_loop,
        sleep,
    ):
        socket_error = PermissionError("socketpair denied")
        socket_error.winerror = 10013
        expected_loop = object()
        new_event_loop.side_effect = [socket_error, expected_loop]

        actual_loop = _new_event_loop_with_retry()

        self.assertIs(actual_loop, expected_loop)
        self.assertEqual(new_event_loop.call_count, 2)
        sleep.assert_called_once_with(0.05)

    @patch("apps.scans.tasks.time.sleep")
    @patch("apps.scans.tasks.asyncio.new_event_loop")
    @patch("apps.scans.tasks.sys.platform", "win32")
    def test_windows_event_loop_creation_does_not_retry_other_permission_errors(
        self,
        new_event_loop,
        sleep,
    ):
        permission_error = PermissionError("different permission failure")
        permission_error.winerror = 5
        new_event_loop.side_effect = permission_error

        with self.assertRaises(PermissionError):
            _new_event_loop_with_retry()

        new_event_loop.assert_called_once()
        sleep.assert_not_called()


@override_settings(
    ARGUS_AUTO_QUEUE_SCANS=True,
    CELERY_TASK_ALWAYS_EAGER=False,
)
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


@override_settings(
    ARGUS_AUTO_QUEUE_SCANS=True,
    CELERY_TASK_ALWAYS_EAGER=True,
    DEBUG=True,
)
class EagerScanDispatchTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eager-dispatch-user",
            email="eager-dispatch@example.com",
            password="safe-test-password",
        )
        CoinWallet.objects.filter(user=self.user).update(balance=200)
        self.client.force_authenticate(self.user)

    @patch("apps.scans.views._submit_eager_scan", return_value=True)
    def test_create_returns_queued_before_eager_scan_runs(self, submit_eager):
        with patch("apps.scans.views.run_scan_job.delay") as delay:
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
        self.assertEqual(response.data["status"], ScanJob.Status.QUEUED)
        scan_job = ScanJob.objects.get(id=response.data["id"])
        delay.assert_not_called()
        submit_eager.assert_called_once_with(scan_job.id)

    @patch("apps.scans.views._EAGER_SCAN_EXECUTOR.submit")
    @patch("apps.scans.views._EAGER_SCAN_SLOT.acquire", return_value=True)
    def test_eager_submit_reserves_single_slot(self, acquire_slot, executor_submit):
        accepted = _submit_eager_scan(23)

        self.assertTrue(accepted)
        acquire_slot.assert_called_once_with(blocking=False)
        executor_submit.assert_called_once()
        self.assertEqual(executor_submit.call_args.args[1], 23)

    @patch("apps.scans.views._EAGER_SCAN_SLOT.release")
    @patch(
        "apps.scans.views._EAGER_SCAN_EXECUTOR.submit",
        side_effect=RuntimeError("private executor failure detail"),
    )
    @patch("apps.scans.views._EAGER_SCAN_SLOT.acquire", return_value=True)
    def test_eager_submit_failure_releases_reserved_slot(
        self,
        _acquire_slot,
        _executor_submit,
        release_slot,
    ):
        with self.assertRaisesRegex(RuntimeError, "private executor failure detail"):
            _submit_eager_scan(31)

        release_slot.assert_called_once()

    @patch("apps.scans.views._submit_eager_scan", return_value=False)
    def test_eager_capacity_full_fails_and_refunds_hold(self, _submit_eager):
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
        scan_job = ScanJob.objects.get()
        self.assertEqual(scan_job.status, ScanJob.Status.FAILED)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 200)
        self.assertEqual(
            list(
                CoinTransaction.objects.filter(scan_job=scan_job)
                .order_by("id")
                .values_list("kind", "amount")
            ),
            [
                (CoinTransaction.Kind.SCAN_HOLD, -10),
                (CoinTransaction.Kind.SCAN_REFUND, 10),
            ],
        )

    @override_settings(DEBUG=False)
    def test_eager_background_is_rejected_outside_debug(self):
        self.assertFalse(_submit_eager_scan(29))

    @patch("apps.scans.views.close_old_connections")
    @patch("apps.scans.views._EAGER_SCAN_SLOT.release")
    @patch("apps.scans.views.connections.close_all")
    @patch("apps.scans.views.reconcile_local_scan_process_exit")
    @patch("apps.scans.views.subprocess.Popen")
    def test_eager_background_uses_child_process_and_releases_slot(
        self,
        popen,
        reconcile_exit,
        close_all,
        release_slot,
        close_connections,
    ):
        popen.return_value.wait.return_value = 0

        _run_eager_scan_in_background(13)

        command = popen.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[-2:], ["13", "--no-color"])
        self.assertIn("run_local_eager_scan", command)
        self.assertTrue(popen.call_args.kwargs["close_fds"])
        self.assertIs(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        popen.return_value.wait.assert_called_once()
        reconcile_exit.assert_not_called()
        close_connections.assert_called_once()
        close_all.assert_called_once()
        release_slot.assert_called_once()

    @patch("apps.scans.views.subprocess.Popen")
    def test_http_response_does_not_wait_for_running_eager_task(self, popen):
        task_started = Event()
        allow_task_to_finish = Event()

        def block_process_wait(*args, **kwargs):
            task_started.set()
            allow_task_to_finish.wait(timeout=5)
            return 0

        popen.return_value.wait.side_effect = block_process_wait
        try:
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
            self.assertEqual(response.data["status"], ScanJob.Status.QUEUED)
            self.assertTrue(task_started.wait(timeout=1))
            self.assertFalse(allow_task_to_finish.is_set())
        finally:
            allow_task_to_finish.set()

        self.assertTrue(_EAGER_SCAN_SLOT.acquire(timeout=2))
        _EAGER_SCAN_SLOT.release()

    @patch("apps.scans.views.close_old_connections")
    @patch("apps.scans.views._EAGER_SCAN_SLOT.release")
    @patch("apps.scans.views.connections.close_all")
    @patch("apps.scans.views.reconcile_local_scan_process_exit")
    @patch("apps.scans.views.subprocess.Popen")
    def test_eager_background_failure_uses_safe_refund_path(
        self,
        popen,
        reconcile_exit,
        close_all,
        release_slot,
        close_connections,
    ):
        popen.return_value.wait.return_value = 1

        _run_eager_scan_in_background(17)

        popen.assert_called_once()
        reconcile_exit.assert_called_once_with(17)
        close_connections.assert_called_once()
        close_all.assert_called_once()
        release_slot.assert_called_once()

    @patch("apps.scans.views._EAGER_SCAN_SLOT.release")
    @patch("apps.scans.views.connections.close_all")
    @patch("apps.scans.views.reconcile_local_scan_process_exit")
    @patch(
        "apps.scans.views.close_old_connections",
        side_effect=RuntimeError("private connection setup failure"),
    )
    def test_connection_setup_failure_still_fails_job_and_releases_slot(
        self,
        _close_connections,
        reconcile_exit,
        close_all,
        release_slot,
    ):
        _run_eager_scan_in_background(37)

        reconcile_exit.assert_called_once_with(37)
        close_all.assert_called_once()
        release_slot.assert_called_once()

    @patch("apps.scans.views._EAGER_SCAN_SLOT.release")
    @patch(
        "apps.scans.views.connections.close_all",
        side_effect=RuntimeError("private connection cleanup failure"),
    )
    @patch("apps.scans.views.subprocess.Popen")
    def test_connection_cleanup_failure_still_releases_slot(
        self,
        popen,
        _close_all,
        release_slot,
    ):
        popen.return_value.wait.return_value = 0

        with self.assertRaisesRegex(RuntimeError, "private connection cleanup failure"):
            _run_eager_scan_in_background(41)

        popen.assert_called_once()
        release_slot.assert_called_once()

    @patch("apps.scans.views._EAGER_SCAN_SLOT.release")
    @patch("apps.scans.views.connections.close_all")
    @patch("apps.scans.views.reconcile_local_scan_process_exit")
    @patch("apps.scans.views._terminate_process_tree")
    @patch("apps.scans.views.subprocess.Popen")
    def test_eager_process_timeout_kills_tree_and_reconciles_scan(
        self,
        popen,
        terminate_tree,
        reconcile_exit,
        _close_all,
        release_slot,
    ):
        process = popen.return_value
        process.wait.side_effect = subprocess.TimeoutExpired("scan", 30)

        _run_eager_scan_in_background(47)

        terminate_tree.assert_called_once_with(process)
        reconcile_exit.assert_called_once_with(47)
        release_slot.assert_called_once()

    @patch("apps.scans.views._EAGER_SCAN_SLOT.release")
    @patch("apps.scans.views.connections.close_all")
    @patch("apps.scans.views.reconcile_local_scan_process_exit")
    @patch("apps.scans.views._terminate_process_tree")
    @patch("apps.scans.views.subprocess.Popen")
    def test_eager_process_wait_error_kills_tree_before_reconciliation(
        self,
        popen,
        terminate_tree,
        reconcile_exit,
        _close_all,
        release_slot,
    ):
        process = popen.return_value
        process.wait.side_effect = OSError("test-only wait failure")

        _run_eager_scan_in_background(53)

        terminate_tree.assert_called_once_with(process)
        reconcile_exit.assert_called_once_with(53)
        release_slot.assert_called_once()

    @patch("apps.scans.views._submit_eager_scan", return_value=True)
    def test_reconcile_local_process_exit_fails_crawling_scan_and_refunds(
        self,
        _submit_eager,
    ):
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
        ScanJob.objects.filter(id=scan_job.id).update(status=ScanJob.Status.CRAWLING)

        self.assertTrue(reconcile_local_scan_process_exit(scan_job.id))

        scan_job.refresh_from_db()
        self.assertEqual(scan_job.status, ScanJob.Status.FAILED)
        self.assertEqual(scan_job.error_message, "本機掃描程序異常結束。")
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 200)
        self.assertFalse(reconcile_local_scan_process_exit(scan_job.id))

    @override_settings(DEBUG=True, CELERY_TASK_ALWAYS_EAGER=True)
    @patch(
        "apps.scans.management.commands.run_local_eager_scan.run_scan_job.apply"
    )
    def test_local_eager_command_runs_task_synchronously(self, apply_task):
        out = StringIO()

        call_command("run_local_eager_scan", 43, stdout=out)

        apply_task.assert_called_once_with(args=(43,), throw=True)
