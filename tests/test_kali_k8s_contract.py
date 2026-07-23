"""Task 7 契約測試：argus-kali namespace 隔離、RBAC、admission 與 NetworkPolicy.

渲染 ``k8s/`` Kustomize 並解析輸出 YAML，逐項斷言受限 namespace 的形狀：

- argus-kali namespace 套用 restricted:v1.35 Pod Security labels + argus.io/kali-runner=true
- argus-worker-kali-orchestrator SA 在 argus namespace；kali-runner SA 在 argus-kali
  namespace 且 ``automountServiceAccountToken=false``（無 RoleBinding → tokenless）
- Role 僅含 least-privilege verbs（secrets 只能 create/delete，不得 get/list/watch/read）
- ResourceQuota hard：pods=1、count/jobs.batch=1、CPU/memory/ephemeral-storage 精確值
- application-egress-boundary 含 10.96.0.1/32:443 與 172.16.2.122/32:6443 兩條 API rule
- argus-kali namespace 內有 default-deny 與 runner-egress（CoreDNS + IPv4/IPv6 公網 80/443）
- ValidatingAdmissionPolicy failurePolicy: Fail，approvedImage 為 disabled sentinel
- VAP Binding validationActions: [Deny]、namespaceSelector: argus.io/kali-runner=true
- 13 條 CEL 涵蓋 brief 全部欄位（name/volume/securityContext/resources/...）
- worker Deployment serviceAccountName=argus-worker-kali-orchestrator
- ConfigMap ARGUS_KALI_* 全 disabled
- kustomization 收錄 10-kali-runtime.yaml 與 11-kali-admission.yaml

本測試刻意與 ``backend/apps/scans/tests_k8s_network_policy.py`` 互補：前者专注
manifests 的靜態形狀（不依賴 Django），後者驗證既有 namespace 邊界未被破壞。
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
K8S_ROOT = REPOSITORY_ROOT / "k8s"

# disabled sentinel：正式 Kali 尚未啟用，admission 只放行這個 digest；
# 啟用時 Task 11 會把這個常數與 ConfigMap / VAP variable 同步換成真 digest。
DISABLED_SENTINEL = (
    "shijie85/argus-kali-runner@sha256:"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def _render_kustomize() -> list[dict]:
    """透過 ``kubectl kustomize k8s`` 渲染全部 manifest，回傳所有 YAML 文件。

    manifest 內含繁體中文註解，subprocess 必須明確指定 UTF-8 解碼，否則在
    Windows 預設 CP950 locale 會 ``UnicodeDecodeError``。
    """
    result = subprocess.run(
        ["kubectl", "kustomize", str(K8S_ROOT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _documents(filename: str) -> list[dict]:
    with (K8S_ROOT / filename).open(encoding="utf-8") as manifest:
        return [doc for doc in yaml.safe_load_all(manifest) if doc]


class KaliK8sContractTests(unittest.TestCase):
    """argus-kali 受限 namespace 的靜態契約。"""

    @classmethod
    def setUpClass(cls):
        cls.rendered = _render_kustomize()
        cls.by_kind_name = {
            (doc.get("kind"), doc.get("metadata", {}).get("name")): doc
            for doc in cls.rendered
        }

    # ------------------------------------------------------------------
    # Namespace + Pod Security Admission labels
    # ------------------------------------------------------------------
    def test_argus_kali_namespace_enforces_restricted_pod_security_v1_35(self):
        ns = self.by_kind_name[("Namespace", "argus-kali")]
        labels = ns["metadata"]["labels"]
        for key in (
            "pod-security.kubernetes.io/enforce",
            "pod-security.kubernetes.io/audit",
            "pod-security.kubernetes.io/warn",
        ):
            self.assertEqual(labels[key], "restricted", f"{key} 必須為 restricted")
        for key in (
            "pod-security.kubernetes.io/enforce-version",
            "pod-security.kubernetes.io/audit-version",
            "pod-security.kubernetes.io/warn-version",
        ):
            self.assertEqual(labels[key], "v1.35", f"{key} 必須為 v1.35")
        # VAP Binding 的 namespaceSelector 標的；缺少會讓 policy 無法附著。
        self.assertEqual(labels["argus.io/kali-runner"], "true")

    # ------------------------------------------------------------------
    # ServiceAccount：worker orchestrator (argus ns) + tokenless runner
    # ------------------------------------------------------------------
    def test_worker_orchestrator_service_account_lives_in_argus_namespace(self):
        sa = self.by_kind_name[("ServiceAccount", "argus-worker-kali-orchestrator")]
        self.assertEqual(sa["metadata"]["namespace"], "argus")

    def test_runner_service_account_is_tokenless_in_argus_kali_namespace(self):
        sa = self.by_kind_name[("ServiceAccount", "kali-runner")]
        self.assertEqual(sa["metadata"]["namespace"], "argus-kali")
        # automountServiceAccountToken 必須是 boolean False（不是字串）
        self.assertIs(sa["automountServiceAccountToken"], False)

    # ------------------------------------------------------------------
    # RBAC：least-privilege Role + 無 secrets read + 無 runner RoleBinding
    # ------------------------------------------------------------------
    def test_orchestrator_role_has_exact_least_privilege_verbs(self):
        role = self.by_kind_name[("Role", "argus-kali-orchestrator")]
        self.assertEqual(role["metadata"]["namespace"], "argus-kali")
        self.assertEqual(
            role["rules"],
            [
                {
                    "apiGroups": ["batch"],
                    "resources": ["jobs"],
                    "verbs": ["create", "get", "list", "watch", "delete"],
                },
                {
                    "apiGroups": [""],
                    "resources": ["secrets"],
                    "verbs": ["create", "delete"],
                },
                {
                    "apiGroups": [""],
                    "resources": ["pods"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": [""],
                    "resources": ["pods/log"],
                    "verbs": ["get"],
                },
            ],
        )

    def test_orchestrator_role_binding_references_worker_sa_in_argus(self):
        binding = self.by_kind_name[
            ("RoleBinding", "argus-kali-orchestrator-binding")
        ]
        self.assertEqual(binding["metadata"]["namespace"], "argus-kali")
        subjects = binding["subjects"]
        self.assertEqual(len(subjects), 1)
        subject = subjects[0]
        self.assertEqual(subject["kind"], "ServiceAccount")
        self.assertEqual(subject["name"], "argus-worker-kali-orchestrator")
        # RoleBinding 跨 namespace：subject 必須指向 argus namespace 的 SA
        self.assertEqual(subject["namespace"], "argus")
        self.assertEqual(
            binding["roleRef"],
            {
                "kind": "Role",
                "name": "argus-kali-orchestrator",
                "apiGroup": "rbac.authorization.k8s.io",
            },
        )

    def test_no_role_binding_references_kali_runner_sa(self):
        """kali-runner SA 必須 tokenless：任何 RoleBinding 都不得 reference 它。"""
        offenders = []
        for doc in self.rendered:
            if doc.get("kind") != "RoleBinding":
                continue
            for subject in doc.get("subjects", []):
                if (
                    subject.get("kind") == "ServiceAccount"
                    and subject.get("name") == "kali-runner"
                ):
                    offenders.append(doc["metadata"]["name"])
        self.assertEqual(offenders, [], "kali-runner SA 不應被任何 RoleBinding 綁定")

    # ------------------------------------------------------------------
    # Quota + LimitRange：只允許一個 runner Pod
    # ------------------------------------------------------------------
    def test_single_runner_resource_quota_exact_values(self):
        quota = self.by_kind_name[("ResourceQuota", "argus-kali-single-runner")]
        self.assertEqual(quota["metadata"]["namespace"], "argus-kali")
        self.assertEqual(
            quota["spec"]["hard"],
            {
                "pods": "1",
                "count/jobs.batch": "1",
                "requests.cpu": "250m",
                "requests.memory": "256Mi",
                "requests.ephemeral-storage": "256Mi",
                "limits.cpu": "1",
                "limits.memory": "768Mi",
                "limits.ephemeral-storage": "1Gi",
            },
        )

    def test_runner_limits_exist_in_argus_kali_namespace(self):
        limit_range = self.by_kind_name[("LimitRange", "argus-kali-runner-limits")]
        self.assertEqual(limit_range["metadata"]["namespace"], "argus-kali")

    # ------------------------------------------------------------------
    # NetworkPolicy：worker API egress + argus-kali 隔離
    # ------------------------------------------------------------------
    def test_application_egress_has_exact_two_api_rules(self):
        policy = self.by_kind_name[("NetworkPolicy", "application-egress-boundary")]
        egress = policy["spec"]["egress"]
        api_rules = [
            rule
            for rule in egress
            if "to" in rule
            and rule["to"]
            and "ipBlock" in rule["to"][0]
            and rule["to"][0]["ipBlock"]["cidr"]
            in ("10.96.0.1/32", "172.16.2.122/32")
        ]
        self.assertEqual(len(api_rules), 2, "必須恰好兩條 API /32 rule")
        cidrs = {rule["to"][0]["ipBlock"]["cidr"] for rule in api_rules}
        self.assertEqual(cidrs, {"10.96.0.1/32", "172.16.2.122/32"})
        for rule in api_rules:
            cidr = rule["to"][0]["ipBlock"]["cidr"]
            expected_port = 443 if cidr == "10.96.0.1/32" else 6443
            self.assertEqual(
                {(port["protocol"], port["port"]) for port in rule["ports"]},
                {("TCP", expected_port)},
            )
            # 確保只有一個 ipBlock（沒有夾帶其它目的）
            self.assertEqual(len(rule["to"]), 1)

    def test_argus_kali_default_deny_isolates_namespace(self):
        policy = self.by_kind_name[("NetworkPolicy", "argus-kali-default-deny")]
        self.assertEqual(policy["metadata"]["namespace"], "argus-kali")
        self.assertEqual(policy["spec"]["podSelector"], {})
        self.assertEqual(
            set(policy["spec"]["policyTypes"]), {"Ingress", "Egress"}
        )
        self.assertEqual(policy["spec"].get("ingress", []), [])
        self.assertEqual(policy["spec"].get("egress", []), [])

    def test_argus_kali_runner_egress_dns_and_public_web_ports_only(self):
        policy = self.by_kind_name[
            ("NetworkPolicy", "argus-kali-runner-egress")
        ]
        self.assertEqual(policy["metadata"]["namespace"], "argus-kali")
        egress = policy["spec"]["egress"]

        # DNS rule：CoreDNS 在 kube-system，TCP/UDP 53
        dns_rules = [
            rule
            for rule in egress
            if "to" in rule
            and rule["to"]
            and "namespaceSelector" in rule["to"][0]
        ]
        self.assertEqual(len(dns_rules), 1)
        dns_rule = dns_rules[0]
        self.assertEqual(
            dns_rule["to"][0]["namespaceSelector"]["matchLabels"],
            {"kubernetes.io/metadata.name": "kube-system"},
        )
        self.assertEqual(
            dns_rule["to"][0]["podSelector"]["matchLabels"], {"k8s-app": "kube-dns"}
        )
        self.assertEqual(
            {(p["protocol"], p["port"]) for p in dns_rule["ports"]},
            {("UDP", 53), ("TCP", 53)},
        )

        # 公網 IPv4/IPv6 rule：只能 TCP 80/443（不可含 587）
        for rule in egress:
            for port in rule.get("ports", []):
                self.assertNotEqual(
                    port["port"], 587, "Kali runner 不得使用 SMTP 587"
                )
        ip_rules = [
            rule
            for rule in egress
            if "to" in rule
            and rule["to"]
            and "ipBlock" in rule["to"][0]
        ]
        self.assertGreaterEqual(len(ip_rules), 1, "必須至少有一條公網 ipBlock egress")
        for rule in ip_rules:
            ports = {(p["protocol"], p["port"]) for p in rule["ports"]}
            self.assertTrue(
                ports.issubset({("TCP", 80), ("TCP", 443)}),
                f"Kali runner 公網 egress 只允許 TCP 80/443，實際：{ports}",
            )

    # ------------------------------------------------------------------
    # Admission：fail-closed VAP + Binding
    # ------------------------------------------------------------------
    def test_admission_policy_is_fail_closed(self):
        policy = self.by_kind_name[
            ("ValidatingAdmissionPolicy", "argus-kali-admission")
        ]
        self.assertEqual(policy["spec"]["failurePolicy"], "Fail")
        # matchConstraints 必須只針對 batch/v1 jobs 的 CREATE/UPDATE
        rules = policy["spec"]["matchConstraints"]["resourceRules"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(
            rules[0],
            {
                "apiGroups": ["batch"],
                "apiVersions": ["v1"],
                "operations": ["CREATE", "UPDATE"],
                "resources": ["jobs"],
            },
        )

    def test_admission_policy_approved_image_variable_is_disabled_sentinel(self):
        policy = self.by_kind_name[
            ("ValidatingAdmissionPolicy", "argus-kali-admission")
        ]
        variables = policy["spec"]["variables"]
        approved = next(v for v in variables if v["name"] == "approvedImage")
        self.assertIn(DISABLED_SENTINEL, approved["expression"])

    def test_admission_binding_denies_with_namespace_selector(self):
        binding = self.by_kind_name[
            ("ValidatingAdmissionPolicyBinding", "argus-kali-admission-binding")
        ]
        self.assertEqual(binding["spec"]["policyName"], "argus-kali-admission")
        self.assertEqual(binding["spec"]["validationActions"], ["Deny"])
        selector = binding["spec"]["matchResources"]["namespaceSelector"]
        self.assertEqual(
            selector["matchLabels"],
            {"argus.io/kali-runner": "true"},
        )

    def test_admission_policy_covers_all_brief_cel_fields(self):
        """13 條 CEL 涵蓋 brief 指定的全部欄位（5 結構 + 8 詳細欄位）。"""
        policy = self.by_kind_name[
            ("ValidatingAdmissionPolicy", "argus-kali-admission")
        ]
        expressions = [v["expression"] for v in policy["spec"]["validations"]]
        self.assertGreaterEqual(
            len(expressions),
            13,
            "CEL 數量不得少於 brief 指定的 13 條（5 結構 + 8 詳細欄位）",
        )
        joined = "\n".join(expressions)
        # 對齊 Task 4 KubernetesSqlmapExecutor.build_restricted_runner_pod 與
        # _create_job 的所有發射欄位；缺任一個代表 CEL 與 executor 形狀不一致。
        required_needles = (
            # Job name pattern（_job_name + _correlation_id）
            "object.metadata.name.matches('^argus-sqlmap-[a-f0-9]{10}-[a-f0-9]{12}$')",
            # Job 結構（_create_job：parallelism/completions/backoff/ttl/deadline）
            "object.spec.parallelism == 1",
            "object.spec.completions == 1",
            "object.spec.backoffLimit == 0",
            "object.spec.ttlSecondsAfterFinished == 300",
            "object.spec.activeDeadlineSeconds >= 150",
            "object.spec.activeDeadlineSeconds <= 390",
            # Pod template（build_restricted_runner_pod）
            "serviceAccountName == 'kali-runner'",
            "automountServiceAccountToken == false",
            "restartPolicy == 'Never'",
            # Image / command / args
            "image == variables.approvedImage",
            "command == ['/usr/local/bin/python']",
            "args == ['/opt/argus/runner.py']",
            # Volumes（targets Secret + scratch emptyDir）
            "v.name == 'targets'",
            "v.secret.secretName.matches('^argus-targets-[a-f0-9]{10}-[a-f0-9]{12}$')",
            "v.secret.defaultMode == 256",
            "v.name == 'scratch'",
            "v.emptyDir.sizeLimit == quantity('1Gi')",
            # Pod securityContext
            "runAsNonRoot == true",
            "runAsUser == 65532",
            "runAsGroup == 65532",
            "fsGroup == 65532",
            "seccompProfile.type == 'RuntimeDefault'",
            # Container securityContext
            "readOnlyRootFilesystem == true",
            "allowPrivilegeEscalation == false",
            "capabilities.drop == ['ALL']",
            # VolumeMounts
            "v.mountPath == '/run/argus-targets'",
            "v.readOnly == true",
            "v.mountPath == '/tmp'",
            # Resources（與 ResourceQuota hard 一致）
            "quantity('250m')",
            "quantity('256Mi')",
            "quantity('1')",
            "quantity('768Mi')",
            "quantity('1Gi')",
            # 禁止 host namespace / privilege
            "hostNetwork",
            "hostPID",
            "hostIPC",
            "hostPath",
            # 禁止 host port / application envFrom / env / ports
            "ports.size() == 0",
            "env.size() == 0",
            "envFrom.size() == 0",
        )
        missing = [n for n in required_needles if n not in joined]
        self.assertEqual(
            missing,
            [],
            f"admission CEL 缺少 brief/Task 4 對齊欄位：{missing}",
        )

    # ------------------------------------------------------------------
    # Worker 接線：serviceAccountName + disabled Kali env
    # ------------------------------------------------------------------
    def test_worker_deployment_uses_kali_orchestrator_service_account(self):
        for doc in _documents("04-backend.yaml"):
            if (
                doc.get("kind") == "Deployment"
                and doc["metadata"]["name"] == "worker"
            ):
                self.assertEqual(
                    doc["spec"]["template"]["spec"]["serviceAccountName"],
                    "argus-worker-kali-orchestrator",
                )
                return
        self.fail("worker Deployment 不存在於 04-backend.yaml")

    def test_config_map_disables_kali_runtime(self):
        for doc in _documents("01-namespace-config.yaml"):
            if (
                doc.get("kind") == "ConfigMap"
                and doc["metadata"]["name"] == "argus-config"
            ):
                data = doc["data"]
                self.assertEqual(data["ARGUS_KALI_ENABLED"], "false")
                self.assertEqual(data["ARGUS_KALI_BACKEND"], "disabled")
                self.assertEqual(data["ARGUS_KALI_NAMESPACE"], "argus-kali")
                self.assertEqual(
                    data["ARGUS_KALI_RUNNER_IMAGE"], DISABLED_SENTINEL
                )
                return
        self.fail("argus-config ConfigMap 不存在於 01-namespace-config.yaml")

    # ------------------------------------------------------------------
    # Kustomization 收錄新 manifest
    # ------------------------------------------------------------------
    def test_kustomization_includes_new_manifests(self):
        kustomization = _documents("kustomization.yaml")[0]
        resources = kustomization["resources"]
        self.assertIn("10-kali-runtime.yaml", resources)
        self.assertIn("11-kali-admission.yaml", resources)


if __name__ == "__main__":
    unittest.main()
