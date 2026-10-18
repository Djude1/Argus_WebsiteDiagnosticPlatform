"""Finding 跨掃描正典身分（finding_identity.py，ADR-0006 決策 A）。

鎖定核心承諾：同一個洞不論被確定性規則還是 Agent 打到、不論措辭或掛載前綴如何，
都收斂成同一把跨掃描鍵；不同弱點類型／不同資源不會被誤併。
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.finding_identity import canonical_resource, finding_identity
from apps.scans.security import owasp_mapper


def _agent(title, description="", *, endpoint="", owasp="", cwe=""):
    """模擬 Agent 觀察發現的 dict（雜湊 rule_id、端點存在 observed_endpoint）。"""
    return {
        "category": "security",
        "rule_id": "agent-observed-security-abc123",
        "title": title,
        "description": description,
        "owasp_category": owasp,
        "cwe_id": cwe,
        "evidence_json": {"observed_endpoint": endpoint} if endpoint else {},
    }


class CanonicalResourceTests(SimpleTestCase):
    def test_strips_mount_prefix(self):
        # 反向代理／直連前綴剝掉後是同一後端資源
        self.assertEqual(canonical_resource("/api_proxy/visits"), "/visits")
        self.assertEqual(canonical_resource("/backend/visits"), "/visits")
        self.assertEqual(
            canonical_resource("/api_proxy/visits"), canonical_resource("/backend/visits")
        )

    def test_numeric_segment_collapses(self):
        # IDOR 枚舉：同端點不同物件 id 是同一資源
        self.assertEqual(canonical_resource("/api/users/1"), canonical_resource("/api/users/2"))
        self.assertEqual(canonical_resource("/shop/p/1043-117736"), "/shop/p/#")

    def test_query_and_trailing_slash_and_case(self):
        self.assertEqual(canonical_resource("/Shop/Products/?q=1"), "/shop/products")

    def test_rest_is_a_mount_prefix(self):
        # juice-shop 的 /rest/* 是反向代理掛載前綴，剝掉後是後端資源
        self.assertEqual(canonical_resource("/rest/products/search"), "/products/search")

    def test_bare_mount_not_stripped(self):
        # 裸 /api（後面沒有資源）不剝
        self.assertEqual(canonical_resource("/api"), "/api")

    def test_root_and_empty(self):
        self.assertEqual(canonical_resource("/"), "/")
        self.assertEqual(canonical_resource(""), "")


class FindingIdentityTests(SimpleTestCase):
    def test_same_hole_different_wording_same_key(self):
        # 同端點、同弱點類別，措辭不同 → 同鍵（Agent 重掃改字不應變成新問題）
        a = _agent("IDOR：可讀取他人訂單", endpoint="/api/orders/5", owasp="A01", cwe="CWE-639")
        b = _agent("越權存取：枚舉其他使用者的訂單資料", endpoint="/api/orders/9",
                   owasp="A01", cwe="CWE-639")
        self.assertEqual(finding_identity(a), finding_identity(b))

    def test_different_mount_prefix_same_key(self):
        # 確定性層（/backend/visits）與 Agent 層（/api_proxy/visits）同一後端資源 → 同鍵
        deterministic = {
            "category": "security", "rule_id": "exposure-file-data",
            "title": "內網 IP 外洩", "description": "回應夾帶內部網段位址",
            "owasp_category": "A01", "cwe_id": "CWE-200",
            "evidence_json": {"endpoint": "/backend/visits"},
        }
        agent = _agent("API 回應洩漏內網 IP", endpoint="/api_proxy/visits",
                       owasp="A01", cwe="CWE-200")
        self.assertEqual(finding_identity(deterministic), finding_identity(agent))

    def test_different_vuln_class_different_key(self):
        # 同端點但 SQL 注入 vs 缺授權＝不同問題、修法不同 → 不同鍵
        sqli = _agent("SQL 注入", endpoint="/api/search", owasp="A03", cwe="CWE-89")
        authz = _agent("未授權存取", endpoint="/api/search", owasp="A01", cwe="CWE-862")
        self.assertNotEqual(finding_identity(sqli), finding_identity(authz))

    def test_different_resource_different_key(self):
        a = _agent("未授權存取", endpoint="/api/orders", owasp="A01", cwe="CWE-862")
        b = _agent("未授權存取", endpoint="/api/invoices", owasp="A01", cwe="CWE-862")
        self.assertNotEqual(finding_identity(a), finding_identity(b))

    def test_non_security_uses_rule_id(self):
        seo = {"category": "seo", "rule_id": "seo-missing-title", "title": "缺少標題"}
        self.assertEqual(finding_identity(seo), "seo-missing-title")

    def test_site_level_other_falls_back_to_title(self):
        # 無資源、無類別、無標籤的站台層級資安問題不應互相誤併
        a = {"category": "security", "rule_id": "x", "title": "問題甲", "description": ""}
        b = {"category": "security", "rule_id": "y", "title": "問題乙", "description": ""}
        self.assertNotEqual(finding_identity(a), finding_identity(b))


class AgentOwaspTagTests(SimpleTestCase):
    def test_agent_hash_rule_tagged_by_vuln_class(self):
        # Agent 雜湊 rule_id 精確表查不到 → 退回弱點類別補標籤
        tagged = owasp_mapper.tag(_agent("IDOR：越權讀取他人資料"))
        self.assertEqual(tagged["owasp_category"], "A01")
        self.assertEqual(tagged["cwe_id"], "CWE-639")

    def test_deterministic_rule_unaffected_by_agent_fallback(self):
        # 非 Agent 的確定性 security finding 查不到精確對映時，維持空（不套 vuln_class 退回）
        f = {"category": "security", "rule_id": "totally-unknown-rule",
             "title": "SQL 注入", "description": ""}
        tagged = owasp_mapper.tag(f)
        self.assertEqual(tagged["owasp_category"], "")
        self.assertEqual(tagged["cwe_id"], "")
