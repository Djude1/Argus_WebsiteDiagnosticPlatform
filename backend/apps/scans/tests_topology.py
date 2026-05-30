"""T15 後端拓撲 API 測試。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.scans.models import Finding, Page, ScanJob


class ScanTopologyApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="topo_user", password="safe-test-password"
        )
        self.client.force_authenticate(self.user)
        self.scan = ScanJob.objects.create(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
            status=ScanJob.Status.COMPLETED,
        )
        # 3 個 page，page_a → page_b, page_b → page_c, page_a → page_c
        self.page_a = Page.objects.create(
            scan_job=self.scan,
            url="https://example.com/",
            final_url="https://example.com/",
            origin="https://example.com",
            depth=0,
            status_code=200,
            outgoing_links=["https://example.com/b", "https://example.com/c"],
        )
        self.page_b = Page.objects.create(
            scan_job=self.scan,
            url="https://example.com/b",
            final_url="https://example.com/b",
            origin="https://example.com",
            depth=1,
            status_code=200,
            outgoing_links=["https://example.com/c", "https://external.com/x"],
        )
        self.page_c = Page.objects.create(
            scan_job=self.scan,
            url="https://example.com/c",
            final_url="https://example.com/c",
            origin="https://example.com",
            depth=2,
            status_code=200,
            outgoing_links=[],
        )
        Finding.objects.create(
            scan_job=self.scan,
            page=self.page_b,
            category=Finding.Category.SECURITY,
            severity=Finding.Severity.CRITICAL,
            title="CSP 缺失",
            description="x",
            remediation="x",
            ai_handoff_prompt="x",
        )
        Finding.objects.create(
            scan_job=self.scan,
            page=self.page_b,
            category=Finding.Category.SEO,
            severity=Finding.Severity.LOW,
            title="alt 缺失",
            description="x",
            remediation="x",
            ai_handoff_prompt="x",
        )

    def _url(self):
        return reverse("scan-topology", kwargs={"pk": self.scan.id})

    def test_returns_nodes_and_edges(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(len(data["nodes"]), 3)
        self.assertEqual(len(data["edges"]), 3)  # a→b, a→c, b→c（external 過濾掉）

    def test_node_includes_finding_stats_and_tone(self):
        resp = self.client.get(self._url())
        data = resp.json()
        nodes_by_id = {n["id"]: n for n in data["nodes"]}
        self.assertEqual(nodes_by_id[self.page_b.id]["finding_count"], 2)
        self.assertEqual(nodes_by_id[self.page_b.id]["max_severity"], "critical")
        self.assertEqual(nodes_by_id[self.page_b.id]["tone"], "bad")
        # page_a 與 page_c 無 finding → good
        self.assertEqual(nodes_by_id[self.page_a.id]["tone"], "good")
        self.assertIsNone(nodes_by_id[self.page_a.id]["max_severity"])

    def test_external_links_excluded_from_edges(self):
        resp = self.client.get(self._url())
        edges = resp.json()["edges"]
        # 確認沒有指向 external.com 的 edge（無對應 page id）
        target_ids = {e["target"] for e in edges}
        self.assertTrue(target_ids.issubset({self.page_b.id, self.page_c.id}))

    def test_requires_auth(self):
        self.client.logout()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_other_user_cannot_access(self):
        other = get_user_model().objects.create_user(
            username="other_user", password="safe-test-password"
        )
        self.client.force_authenticate(other)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
