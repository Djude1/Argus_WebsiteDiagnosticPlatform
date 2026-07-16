"""Task 8：argus-kali-runner 不可變 digest 的 GitOps 推廣腳本。

把 ``shijie85/argus-kali-runner@sha256:<64 hex>`` 原子寫入兩份契約：
- ``k8s/01-namespace-config.yaml`` 的 ``ARGUS_KALI_RUNNER_IMAGE``（ConfigMap）
- ``k8s/11-kali-admission.yaml`` 的 CEL ``approvedImage`` expression（VAP）

設計原則（brief Step 2）：
- 只接受 ``shijie85/argus-kali-runner@sha256:<64 小寫 hex>``；永不接受 tag（如 ``:latest``）。
- 兩份 manifest 必須各自「恰恰一個」digest 符記；零個或多個 → ``ValueError``，
  避免在漂移的 manifest 上靜默寫入。
- 純 regex 字串替換，不重排 YAML、不動註解、不解析引號結構，保持 diff 最小。
- 不印任何機密；``--check`` 僅比對兩份檔案既有的 digest 是否一致。

使用：
    uv run python scripts/promote_kali_image.py --image shijie85/argus-kali-runner@sha256:<hex>
    uv run python scripts/promote_kali_image.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 輸入 image 的錨定格式：只放行 shijie85/argus-kali-runner + 64 個小寫 hex。
# 拒絕：tag（如 :latest）、大寫 hex、非 shijie85 帳號、長度不等於 64。
IMAGE_RE = re.compile(r"^shijie85/argus-kali-runner@sha256:[0-9a-f]{64}$")

# 在 manifest 內搜尋既有 digest 的非錨定 regex（容許被引號或 CEL 字串包住）。
_DIGEST_SEARCH = re.compile(r"shijie85/argus-kali-runner@sha256:[0-9a-f]{64}")

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_REL = Path("k8s/01-namespace-config.yaml")
POLICY_REL = Path("k8s/11-kali-admission.yaml")


def _assert_exactly_one(text: str, where: str) -> str:
    """確認 ``text`` 恰含一個 runner digest 符記；回傳該 digest，否則 ``ValueError``。"""
    matches = _DIGEST_SEARCH.findall(text)
    if len(matches) != 1:
        raise ValueError(
            f"{where} 必須恰恰含一個 runner digest，實際找到 {len(matches)} 個"
        )
    return matches[0]


def read_config_image(root: Path) -> str:
    """讀取 ConfigMap ``ARGUS_KALI_RUNNER_IMAGE`` 目前的 digest。"""
    text = (root / CONFIG_REL).read_text(encoding="utf-8")
    return _assert_exactly_one(text, str(CONFIG_REL))


def read_policy_image(root: Path) -> str:
    """讀取 VAP ``approvedImage`` expression 內目前的 digest。"""
    text = (root / POLICY_REL).read_text(encoding="utf-8")
    return _assert_exactly_one(text, str(POLICY_REL))


def update_repository(root: Path, image: str) -> bool:
    """把兩份 manifest 同步推廣成同一個不可變 digest。

    回傳 ``True`` 表示有檔案被改寫；``False`` 表示兩份原本就已是該 digest（冪等）。
    ``image`` 必須完整匹配 :data:`IMAGE_RE`，否則 ``ValueError``。
    任一份 manifest 的 digest 符記數量不是 1 時亦 ``ValueError``。
    """
    if not IMAGE_RE.match(image):
        raise ValueError(
            "image 必須為 shijie85/argus-kali-runner@sha256:<64 小寫 hex>，"
            f"不接受 tag；收到 {image!r}"
        )

    config_path = root / CONFIG_REL
    policy_path = root / POLICY_REL
    config_text = config_path.read_text(encoding="utf-8")
    policy_text = policy_path.read_text(encoding="utf-8")

    current_config = _assert_exactly_one(config_text, str(CONFIG_REL))
    current_policy = _assert_exactly_one(policy_text, str(POLICY_REL))

    if current_config == image and current_policy == image:
        return False

    # 只替換第一個（也是唯一一個）匹配，保留周邊 YAML 引號與 CEL 字串結構。
    config_path.write_text(
        _DIGEST_SEARCH.sub(lambda _m: image, config_text, count=1),
        encoding="utf-8",
    )
    policy_path.write_text(
        _DIGEST_SEARCH.sub(lambda _m: image, policy_text, count=1),
        encoding="utf-8",
    )
    return True


def check_repository(root: Path) -> int:
    """驗證兩份 manifest 的 digest 一致。

    回傳 0 代表一致；1 代表兩者不一致；2 代表其中一份找不到唯一 digest
    （manifest 結構損毀）。CLI ``--check`` 以本函式回傳值直接 ``sys.exit``。
    """
    try:
        config_image = read_config_image(root)
        policy_image = read_policy_image(root)
    except ValueError:
        return 2
    return 0 if config_image == policy_image else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "把 argus-kali-runner 的不可變 digest 原子寫入 ConfigMap 與 "
            "ValidatingAdmissionPolicy；或以 --check 驗證兩者一致。"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--image",
        metavar="IMAGE",
        help="目標 image，格式 shijie85/argus-kali-runner@sha256:<64 hex>",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="只驗證兩份 manifest 的 digest 是否一致，不寫入",
    )
    args = parser.parse_args(argv)

    root = REPOSITORY_ROOT

    if args.check:
        rc = check_repository(root)
        if rc == 0:
            print("runner digest 一致")
        elif rc == 1:
            print("runner digest 不一致", file=sys.stderr)
        else:
            print("runner digest 符記數量異常", file=sys.stderr)
        return rc

    changed = update_repository(root, args.image)
    print("已推廣 digest" if changed else "digest 未變，無需寫入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
