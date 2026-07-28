"""外部掃描 process 的取消與 timeout 測試。"""

import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from apps.scans.cancellation import ScanCancelled
from apps.scans.process_runner import _terminate_process_tree, run_cancellable_process


class CancellableProcessTests(SimpleTestCase):
    def test_posix_termination_escalates_entire_original_process_group(self):
        process = mock.Mock(pid=123, returncode=None)

        with (
            mock.patch("apps.scans.process_runner.os.name", "posix"),
            mock.patch(
                "apps.scans.process_runner.os.killpg",
                create=True,
            ) as kill_group,
            mock.patch(
                "apps.scans.process_runner.signal.SIGKILL",
                9,
                create=True,
            ),
            mock.patch(
                "apps.scans.process_runner.time.monotonic",
                side_effect=[0.0, 1.0],
            ),
        ):
            _terminate_process_tree(process)

        self.assertEqual(
            kill_group.call_args_list,
            [
                mock.call(123, signal.SIGTERM),
                mock.call(123, 9),
            ],
        )

    def test_cancelled_scan_terminates_process_tree_and_raises(self):
        process = mock.Mock(pid=123, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired("tool", 0.5)

        with (
            mock.patch("apps.scans.process_runner.subprocess.Popen", return_value=process),
            mock.patch(
                "apps.scans.process_runner.is_cancelled",
                side_effect=[False, True],
            ),
            mock.patch("apps.scans.process_runner._terminate_process_tree") as terminate,
        ):
            with self.assertRaises(ScanCancelled):
                run_cancellable_process(["tool"], scan_job_id=7, timeout=30)

        terminate.assert_called_once_with(process)

    def test_completed_process_returns_captured_output(self):
        process = mock.Mock(pid=123, returncode=0)
        process.communicate.return_value = ("ok", "")

        with (
            mock.patch("apps.scans.process_runner.subprocess.Popen", return_value=process),
            mock.patch("apps.scans.process_runner.is_cancelled", return_value=False),
        ):
            result = run_cancellable_process(["tool"], scan_job_id=7, timeout=30)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")

    def test_timeout_terminates_process_tree(self):
        process = mock.Mock(pid=123, returncode=None)

        with (
            mock.patch("apps.scans.process_runner.subprocess.Popen", return_value=process),
            mock.patch("apps.scans.process_runner.is_cancelled", return_value=False),
            mock.patch(
                "apps.scans.process_runner.time.monotonic",
                side_effect=[0.0, 31.0],
            ),
            mock.patch("apps.scans.process_runner._terminate_process_tree") as terminate,
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                run_cancellable_process(["tool"], scan_job_id=7, timeout=30)

        terminate.assert_called_once_with(process)

    @unittest.skipUnless(
        sys.platform.startswith("linux"),
        "Linux 才能驗證 /proc 與 POSIX process group",
    )
    def test_linux_cancel_kills_descendant_that_ignores_sigterm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            child_pid_path = Path(temp_dir) / "child.pid"
            child_code = (
                "import signal,time;"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
                "time.sleep(60)"
            )
            parent_code = (
                "import signal,subprocess,sys,time;"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
                f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
                f"open({str(child_pid_path)!r},'w').write(str(child.pid));"
                "time.sleep(60)"
            )

            with mock.patch(
                "apps.scans.process_runner.is_cancelled",
                side_effect=[False, True],
            ):
                with self.assertRaises(ScanCancelled):
                    run_cancellable_process(
                        [sys.executable, "-c", parent_code],
                        scan_job_id=7,
                        timeout=30,
                    )

            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            proc_stat_path = Path(f"/proc/{child_pid}/stat")
            deadline = time.monotonic() + 2
            while proc_stat_path.exists() and time.monotonic() < deadline:
                state = proc_stat_path.read_text(encoding="utf-8").split()[2]
                if state == "Z":
                    break
                time.sleep(0.05)

            if proc_stat_path.exists():
                state = proc_stat_path.read_text(encoding="utf-8").split()[2]
                self.assertEqual(state, "Z")
