"""跨層資安發現去重測試（security/cross_layer.py）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.agent.findings import agent_security_rule_id
from apps.scans.security.cross_layer import consolidate_cross_layer


def _exposure(endpoint: str, rule_id: str = "exposure-file-apidoc") -> dict:
    return {
        "category": "security",
        "severity": "high",
        "rule_id": rule_id,
        "title": "敏感檔案外洩：API 文件",
        "description": f"發現可公開存取的 API 文件：https://site.example.test{endpoint}。",
        "evidence_source": "exposure_probe",
        "impact_area": "information_exposure",
        "evidence_json": {"endpoint": endpoint},
    }


def _agent(endpoint: str, title: str = "OpenAPI 規格未授權可讀導致後端結構洩漏") -> dict:
    url = f"https://site.example.test{endpoint}"
    return {
        "category": "security",
        "severity": "high",
        "rule_id": agent_security_rule_id(title, "openapi 規格匿名可讀", url),
        "title": title,
        "description": "AI Agent 觀察到規格匿名可讀",
        "evidence_source": "hermes_agent",
        "evidence_json": {"source": "hermes_agent", "observed_endpoint": endpoint},
    }


class ConsolidateCrossLayerTests(SimpleTestCase):
    def test_same_endpoint_drops_agent_keeps_deterministic(self):
        det = _exposure("/svc/v3/api-docs")
        agent = _agent("/svc/v3/api-docs")
        kept, dropped = consolidate_cross_layer([det, agent])
        self.assertIn(det, kept)
        self.assertNotIn(agent, kept)
        self.assertEqual(dropped, [agent])

    def test_agent_wording_with_unauthorized_still_merged(self):
        # Agent 標題含「未授權」（弱點類型會被歸 auth），端點相同仍要併掉
        det = _exposure("/svc/v3/api-docs")
        agent = _agent("/svc/v3/api-docs", title="/v3/api-docs 未授權存取")
        kept, dropped = consolidate_cross_layer([det, agent])
        self.assertEqual(dropped, [agent])

    def test_different_endpoint_keeps_both(self):
        # /alt 前綴的 api-docs 沒有對應確定性發現（確定性只探到 /svc），保留
        det = _exposure("/svc/v3/api-docs")
        agent = _agent("/alt/v3/api-docs")
        kept, dropped = consolidate_cross_layer([det, agent])
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 2)

    def test_agent_without_endpoint_kept(self):
        det = _exposure("/svc/v3/api-docs")
        agent = _agent("/svc/v3/api-docs")
        agent["evidence_json"]["observed_endpoint"] = ""
        kept, dropped = consolidate_cross_layer([det, agent])
        self.assertEqual(dropped, [])
        self.assertIn(agent, kept)

    def test_non_exposure_deterministic_does_not_merge(self):
        # 同端點但確定性那筆不是「檔案外洩」類（例如 CORS），不以端點併掉 Agent 發現
        cors = {
            "category": "security",
            "severity": "low",
            "rule_id": "api-cors-wildcard",
            "title": "API 允許任意來源跨域",
            "evidence_json": {"endpoint": "/svc/data"},
        }
        agent = _agent("/svc/data", title="SQL 注入")
        kept, dropped = consolidate_cross_layer([cors, agent])
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 2)

    def test_agent_only_kept(self):
        agent = _agent("/svc/members/all", title="未授權成員資料 API")
        kept, dropped = consolidate_cross_layer([agent])
        self.assertEqual(dropped, [])
        self.assertIn(agent, kept)


def _agent_sev(endpoint: str, severity: str, title: str) -> dict:
    url = f"https://site.example.test{endpoint}"
    return {
        "category": "security",
        "severity": severity,
        "rule_id": agent_security_rule_id(title, "", url),
        "title": title,
        "description": "AI Agent 觀察",
        "evidence_source": "hermes_agent",
        "evidence_json": {"source": "hermes_agent", "observed_endpoint": endpoint},
    }


class AgentCrossPathMergeTests(SimpleTestCase):
    """同一後端資源的兩種掛載路徑（/api_proxy/* 與 /backend/*）在 Agent 層各報一次時合併。"""

    def test_same_resource_different_mount_keeps_most_severe(self):
        # 同一個 visits 錯誤洩內網 IP：/api_proxy/visits（高）與 /backend/visits（低）＝同一件事
        high = _agent_sev("/api_proxy/visits", "high", "錯誤訊息洩漏內部後端 IP 與完整 URL")
        low = _agent_sev("/backend/visits", "low", "Spring Boot 錯誤訊息洩漏內部伺服器位址")
        kept, dropped = consolidate_cross_layer([high, low])
        self.assertIn(high, kept)
        self.assertNotIn(low, kept)
        self.assertEqual(dropped, [low])

    def test_most_severe_wins_regardless_of_order(self):
        low = _agent_sev("/backend/visits", "low", "錯誤訊息洩漏內部伺服器位址")
        high = _agent_sev("/api_proxy/visits", "high", "錯誤訊息洩漏內部後端 IP")
        kept, dropped = consolidate_cross_layer([low, high])
        self.assertIn(high, kept)
        self.assertEqual(dropped, [low])

    def test_different_vuln_class_not_merged(self):
        # 同資源但一個是外洩、一個是 SQL 注入：修法不同，不能併
        leak = _agent_sev("/api_proxy/orders", "medium", "錯誤訊息洩漏內部位址")
        sqli = _agent_sev("/backend/orders", "high", "SQL 注入可取得資料庫內容")
        kept, dropped = consolidate_cross_layer([leak, sqli])
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 2)

    def test_different_resource_not_merged(self):
        a = _agent_sev("/backend/visits", "medium", "錯誤訊息洩漏內部位址")
        b = _agent_sev("/backend/orders", "medium", "錯誤訊息洩漏內部位址")
        kept, dropped = consolidate_cross_layer([a, b])
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 2)

    def test_non_mount_first_segment_not_stripped(self):
        # /shop 不是掛載前綴，/shop/items 與 /backend/items 不是同一資源
        shop = _agent_sev("/shop/items", "medium", "錯誤訊息洩漏內部位址")
        backend = _agent_sev("/backend/items", "medium", "錯誤訊息洩漏內部位址")
        kept, dropped = consolidate_cross_layer([shop, backend])
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 2)

    def test_bare_mount_segment_not_merged(self):
        # 只有掛載詞本身（/api、/backend）沒有後續資源，不剝除、不合併
        a = _agent_sev("/api", "medium", "錯誤訊息洩漏內部位址")
        b = _agent_sev("/backend", "medium", "錯誤訊息洩漏內部位址")
        kept, dropped = consolidate_cross_layer([a, b])
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 2)

    def test_deterministic_same_resource_untouched(self):
        # 確定性（非 exposure、非 Agent）發現與兩筆同資源 Agent 發現並存：
        # Agent 層內部合併只在 Agent 之間，不碰確定性那筆。
        det = {
            "category": "security",
            "severity": "medium",
            "rule_id": "api-error-stack-trace",
            "title": "API 錯誤回傳堆疊追蹤",
            "evidence_json": {"endpoint": "/backend/members/all"},
        }
        agent_a = _agent_sev("/api_proxy/members/all", "high", "成員資料未授權外洩")
        agent_b = _agent_sev("/backend/members/all", "medium", "成員資料未授權外洩")
        kept, dropped = consolidate_cross_layer([det, agent_a, agent_b])
        self.assertIn(det, kept)
        self.assertIn(agent_a, kept)
        self.assertEqual(dropped, [agent_b])
