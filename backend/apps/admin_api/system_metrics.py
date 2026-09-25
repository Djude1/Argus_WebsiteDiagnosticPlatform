"""後台系統資訊：CPU／記憶體／磁碟／網路／運行時間。

**為什麼不用 psutil**：後端跑在 K8s pod 裡，`psutil.virtual_memory()` 在容器內
讀到的是**宿主機**的總記憶體，不是 pod 的 limit。拿宿主機的數字當 Argus 的
資源使用率會嚴重誤導——節點有 64G、pod 限 1G 時，顯示「記憶體 8%」等於沒說。

因此這裡優先讀 cgroup v2（`memory.max` / `memory.current` / `cpu.max` /
`cpu.stat`），拿不到才退回 `/proc` 的宿主機數字，並在回應中用 `scope` 明確標示
這組數字是容器的還是宿主機的。不標示就會變成另一種說謊。

全部以純標準庫實作，不新增相依套件。非 Linux 環境（開發用 Windows／macOS）
會回傳 `available: False` 而非拋錯。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return None


def _read_int(path: Path) -> int | None:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _cgroup_v2_available() -> bool:
    return (CGROUP_ROOT / "cgroup.controllers").exists()


# ---------------------------------------------------------------- 記憶體


def read_memory() -> dict:
    """優先回傳容器的記憶體使用；拿不到才退回宿主機。"""
    if _cgroup_v2_available():
        current = _read_int(CGROUP_ROOT / "memory.current")
        raw_max = _read_text(CGROUP_ROOT / "memory.max")
        if current is not None and raw_max is not None and raw_max != "max":
            try:
                limit = int(raw_max)
            except ValueError:
                limit = None
            if limit:
                return {
                    "available": True,
                    "scope": "container",
                    "used_bytes": current,
                    "total_bytes": limit,
                    "percent": round(current / limit * 100, 1),
                }

    # 退回 /proc/meminfo（宿主機視角）
    info = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    info[key] = int(parts[0]) * 1024  # kB → bytes
    except OSError:
        return {"available": False, "reason": "無法讀取 /proc/meminfo"}

    total = info.get("MemTotal")
    avail = info.get("MemAvailable")
    if not total or avail is None:
        return {"available": False, "reason": "meminfo 缺少必要欄位"}
    used = total - avail
    return {
        "available": True,
        "scope": "host",
        "used_bytes": used,
        "total_bytes": total,
        "percent": round(used / total * 100, 1),
    }


# ---------------------------------------------------------------- CPU


def _proc_stat_busy_total() -> tuple[int, int] | None:
    try:
        with open("/proc/stat", encoding="utf-8") as fh:
            line = fh.readline()
    except OSError:
        return None
    if not line.startswith("cpu "):
        return None
    values = [int(v) for v in line.split()[1:]]
    if len(values) < 4:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return total - idle, total


def read_cpu(sample_seconds: float = 0.15) -> dict:
    """CPU 使用率。

    /proc/stat 是累計值，必須取兩次差分。取樣 0.15 秒是刻意的折衷：
    這個端點是給人看的儀表板，不值得為了更平滑的數字讓請求多等半秒。
    也因此數字會有抖動，頁面上會說明它是瞬時取樣。
    """
    first = _proc_stat_busy_total()
    if first is None:
        return {"available": False, "reason": "無法讀取 /proc/stat"}
    time.sleep(sample_seconds)
    second = _proc_stat_busy_total()
    if second is None:
        return {"available": False, "reason": "無法讀取 /proc/stat"}

    busy_delta = second[0] - first[0]
    total_delta = second[1] - first[1]
    percent = round(busy_delta / total_delta * 100, 1) if total_delta > 0 else 0.0

    # cgroup v2 的 cpu.max 格式是 "<quota> <period>"，quota 為 max 表示未設限
    quota_cores = None
    if _cgroup_v2_available():
        raw = _read_text(CGROUP_ROOT / "cpu.max")
        if raw:
            parts = raw.split()
            if len(parts) == 2 and parts[0] != "max":
                try:
                    quota_cores = round(int(parts[0]) / int(parts[1]), 2)
                except (ValueError, ZeroDivisionError):
                    quota_cores = None

    try:
        load1, load5, load15 = os.getloadavg()
    except (OSError, AttributeError):
        load1 = load5 = load15 = None

    return {
        "available": True,
        # 差分來自 /proc/stat，在容器內仍是宿主機的 CPU 時間
        "scope": "host",
        "percent": percent,
        "cores": os.cpu_count(),
        "quota_cores": quota_cores,
        "load_avg": None if load1 is None else {
            "1min": round(load1, 2),
            "5min": round(load5, 2),
            "15min": round(load15, 2),
        },
    }


# ---------------------------------------------------------------- 磁碟


def read_disk(path: str = "/") -> dict:
    """指定掛載點的磁碟使用量。預設看根目錄（容器的可寫層與 media）。"""
    try:
        st = os.statvfs(path)
    except (OSError, AttributeError):
        return {"available": False, "reason": f"無法讀取 {path} 的檔案系統資訊"}
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - free
    if total <= 0:
        return {"available": False, "reason": "檔案系統總容量為 0"}
    return {
        "available": True,
        "path": path,
        "used_bytes": used,
        "total_bytes": total,
        "percent": round(used / total * 100, 1),
    }


# ---------------------------------------------------------------- 網路


def read_network() -> dict:
    """累計收送位元組（排除 loopback）。

    只回累計值不回速率：算速率需要兩次取樣，而這個端點是使用者按一次才打一次，
    沒有穩定的取樣間隔。前端會用兩次輪詢的差分自行算速率。
    """
    try:
        with open("/proc/net/dev", encoding="utf-8") as fh:
            lines = fh.readlines()[2:]
    except OSError:
        return {"available": False, "reason": "無法讀取 /proc/net/dev"}

    rx = tx = 0
    for line in lines:
        name, _, rest = line.partition(":")
        if name.strip() == "lo":
            continue
        parts = rest.split()
        if len(parts) >= 9:
            rx += int(parts[0])
            tx += int(parts[8])
    return {"available": True, "rx_bytes": rx, "tx_bytes": tx}


# ---------------------------------------------------------------- 運行時間


_PROCESS_START = time.time()


def read_uptime() -> dict:
    """同時回傳宿主機開機時間與本 Django 程序的運行時間。

    在 K8s 裡「這個 pod 活多久」比「節點開機多久」有用得多——pod 若頻繁重啟，
    程序運行時間會一直很短，那是個值得注意的訊號。
    """
    host_seconds = None
    raw = _read_text(Path("/proc/uptime"))
    if raw:
        try:
            host_seconds = int(float(raw.split()[0]))
        except (ValueError, IndexError):
            host_seconds = None
    return {
        "available": True,
        "host_seconds": host_seconds,
        "process_seconds": int(time.time() - _PROCESS_START),
    }


# ---------------------------------------------------------------- 匯總


def collect() -> dict:
    """匯總所有指標。任一項失敗只讓該項 available=False，不影響其他項。"""
    return {
        "cpu": read_cpu(),
        "memory": read_memory(),
        "disk": read_disk(),
        "network": read_network(),
        "uptime": read_uptime(),
        "hostname": os.uname().nodename if hasattr(os, "uname") else None,
    }
