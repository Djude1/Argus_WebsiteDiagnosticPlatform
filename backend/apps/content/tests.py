from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.content.models import AppRelease, ProjectFeature, TeamMember


class ContentAPITests(APITestCase):
    def test_features_endpoint_public_and_active_only(self):
        ProjectFeature.objects.create(
            title="Hidden", description="should not show", is_active=False,
        )
        # 不登入也能讀
        response = self.client.get(reverse("content-features"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [f["title"] for f in response.data["features"]]
        self.assertNotIn("Hidden", titles)
        # data migration 0002 seed 過的 6 個 feature 至少要有
        self.assertGreaterEqual(len(titles), 6)

    def test_team_endpoint_returns_skills_array(self):
        response = self.client.get(reverse("content-team"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        members = response.data["members"]
        self.assertTrue(len(members) >= 4)
        for m in members:
            self.assertIsInstance(m["skills"], list)

    def test_team_inactive_member_hidden(self):
        TeamMember.objects.create(
            name="離職員工", role="退場", is_active=False,
        )
        response = self.client.get(reverse("content-team"))
        names = [m["name"] for m in response.data["members"]]
        self.assertNotIn("離職員工", names)

    def test_releases_endpoint_returns_latest_flag(self):
        response = self.client.get(reverse("content-releases"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        releases = response.data["releases"]
        self.assertTrue(len(releases) >= 1)
        latest = [r for r in releases if r["is_latest"]]
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["platform"], "pwa")

    def test_inactive_release_hidden(self):
        from django.utils import timezone
        AppRelease.objects.create(
            version="0.1.0", platform="pwa",
            released_at=timezone.now(), is_active=False,
        )
        response = self.client.get(reverse("content-releases"))
        versions = [r["version"] for r in response.data["releases"]]
        self.assertNotIn("0.1.0", versions)

    def test_milestones_endpoint_public_and_seeded(self):
        response = self.client.get(reverse("content-milestones"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ms = response.data["milestones"]
        self.assertGreaterEqual(len(ms), 5)  # seed migration 0006 至少 5 個
        # 每筆有必要欄位
        for m in ms:
            self.assertIn("title", m)
            self.assertIn("date", m)
            self.assertIn("icon", m)

    def test_team_member_skill_levels_and_contributions(self):
        """W2 新增的 skill_levels / contributions 欄位應該回傳給前端。"""
        response = self.client.get(reverse("content-team"))
        members = response.data["members"]
        # data migration 0004 seed 過的 4 個應有 contributions
        with_contrib = [m for m in members if m.get("contributions")]
        self.assertGreaterEqual(len(with_contrib), 1)
        for m in with_contrib:
            self.assertIsInstance(m["contributions"], list)
            self.assertIsInstance(m["skill_levels"], list)

    def test_team_seeded_with_real_members(self):
        """migration 0009：團隊頁應顯示真實組員、回傳學號，且不殘留佔位資料。"""
        response = self.client.get(reverse("content-team"))
        members = response.data["members"]
        names = [m["name"] for m in members]
        # 真實組員存在
        for real in ["侯雨利", "羅建凱", "李仕傑", "曾子睿"]:
            self.assertIn(real, names)
        # 佔位資料不殘留
        for placeholder in ["後端工程師", "前端工程師", "AI / Agent", "DevOps / QA", "組長A"]:
            self.assertNotIn(placeholder, names)
        # 學號欄位有回傳且正確
        leader = next(m for m in members if m["name"] == "侯雨利")
        self.assertEqual(leader["student_id"], "11246034")

    def test_milestones_seeded_real_timeline(self):
        """migration 0010：開發歷程應為手冊真實時程（跨 2025/12–2026/06），不殘留舊里程碑。"""
        response = self.client.get(reverse("content-milestones"))
        ms = response.data["milestones"]
        titles = [m["title"] for m in ms]
        self.assertIn("主題構思與需求分析", titles)
        self.assertIn("系統整合測試與初評", titles)
        # 舊的擠在 5 月的里程碑不應殘留
        for old in ["MVP 完成", "Hermes-Agent 上線", "電子發票 + 載具"]:
            self.assertNotIn(old, titles)
        # 時間軸應回溯到 2025（手冊起始 114/12）
        self.assertTrue(any(str(m["date"]).startswith("2025") for m in ms))
