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

    def test_web_http_probes_use_allowed_host_header(self):
        manifest = (
            Path(__file__).resolve().parents[1] / "k8s" / "04-backend.yaml"
        ).read_text(encoding="utf-8")

        for probe, path in (
            ("readinessProbe", "/api/health/ready/"),
            ("livenessProbe", "/api/health/live/"),
        ):
            expected_probe = (
                f"          {probe}:\n"
                "            httpGet:\n"
                f"              path: {path}\n"
                "              port: 8000\n"
                "              httpHeaders:\n"
                "                - name: Host\n"
                "                  value: localhost"
            )
            self.assertIn(expected_probe, manifest)

    def test_ipv6_egress_uses_kubernetes_valid_global_unicast_cidr(self):
        manifest = (
            Path(__file__).resolve().parents[1] / "k8s" / "07-network-policies.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn("cidr: 2000::/3", manifest)
        self.assertNotIn("cidr: ::/0", manifest)
        self.assertNotIn("::ffff:0:0/96", manifest)
        self.assertIn("- 2001::/23", manifest)
        self.assertIn("- 2001:db8::/32", manifest)
        self.assertIn("- 2002::/16", manifest)
        self.assertIn("- 3fff::/20", manifest)


if __name__ == "__main__":
    unittest.main()
