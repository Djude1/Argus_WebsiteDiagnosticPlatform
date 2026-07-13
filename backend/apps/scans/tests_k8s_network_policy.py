from pathlib import Path

import yaml
from django.test import SimpleTestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
K8S_ROOT = REPOSITORY_ROOT / "k8s"


def _documents(filename: str) -> list[dict]:
    with (K8S_ROOT / filename).open(encoding="utf-8") as manifest:
        return [document for document in yaml.safe_load_all(manifest) if document]


class KubernetesNetworkPolicyTests(SimpleTestCase):
    def setUp(self):
        policies = _documents("07-network-policies.yaml")
        self.policies = {
            policy["metadata"]["name"]: policy
            for policy in policies
            if policy.get("kind") == "NetworkPolicy"
        }

    def assert_core_dns_rule(self, rule):
        self.assertEqual(
            rule["to"],
            [
                {
                    "namespaceSelector": {
                        "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                    },
                    "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                }
            ],
        )
        self.assertEqual(
            {(port["protocol"], port["port"]) for port in rule["ports"]},
            {("UDP", 53), ("TCP", 53)},
        )

    def test_kustomization_includes_seven_named_policies(self):
        kustomization = _documents("kustomization.yaml")[0]
        self.assertIn("07-network-policies.yaml", kustomization["resources"])
        self.assertEqual(
            set(self.policies),
            {
                "web-ingress-from-frontend",
                "postgres-ingress-from-backend",
                "redis-ingress-from-backend",
                "frontend-egress-boundary",
                "migrate-egress-boundary",
                "application-egress-boundary",
                "data-deny-egress",
            },
        )

    def test_application_egress_only_allows_data_dns_and_public_web_ports(self):
        policy = self.policies["application-egress-boundary"]
        self.assertEqual(
            set(policy["spec"]["podSelector"]["matchExpressions"][0]["values"]),
            {"web", "worker"},
        )
        rules = policy["spec"]["egress"]
        self.assertEqual(rules[0]["to"][0]["podSelector"]["matchLabels"], {"app": "db"})
        self.assertEqual(rules[1]["to"][0]["podSelector"]["matchLabels"], {"app": "redis"})
        self.assert_core_dns_rule(rules[2])

        public_rule = rules[3]
        ip_block = public_rule["to"][0]["ipBlock"]
        self.assertEqual(ip_block["cidr"], "0.0.0.0/0")
        self.assertTrue(
            {
                "0.0.0.0/8",
                "10.0.0.0/8",
                "100.64.0.0/10",
                "127.0.0.0/8",
                "169.254.0.0/16",
                "172.16.0.0/12",
                "192.168.0.0/16",
                "198.18.0.0/15",
                "224.0.0.0/4",
                "240.0.0.0/4",
            }.issubset(set(ip_block["except"]))
        )
        self.assertEqual(
            {(port["protocol"], port["port"]) for port in public_rule["ports"]},
            {("TCP", 80), ("TCP", 443), ("TCP", 587)},
        )

        # IPv6 公網 egress：dual-stack 叢集若無此 rule，預設 deny 擋掉所有 IPv6 出站。
        # CNI 必須支援 IPv6 NetworkPolicy 才生效；ipBlock.except 對 IPv6 同樣有效。
        ipv6_rule = rules[4]
        ipv6_block = ipv6_rule["to"][0]["ipBlock"]
        self.assertEqual(ipv6_block["cidr"], "::/0")
        self.assertTrue(
            {
                "::/128",
                "::1/128",
                "::ffff:0:0/96",
                "64:ff9b::/96",
                "100::/64",
                "2001:db8::/32",
                "fc00::/7",
                "fe80::/10",
                "ff00::/8",
            }.issubset(set(ipv6_block["except"]))
        )
        self.assertEqual(
            {(port["protocol"], port["port"]) for port in ipv6_rule["ports"]},
            {("TCP", 80), ("TCP", 443), ("TCP", 587)},
        )

    def test_frontend_and_migrate_have_minimal_egress(self):
        frontend_rules = self.policies["frontend-egress-boundary"]["spec"]["egress"]
        self.assertEqual(len(frontend_rules), 2)
        self.assertEqual(
            frontend_rules[0]["to"][0]["podSelector"]["matchLabels"],
            {"app": "web"},
        )
        self.assert_core_dns_rule(frontend_rules[1])

        migrate_job = next(
            document
            for document in _documents("04-backend.yaml")
            if document.get("kind") == "Job"
        )
        self.assertEqual(
            migrate_job["spec"]["template"]["metadata"]["labels"],
            {"app": "migrate"},
        )
        migrate_rules = self.policies["migrate-egress-boundary"]["spec"]["egress"]
        self.assertEqual(len(migrate_rules), 2)
        self.assertEqual(
            migrate_rules[0]["to"][0]["podSelector"]["matchLabels"],
            {"app": "db"},
        )
        self.assert_core_dns_rule(migrate_rules[1])

    def test_data_services_are_ingress_limited_and_cannot_initiate_egress(self):
        postgres = self.policies["postgres-ingress-from-backend"]
        postgres_sources = postgres["spec"]["ingress"][0]["from"][0]["podSelector"]
        self.assertEqual(
            set(postgres_sources["matchExpressions"][0]["values"]),
            {"web", "worker", "migrate"},
        )
        redis = self.policies["redis-ingress-from-backend"]
        redis_sources = redis["spec"]["ingress"][0]["from"][0]["podSelector"]
        self.assertEqual(
            set(redis_sources["matchExpressions"][0]["values"]),
            {"web", "worker"},
        )
        self.assertEqual(self.policies["data-deny-egress"]["spec"]["egress"], [])

    def test_kustomization_includes_ngf_client_settings_policy(self):
        kustomization = _documents("kustomization.yaml")[0]
        self.assertIn("09-ngf-client-settings.yaml", kustomization["resources"])
        documents = _documents("09-ngf-client-settings.yaml")
        policies = [
            doc for doc in documents
            if doc.get("kind") == "ClientSettingsPolicy"
        ]
        self.assertEqual(len(policies), 1)
        policy = policies[0]
        self.assertEqual(policy["apiVersion"], "gateway.nginx.org/v1alpha1")
        self.assertEqual(policy["metadata"]["namespace"], "argus")
        target = policy["spec"]["targetRef"]
        self.assertEqual(target["kind"], "Gateway")
        self.assertEqual(target["name"], "argus-gateway")
        # 對齊 frontend nginx 的 client_max_body_size 6m
        self.assertEqual(policy["spec"]["body"]["maxSize"], "6m")
