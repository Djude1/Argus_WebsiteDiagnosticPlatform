"""Task 8 測試：不可變 runner digest 推廣腳本。

驗證 ``scripts/promote_kali_image.py`` 的契約：
- ``update_repository`` 把同一個 ``shijie85/argus-kali-runner@sha256:<64 hex>``
  原子寫入 ConfigMap 與 ValidatingAdmissionPolicy；零個或多個 digest 符記 → ValueError。
- 只接受不可變 digest，拒絕 tag（如 ``:latest``）、錯誤帳號、長度/大小寫不符的 hash。
- ``check_repository`` 在兩份 manifest 一致時回傳 0，不一致時回傳非零。
- ``--check`` CLI 在真實 repo root（目前為 disabled sentinel）exit 0。

為了隔離，更新邏輯的測試使用暫存目錄，只鋪兩份假的 k8s manifest；
``--check`` CLI 測試才打開真實 repo root。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
# 讓 `import promote_kali_image` 在單元測試與 CI 都能找到 scripts/ 目錄。
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import promote_kali_image  # noqa: E402  (sys.path 注入後才能 import)

CONFIG_REL = Path("k8s/01-namespace-config.yaml")
POLICY_REL = Path("k8s/11-kali-admission.yaml")

# disabled sentinel：與 k8s/01-namespace-config.yaml、11-kali-admission.yaml 同步。
DISABLED_SENTINEL = (
    "shijie85/argus-kali-runner@sha256:"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def _config_text(image: str) -> str:
    """產生只含 ARGUS_KALI_RUNNER_IMAGE 一列的 ConfigMap 片段。"""
    return 'data:\n  ARGUS_KALI_RUNNER_IMAGE: "' + image + '"\n'


def _policy_text(image: str) -> str:
    """產生含 CEL approvedImage expression 的 VAP 片段（digest 藏在 CEL 字串內）。"""
    return (
        "variables:\n"
        "  - name: approvedImage\n"
        '    expression: "\'' + image + '\'"\n'
    )


class UpdateRepositoryTests(unittest.TestCase):
    """``update_repository`` 的契約測試，使用暫存目錄隔離真實 manifest。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "k8s").mkdir(parents=True)
        self._seed(DISABLED_SENTINEL, DISABLED_SENTINEL)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self, config_image: str, policy_image: str) -> None:
        (self.root / CONFIG_REL).write_text(_config_text(config_image), encoding="utf-8")
        (self.root / POLICY_REL).write_text(_policy_text(policy_image), encoding="utf-8")

    # -- brief 種子測試 --------------------------------------------------

    def test_updates_config_and_policy_to_the_same_digest(self) -> None:
        image = "shijie85/argus-kali-runner@sha256:" + "a" * 64
        changed = promote_kali_image.update_repository(self.root, image)
        self.assertTrue(changed)
        self.assertEqual(promote_kali_image.read_config_image(self.root), image)
        self.assertEqual(promote_kali_image.read_policy_image(self.root), image)

    def test_rejects_tags(self) -> None:
        with self.assertRaises(ValueError):
            promote_kali_image.update_repository(
                self.root, "shijie85/argus-kali-runner:latest"
            )

    # -- 邊界情境：malformed / 帳號 / hash 長度與大小寫 -------------------

    def test_rejects_short_hash(self) -> None:
        with self.assertRaises(ValueError):
            promote_kali_image.update_repository(
                self.root,
                "shijie85/argus-kali-runner@sha256:" + "a" * 63,
            )

    def test_rejects_uppercase_hex(self) -> None:
        with self.assertRaises(ValueError):
            promote_kali_image.update_repository(
                self.root,
                "shijie85/argus-kali-runner@sha256:" + "A" * 64,
            )

    def test_rejects_wrong_repository(self) -> None:
        with self.assertRaises(ValueError):
            promote_kali_image.update_repository(
                self.root,
                "evil/argus-kali-runner@sha256:" + "a" * 64,
            )

    # -- 邊界情境：manifest 漂移（零個 / 多個符記）------------------------

    def test_rejects_zero_matches_in_config(self) -> None:
        (self.root / CONFIG_REL).write_text('data:\n  OTHER: "x"\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            promote_kali_image.update_repository(
                self.root,
                "shijie85/argus-kali-runner@sha256:" + "a" * 64,
            )

    def test_rejects_multiple_matches_in_config(self) -> None:
        doubled = _config_text(DISABLED_SENTINEL) + _config_text(DISABLED_SENTINEL)
        (self.root / CONFIG_REL).write_text(doubled, encoding="utf-8")
        with self.assertRaises(ValueError):
            promote_kali_image.update_repository(
                self.root,
                "shijie85/argus-kali-runner@sha256:" + "a" * 64,
            )

    def test_rejects_zero_matches_in_policy(self) -> None:
        (self.root / POLICY_REL).write_text("variables: []\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            promote_kali_image.update_repository(
                self.root,
                "shijie85/argus-kali-runner@sha256:" + "a" * 64,
            )

    # -- 冪等：相同 digest 不再寫入 --------------------------------------

    def test_no_change_returns_false(self) -> None:
        changed = promote_kali_image.update_repository(self.root, DISABLED_SENTINEL)
        self.assertFalse(changed)


class CheckRepositoryTests(unittest.TestCase):
    """``check_repository`` 的 exit-code 契約。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "k8s").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self, config_image: str, policy_image: str) -> None:
        (self.root / CONFIG_REL).write_text(_config_text(config_image), encoding="utf-8")
        (self.root / POLICY_REL).write_text(_policy_text(policy_image), encoding="utf-8")

    def test_check_zero_when_both_equal(self) -> None:
        self._seed(DISABLED_SENTINEL, DISABLED_SENTINEL)
        self.assertEqual(promote_kali_image.check_repository(self.root), 0)

    def test_check_nonzero_when_diverged(self) -> None:
        other = "shijie85/argus-kali-runner@sha256:" + "b" * 64
        self._seed(DISABLED_SENTINEL, other)
        self.assertNotEqual(promote_kali_image.check_repository(self.root), 0)

    def test_check_nonzero_when_manifest_broken(self) -> None:
        (self.root / CONFIG_REL).write_text('data:\n  OTHER: "x"\n', encoding="utf-8")
        (self.root / POLICY_REL).write_text(_policy_text(DISABLED_SENTINEL), encoding="utf-8")
        self.assertNotEqual(promote_kali_image.check_repository(self.root), 0)


class CheckCliTests(unittest.TestCase):
    """``--check`` CLI 在真實 repo root 的 exit-code 契約。"""

    def test_real_repo_sentinel_pair_exits_zero(self) -> None:
        # 真實 repo 目前為 disabled sentinel；兩份 manifest 一致 → exit 0。
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "scripts" / "promote_kali_image.py"),
                "--check",
            ],
            cwd=str(REPOSITORY_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"--check 應 exit 0；stderr={result.stderr!r} stdout={result.stdout!r}",
        )


if __name__ == "__main__":
    unittest.main()
