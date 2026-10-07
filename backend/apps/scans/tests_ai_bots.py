"""AI 爬蟲的 robots.txt 政策（ai_bots.py）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.ai_bots import (
    ALLOWED,
    BLOCKED,
    PARTIAL,
    SEARCH,
    TRAINING,
    analyze_policy,
    blocked,
    parse_groups,
    summary_line,
)


def _status(policy, agent):
    return next(b for b in policy["bots"] if b["agent"] == agent)


class PolicyTests(SimpleTestCase):
    def test_no_robots_allows_everything(self):
        policy = analyze_policy(None)
        self.assertFalse(policy["robots_found"])
        self.assertEqual({b["status"] for b in policy["bots"]}, {ALLOWED})
        self.assertEqual(summary_line(policy), "沒有 robots.txt，所有 AI 爬蟲都可抓取")

    def test_named_group_overrides_wildcard(self):
        robots = "User-agent: *\nDisallow: /\n\nUser-agent: OAI-SearchBot\nAllow: /\n"
        policy = analyze_policy(robots)
        self.assertEqual(_status(policy, "OAI-SearchBot")["status"], ALLOWED)
        self.assertTrue(_status(policy, "OAI-SearchBot")["explicit"])
        # 沒點名的 bot 用 * 群組
        self.assertEqual(_status(policy, "GPTBot")["status"], BLOCKED)
        self.assertFalse(_status(policy, "GPTBot")["explicit"])

    def test_exact_product_token_not_substring(self):
        # 「ClaudeBot」群組不會套到 Claude-SearchBot／Claude-User
        # （Python 內建 robotparser 會用子字串比對）
        policy = analyze_policy("User-agent: ClaudeBot\nDisallow: /\n")
        self.assertEqual(_status(policy, "ClaudeBot")["status"], BLOCKED)
        self.assertEqual(_status(policy, "Claude-SearchBot")["status"], ALLOWED)

    def test_grouped_agents_and_comments(self):
        robots = (
            "# 不讓模型訓練\n"
            "User-agent: GPTBot\nUser-agent: Google-Extended  # Gemini\nDisallow: /\n"
        )
        policy = analyze_policy(robots)
        self.assertEqual(_status(policy, "GPTBot")["status"], BLOCKED)
        self.assertEqual(_status(policy, "Google-Extended")["status"], BLOCKED)
        self.assertEqual(blocked(policy, SEARCH), [])
        self.assertEqual({b["agent"] for b in blocked(policy, TRAINING)},
                         {"GPTBot", "Google-Extended"})

    def test_partial_and_longest_match(self):
        robots = (
            "User-agent: PerplexityBot\nDisallow: /members/\n\n"
            "User-agent: CCBot\nDisallow: /\nAllow: /$\n"
        )
        policy = analyze_policy(robots)
        self.assertEqual(_status(policy, "PerplexityBot")["status"], PARTIAL)
        # Allow: /$ 比 Disallow: / 長，首頁允許、其他頁封鎖 → 部分限制
        self.assertEqual(_status(policy, "CCBot")["status"], PARTIAL)

    def test_empty_disallow_means_allow(self):
        policy = analyze_policy("User-agent: *\nDisallow:\n")
        self.assertEqual({b["status"] for b in policy["bots"]}, {ALLOWED})

    def test_parse_groups(self):
        groups = parse_groups(
            "User-agent: A\nUser-agent: B\nDisallow: /x\nUser-agent: C\nAllow: /\n"
        )
        self.assertEqual(groups, [({"a", "b"}, [(False, "/x")]), ({"c"}, [(True, "/")])])

    def test_summary_line(self):
        policy = analyze_policy("User-agent: GPTBot\nDisallow: /\n")
        self.assertEqual(
            summary_line(policy),
            "模型訓練：封鎖 GPTBot；AI 搜尋與回答：未封鎖；使用者觸發讀取：未封鎖",
        )
