import unittest
from pathlib import Path


class K8sRuntimeCommandsTest(unittest.TestCase):
    def test_backend_manifest_does_not_run_uv_at_runtime(self):
        manifest = (
            Path(__file__).resolve().parents[1] / "k8s" / "04-backend.yaml"
        ).read_text(encoding="utf-8")

        self.assertNotIn('["uv", "run"', manifest)
        self.assertNotIn("uv run ", manifest)

    def test_backend_manifest_uses_image_virtualenv_executables(self):
        manifest = (
            Path(__file__).resolve().parents[1] / "k8s" / "04-backend.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'command: ["/app/.venv/bin/python", "manage.py", "migrate", "--noinput"]',
            manifest,
        )
        self.assertEqual(manifest.count("until /app/.venv/bin/python "), 2)
        self.assertIn(
            'command: ["/app/.venv/bin/gunicorn", "config.wsgi:application"',
            manifest,
        )
        self.assertIn(
            'command: ["/app/.venv/bin/celery", "-A", "config", "worker"',
            manifest,
        )
        self.assertIn(
            '"/app/.venv/bin/celery -A config inspect ping ',
            manifest,
        )


if __name__ == "__main__":
    unittest.main()
