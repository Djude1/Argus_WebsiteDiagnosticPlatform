# start_multi_device.py
# -*- coding: utf-8 -*-
"""
多裝置啟動器：同時啟動多個 FastAPI instance，每台裝置各自獨立。

用法：
    uv run python start_multi_device.py              # 啟動 4 台（預設）
    uv run python start_multi_device.py --count 2    # 只啟動 2 台
    uv run python start_multi_device.py --base-port 8081  # 指定起始 port

每個 instance 會得到不同的 SERVER_PORT 和 UDP_PORT，其餘設定共用 .env。
按 Ctrl+C 可一次關閉所有裝置。
"""

import os
import sys
import signal
import subprocess
import argparse
import time
import socket
import urllib.request

# 專案根目錄（此腳本所在位置）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description="AI 智慧眼鏡 — 多裝置啟動器")
    parser.add_argument(
        "--count", type=int, default=4,
        help="要啟動的裝置數量（預設 4）",
    )
    parser.add_argument(
        "--base-port", type=int, default=8081,
        help="起始 port（預設 8081，依序 8081/8082/8083/8084）",
    )
    parser.add_argument(
        "--base-udp-port", type=int, default=12345,
        help="起始 UDP port（IMU 接收，預設 12345，依序遞增）",
    )
    parser.add_argument(
        "--model-server", action="store_true", default=True,
        help="啟動共用模型伺服器（預設開啟，可用 --no-model-server 關閉）",
    )
    parser.add_argument(
        "--no-model-server", dest="model_server", action="store_false",
        help="不使用共用模型伺服器（每台各自載入模型，需要更多 VRAM）",
    )
    parser.add_argument(
        "--model-server-port", type=int, default=9099,
        help="共用模型伺服器 port（預設 9099）",
    )
    args = parser.parse_args()

    count            = args.count
    base_port        = args.base_port
    base_udp         = args.base_udp_port
    use_model_server = args.model_server
    ms_port          = args.model_server_port

    print("=" * 56)
    print(f"  AI 智慧眼鏡 — 多裝置啟動器（{count} 台）")
    if use_model_server:
        print(f"  模式：共用模型伺服器（port {ms_port}）")
    else:
        print(f"  模式：各自載入模型（需要較多 VRAM）")
    print("=" * 56)

    # 已停止的假 process 佔位符（冷卻期間使用，避免立即重啟）
    class _StoppedStub:
        pid = 0
        def poll(self): return 0
        def terminate(self): pass
        def wait(self, **kw): pass
        def kill(self): pass

    processes: list[subprocess.Popen] = []
    last_restart: list[float] = []
    RESTART_COOLDOWN = 10.0

    # ── 啟動共用模型伺服器 ──────────────────────────────────────────────────────
    ms_proc = None
    if use_model_server:
        print(f"\n[ModelServer] 啟動共用模型伺服器...")
        ms_env = os.environ.copy()
        ms_env["MODEL_SERVER_PORT"] = str(ms_port)
        ms_proc = subprocess.Popen(
            [sys.executable, "model_server.py"],
            cwd=_PROJECT_ROOT,
            env=ms_env,
        )
        print(f"[ModelServer] PID={ms_proc.pid}，等待模型載入就緒（最多 180 秒）...")

        # 輪詢 TCP port，直到 model_server 開始監聽
        deadline = time.time() + 180
        ready = False
        while time.time() < deadline:
            if ms_proc.poll() is not None:
                print("[ModelServer] 意外退出，改用本機模式")
                use_model_server = False
                break
            try:
                s = socket.create_connection(("127.0.0.1", ms_port), timeout=1)
                s.close()
                ready = True
                break
            except OSError:
                pass
            time.sleep(2)

        if ready:
            print(f"[ModelServer] 就緒！所有裝置將共用 port {ms_port} 的模型推論")
        elif use_model_server:
            print(f"[ModelServer] 180 秒內未就緒，改用本機模式（各自載入模型）")
            use_model_server = False

    # ── 啟動各裝置 FastAPI instance ───────────────────────────────────────────
    for i in range(count):
        device_num = i + 1
        port       = base_port + i
        udp_port   = base_udp + i

        env = os.environ.copy()
        env["SERVER_PORT"] = str(port)
        env["UDP_PORT"]    = str(udp_port)
        env["DEVICE_ID"]   = f"glasses_{device_num:02d}"
        if use_model_server:
            env["MODEL_SERVER_PORT"] = str(ms_port)

        print(f"\n[裝置 {device_num}] 啟動中... port={port}, udp={udp_port}")

        proc = subprocess.Popen(
            [sys.executable, "app_main.py"],
            cwd=_PROJECT_ROOT,
            env=env,
        )
        processes.append(proc)
        last_restart.append(time.time())
        print(f"[裝置 {device_num}] PID={proc.pid}, http://localhost:{port}")

        # 共用模型伺服器模式：不需等待 VRAM 釋放，但稍微錯開啟動避免同時連線 model_server
        if use_model_server:
            if i < count - 1:
                time.sleep(2)
        else:
            # 本機模式：等健康檢查通過，確保 GPU 模型完全載入再啟動下一台
            if i < count - 1:
                print(f"  等待裝置 {device_num} 健康檢查通過（最多 120 秒）...")
                deadline = time.time() + 120
                ready = False
                while time.time() < deadline:
                    try:
                        with urllib.request.urlopen(
                            f"http://localhost:{port}/api/health", timeout=3
                        ) as resp:
                            if resp.status == 200:
                                ready = True
                                break
                    except Exception:
                        pass
                    time.sleep(3)
                if ready:
                    print(f"  裝置 {device_num} 就緒，啟動下一台...")
                else:
                    print(f"  裝置 {device_num} 120 秒未就緒，仍繼續...")

    print("\n" + "=" * 56)
    print(f"  全部 {count} 台裝置已啟動")
    print(f"  port 範圍：{base_port} ~ {base_port + count - 1}")
    print(f"  按 Ctrl+C 關閉所有裝置")
    print("=" * 56 + "\n")

    # 等待所有 process，任一結束或 Ctrl+C 時關閉全部
    def shutdown(signum=None, frame=None):
        print("\n[啟動器] 正在關閉所有裝置...")
        for i, proc in enumerate(processes):
            if proc.poll() is None:  # 仍在運行
                print(f"  關閉裝置 {i + 1} (PID={proc.pid})...")
                proc.terminate()
        if ms_proc is not None and ms_proc.poll() is None:
            print(f"  關閉模型伺服器 (PID={ms_proc.pid})...")
            ms_proc.terminate()
        # 等待最多 5 秒讓 process 優雅退出
        deadline = time.time() + 5
        for proc in processes:
            remaining = max(0.1, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("[啟動器] 所有裝置已關閉。")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Windows 不支援 SIGTERM 的 signal handler，用 try/except 補
    try:
        while True:
            # 每秒檢查是否有 process 意外退出
            for i, proc in enumerate(processes):
                ret = proc.poll()
                if ret is not None:
                    print(f"\n[警告] 裝置 {i + 1} 意外退出（return code={ret}）")
                    # 冷卻時間內不重啟，避免 VRAM 爆炸等問題導致無限重啟
                    if time.time() - last_restart[i] < RESTART_COOLDOWN:
                        print(f"[裝置 {i + 1}] 距離上次啟動不到 {RESTART_COOLDOWN} 秒，{RESTART_COOLDOWN} 秒後自動重試")
                        last_restart[i] = time.time()  # 重設冷卻計時器
                        processes[i] = _StoppedStub()
                        continue
                    # 自動重啟
                    env = os.environ.copy()
                    env["SERVER_PORT"] = str(base_port + i)
                    env["UDP_PORT"] = str(base_udp + i)
                    env["DEVICE_ID"] = f"glasses_{i + 1:02d}"
                    print(f"[裝置 {i + 1}] 自動重啟中...")
                    new_proc = subprocess.Popen(
                        [sys.executable, "app_main.py"],
                        cwd=_PROJECT_ROOT,
                        env=env,
                    )
                    processes[i] = new_proc
                    last_restart[i] = time.time()
                    print(f"[裝置 {i + 1}] 已重啟，新 PID={new_proc.pid}")
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
