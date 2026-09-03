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

    def test_worker_grace_period_covers_a_full_scan(self):
        """SIGTERM 後要讓 Celery 有時間把當前掃描跑完。

        預設 grace period 只有 30 秒，但一次掃描要好幾分鐘。30 秒後 SIGKILL，
        run_scan_job 的 except 全部跑不到，ScanJob 永遠停在 scanning、預扣的
        coin 永遠不退——使用者實際遇過一次（卡 95 分鐘），而每次 rollout 都會
        重新觸發。
        """
        import yaml

        documents = [
            d
            for d in yaml.safe_load_all(
                (Path(__file__).resolve().parents[1] / "k8s" / "04-backend.yaml")
                .read_text(encoding="utf-8")
            )
            if d
        ]
        worker = next(
            d for d in documents
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "worker"
        )
        grace = worker["spec"]["template"]["spec"].get("terminationGracePeriodSeconds")

        self.assertIsNotNone(grace, "worker 必須明確設定 terminationGracePeriodSeconds")
        self.assertGreaterEqual(grace, 600)

    def test_stale_scan_reaper_cronjob_exists(self):
        """grace period 擋不住 OOM 與節點故障，仍需要定期回收。"""
        import yaml

        documents = [
            d
            for d in yaml.safe_load_all(
                (Path(__file__).resolve().parents[1] / "k8s" / "04-backend.yaml")
                .read_text(encoding="utf-8")
            )
            if d
        ]
        cron = next(
            (d for d in documents if d["kind"] == "CronJob"), None
        )

        self.assertIsNotNone(cron, "缺少回收卡住掃描的 CronJob")
        container = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(
            container["command"],
            ["/app/.venv/bin/python", "manage.py", "reap_stale_scans"],
        )
        # Forbid：回收作業重疊執行沒有好處，只會讓兩個程序搶同一批列
        self.assertEqual(cron["spec"]["concurrencyPolicy"], "Forbid")

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
