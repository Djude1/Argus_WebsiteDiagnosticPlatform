"""可回應 ScanJob 合作式取消的外部掃描 process runner。"""

from __future__ import annotations

import os
import signal
import subprocess
import time

from apps.scans.cancellation import ScanCancelled, is_cancelled

_POLL_SECONDS = 1.0
_TERMINATION_GRACE_SECONDS = 1.0


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """終止 process 與其子程序；寬限期後強制 kill 整個程序群組。"""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        else:
            # start_new_session=True 使 PID 同時是固定的 process group id。
            # 即使父程序先退出，仍要對原群組送 SIGKILL，避免後代繼續對外請求。
            process_group_id = process.pid
            os.killpg(process_group_id, signal.SIGTERM)
            grace_deadline = time.monotonic() + _TERMINATION_GRACE_SECONDS
            try:
                process.wait(timeout=_TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            remaining_grace = grace_deadline - time.monotonic()
            if remaining_grace > 0:
                time.sleep(remaining_grace)
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception:
            pass


def run_cancellable_process(
    cmd: list[str],
    *,
    scan_job_id: int,
    timeout: int | float,
) -> subprocess.CompletedProcess[str]:
    """執行外部工具，最多一秒檢查一次取消；timeout/cancel 皆終止 process tree。"""
    if scan_job_id and is_cancelled(scan_job_id):
        raise ScanCancelled()

    group_kwargs = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        errors="replace",
        **group_kwargs,
    )
    deadline = time.monotonic() + float(timeout)

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_process_tree(process)
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
        try:
            stdout, stderr = process.communicate(timeout=min(_POLL_SECONDS, remaining))
            return subprocess.CompletedProcess(
                cmd,
                process.returncode,
                stdout,
                stderr,
            )
        except subprocess.TimeoutExpired:
            if scan_job_id and is_cancelled(scan_job_id):
                _terminate_process_tree(process)
                raise ScanCancelled() from None
