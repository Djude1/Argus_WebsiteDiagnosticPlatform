"""掃描列表「同 origin 只回最新一筆」測試。

確認：
- list 預設過濾，每 origin 只回 id 最大者
- ?include_history=true 回所有
- detail / status / topology 仍可拿任何 id（包含被列表過濾掉的舊 scan）
- 不同 origin 各自取最新，互不影響
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from apps.scans.models import ScanJob


class ScanListDedupTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dedup_user", password="safe-test-password"
        )
        self.client.force_authenticate(self.user)
        # 同 origin 兩筆：a_old 與 a_new
        self.a_old = ScanJob.objects.create(
            user=self.user,
            original_url="https://a.com/",
            normalized_url="https://a.com/",
            origin="https://a.com",
            status=ScanJob.Status.COMPLETED,
        )
        self.a_new = ScanJob.objects.create(
            user=self.user,
            original_url="https://a.com/",
            normalized_url="https://a.com/",
            origin="https://a.com",
            status=ScanJob.Status.COMPLETED,
        )
        # 不同 origin
        self.b = ScanJob.objects.create(
            user=self.user,
            original_url="https://b.com/",
            normalized_url="https://b.com/",
            origin="https://b.com",
            status=ScanJob.Status.COMPLETED,
        )

    def test_list_returns_only_latest_per_origin(self):
        resp = self.client.get("/api/scans/")
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        ids = {row["id"] for row in resp.json()}
        # a.com 只回最新（a_new），不含 a_old；b.com 全回
        self.assertEqual(ids, {self.a_new.id, self.b.id})

    def test_include_history_returns_all(self):
        resp = self.client.get("/api/scans/?include_history=true")
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        ids = {row["id"] for row in resp.json()}
        self.assertEqual(ids, {self.a_old.id, self.a_new.id, self.b.id})

    def test_detail_still_accessible_for_old_scan(self):
        # 被列表過濾掉的舊掃描，詳情頁仍能拿到（從歷史紀錄點進去要能看）
        resp = self.client.get(f"/api/scans/{self.a_old.id}/")
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.json()["id"], self.a_old.id)

    def test_status_endpoint_still_accessible_for_old_scan(self):
        resp = self.client.get(f"/api/scans/{self.a_old.id}/status/")
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

    def test_topology_endpoint_still_accessible_for_old_scan(self):
        url = reverse("scan-topology", kwargs={"pk": self.a_old.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

    def test_other_user_scans_excluded(self):
        # 另一使用者建一筆同 a.com origin 的，不應出現在當前使用者列表
        other = get_user_model().objects.create_user(
            username="other_dedup", password="safe-test-password"
        )
        ScanJob.objects.create(
            user=other,
            original_url="https://a.com/",
            normalized_url="https://a.com/",
            origin="https://a.com",
            status=ScanJob.Status.COMPLETED,
        )
        resp = self.client.get("/api/scans/")
        ids = {row["id"] for row in resp.json()}
        # 仍只有當前使用者的 a_new 與 b
        self.assertEqual(ids, {self.a_new.id, self.b.id})
