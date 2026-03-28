"""
download_models.py
自動從 ModelScope 下載 AI 眼鏡系統所需的所有模型檔案。

使用方式：
    uv run python download_models.py

若已安裝 modelscope CLI，也可用：
    modelscope download --model archifancy/AIGlasses_for_navigation --local_dir model/
"""

import os
import sys
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

# ── 模型目錄 ──────────────────────────────────────────────────────────────────
MODEL_DIR = Path(os.getenv("MODEL_DIR", "model"))

# ── 需要下載的模型清單 ────────────────────────────────────────────────────────
# (本地檔名, ModelScope 路徑, 說明, 大小參考)
MODELS = [
    (
        "yolo-seg.pt",
        "yolo-seg.pt",
        "盲道分割模型（YOLO）",
        None,
    ),
    (
        "yoloe-11l-seg.pt",
        "yoloe-11l-seg.pt",
        "開放詞彙物件偵測模型（YOLOE）",
        None,
    ),
    (
        "trafficlight.pt",
        "trafficlight.pt",
        "紅綠燈偵測模型",
        None,
    ),
    (
        "shoppingbest5.pt",
        "shoppingbest5.pt",
        "物品識別模型",
        None,
    ),
    (
        "hand_landmarker.task",
        "hand_landmarker.task",
        "Google MediaPipe 手部偵測模型",
        None,
    ),
]

# ModelScope 原始檔案下載基礎 URL
MODELSCOPE_BASE = (
    "https://modelscope.cn/models/archifancy/AIGlasses_for_navigation"
    "/resolve/master"
)


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    """將 bytes 轉為人類可讀大小"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _progress_hook(downloaded: int, block_size: int, total: int) -> None:
    """下載進度回調"""
    if total <= 0:
        print(f"\r  已下載 {_fmt_size(downloaded)}", end="", flush=True)
        return
    pct = min(100, downloaded * 100 // total)
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(
        f"\r  [{bar}] {pct:3d}%  {_fmt_size(downloaded)}/{_fmt_size(total)}",
        end="",
        flush=True,
    )


def download_file(url: str, dest: Path) -> bool:
    """
    下載單一檔案到指定路徑，失敗回傳 False。
    使用斷點續傳（若伺服器支援）。
    """
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress_hook)
        print()  # 換行
        return True
    except urllib.error.HTTPError as e:
        print(f"\n  HTTP 錯誤 {e.code}：{e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"\n  連線失敗：{e.reason}")
        return False
    except Exception as e:
        print(f"\n  下載失敗：{e}")
        return False


def try_modelscope_sdk(model_id: str, local_dir: Path) -> bool:
    """
    嘗試使用 modelscope Python SDK 下載（速度較快，有完整性驗證）。
    若未安裝 SDK 則跳過。
    """
    try:
        from modelscope.hub.snapshot_download import snapshot_download
        print("  使用 modelscope SDK 下載（推薦）…")
        snapshot_download(model_id=model_id, local_dir=str(local_dir))
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"  SDK 下載失敗：{e}，改用 HTTP 直連…")
        return False


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print(" AI 眼鏡系統 — 模型檔案下載工具")
    print("=" * 60)
    print(f"模型目錄：{MODEL_DIR.resolve()}\n")

    # 建立模型目錄
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 先嘗試用 SDK 一次下載全部
    print("【步驟 1】嘗試使用 modelscope SDK 整批下載…")
    sdk_ok = try_modelscope_sdk(
        "archifancy/AIGlasses_for_navigation", MODEL_DIR
    )

    if sdk_ok:
        print("\n✅ SDK 下載完成！請確認 model/ 目錄中是否有所有模型檔案。")
        _check_all()
        return

    # SDK 不可用，逐一用 HTTP 下載
    print("【步驟 2】使用 HTTP 直連逐一下載…\n")
    failed = []

    for local_name, remote_name, desc, _ in MODELS:
        dest = MODEL_DIR / local_name
        if dest.exists():
            print(f"  ✓ 已存在，跳過：{local_name}（{_fmt_size(dest.stat().st_size)}）")
            continue

        url = f"{MODELSCOPE_BASE}/{remote_name}"
        print(f"  ↓ {desc}")
        print(f"    {local_name}")
        ok = download_file(url, dest)

        if not ok:
            # 清除可能損壞的部分下載
            if dest.exists():
                dest.unlink()
            failed.append(local_name)

    # ── 結果摘要 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    _check_all()

    if failed:
        print("\n⚠ 以下檔案下載失敗，請手動下載：")
        for f in failed:
            print(f"    {f}")
        print(
            "\n手動下載網址：\n"
            "  https://www.modelscope.cn/models/archifancy/AIGlasses_for_navigation\n"
            "  下載後放至 model/ 目錄即可。"
        )
        sys.exit(1)
    else:
        print("\n✅ 所有模型檔案就緒，可以啟動伺服器：")
        print("   uv run python app_main.py")


def _check_all() -> None:
    """列出所有模型檔案的存在狀態"""
    print("\n模型檔案狀態：")
    all_ok = True
    for local_name, _, desc, _ in MODELS:
        dest = MODEL_DIR / local_name
        if dest.exists():
            print(f"  ✅ {local_name:<30} {_fmt_size(dest.stat().st_size):>10}  {desc}")
        else:
            print(f"  ❌ {local_name:<30} {'缺少':>10}  {desc}")
            all_ok = False
    return all_ok


if __name__ == "__main__":
    main()
