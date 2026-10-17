"""OWASP ZAP 被動分析的部署契約。

檔案：k8s/12-zap-passive.yaml、docker-compose.yml 的 zap service。

鎖定：
- 正式環境（K8s）預設部署並啟用：manifest 列在 kustomization、ConfigMap 開啟並指向叢集內 Service、
  worker 有到 ZAP 8090 的 egress（2026-10-12）；本機 compose 仍只在 profile `zap`
- 映像以 digest 固定版本，兩處一致
- 啟用檔案傳輸（HAR 上傳需要），API 金鑰來自 Secret／.env，不寫死
- ZAP 沒有對外連線：K8s egress 全擋、只收 argus namespace worker；compose 只接 internal 網路
- restricted Pod Security：非 root、不提權、drop ALL、有資源上限
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "k8s" / "12-zap-passive.yaml"
IMAGE = (
    "ghcr.io/zaproxy/zaproxy:2.16.1@sha256:"
    "7840969c7c9fead565bf9734b12f49f6886db90b1d35b1f74d79710bbd081dab"
)


def _docs() -> dict[str, dict]:
    return {doc["kind"]: doc for doc in yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8"))}


class ZapKubernetesContractTests(unittest.TestCase):
    def test_deployed_and_enabled_in_production(self):
        kustomization = yaml.safe_load((ROOT / "k8s" / "kustomization.yaml").read_text())
        self.assertIn("12-zap-passive.yaml", kustomization["resources"])
        config = next(
            doc
            for doc in yaml.safe_load_all((ROOT / "k8s" / "01-namespace-config.yaml").read_text())
            if doc and doc.get("kind") == "ConfigMap"
        )["data"]
        self.assertEqual(config["ARGUS_ZAP_ENABLED"], "true")
        self.assertEqual(config["ARGUS_ZAP_API_URL"], "http://zap.argus-zap.svc.cluster.local:8090")
        # 金鑰只能在 Secret，不得出現在 ConfigMap
        self.assertNotIn("ARGUS_ZAP_API_KEY", config)

    def test_worker_egress_to_zap_only(self):
        policies = {
            doc["metadata"]["name"]: doc["spec"]
            for doc in yaml.safe_load_all((ROOT / "k8s" / "07-network-policies.yaml").read_text())
            if doc and doc.get("kind") == "NetworkPolicy"
        }
        spec = policies["worker-egress-to-zap"]
        self.assertEqual(spec["podSelector"], {"matchLabels": {"app": "worker"}})
        self.assertEqual(spec["policyTypes"], ["Egress"])
        target = spec["egress"][0]["to"][0]
        self.assertEqual(
            target["namespaceSelector"]["matchLabels"], {"kubernetes.io/metadata.name": "argus-zap"}
        )
        self.assertEqual(target["podSelector"]["matchLabels"], {"app": "zap"})
        self.assertEqual(spec["egress"][0]["ports"], [{"protocol": "TCP", "port": 8090}])

    def test_pinned_image_and_secret_key(self):
        container = _docs()["Deployment"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], IMAGE)
        args = " ".join(container["args"])
        self.assertIn("api.filexfer=true", args)
        self.assertIn('api.key="$ZAP_API_KEY"', args)
        self.assertIn("start.checkForUpdates=false", args)
        # api.addrs 是清單，-config 必須帶索引 addr(0)；少了 (0) ZAP 不會註冊這條，
        # 預設只認 localhost，worker 用 FQDN 連進來會被當成 proxy 流量並回 502（2026-10-18）
        self.assertIn("api.addrs.addr(0).name=.*", args)
        self.assertIn("api.addrs.addr(0).regex=true", args)
        key_env = next(e for e in container["env"] if e["name"] == "ZAP_API_KEY")
        self.assertEqual(
            key_env["valueFrom"]["secretKeyRef"], {"name": "zap-api", "key": "api-key"}
        )

    def test_no_egress_and_worker_only_ingress(self):
        policy = _docs()["NetworkPolicy"]["spec"]
        self.assertEqual(set(policy["policyTypes"]), {"Ingress", "Egress"})
        self.assertEqual(policy["egress"], [])
        source = policy["ingress"][0]["from"][0]
        self.assertEqual(
            source["namespaceSelector"]["matchLabels"], {"kubernetes.io/metadata.name": "argus"}
        )
        self.assertEqual(source["podSelector"]["matchLabels"], {"app": "worker"})
        self.assertEqual(policy["ingress"][0]["ports"], [{"protocol": "TCP", "port": 8090}])

    def test_restricted_pod(self):
        docs = _docs()
        labels = docs["Namespace"]["metadata"]["labels"]
        self.assertEqual(labels["pod-security.kubernetes.io/enforce"], "restricted")
        pod = docs["Deployment"]["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        container = pod["containers"][0]
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertIn("memory", container["resources"]["limits"])
        self.assertIn("emptyDir", pod["volumes"][0])


class ZapComposeContractTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    def test_profile_only_and_internal_network(self):
        zap = self.compose["services"]["zap"]
        self.assertEqual(zap["profiles"], ["zap"])
        self.assertEqual(zap["image"], IMAGE)
        self.assertEqual(zap["networks"], ["zap_internal"])
        self.assertTrue(self.compose["networks"]["zap_internal"]["internal"])
        self.assertIn("zap_internal", self.compose["services"]["worker"]["networks"])
        self.assertIn("default", self.compose["services"]["worker"]["networks"])

    def test_key_from_env_and_refuses_empty(self):
        zap = self.compose["services"]["zap"]
        self.assertEqual(zap["environment"]["ZAP_API_KEY"], "${ARGUS_ZAP_API_KEY:-}")
        script = zap["command"][-1]
        self.assertIn('test -n "$$ZAP_API_KEY"', script)
        self.assertIn("api.filexfer=true", script)
        self.assertIn("api.addrs.addr(0).name=.*", script)


if __name__ == "__main__":
    unittest.main()
