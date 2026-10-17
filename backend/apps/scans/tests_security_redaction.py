"""掃描證據共用遮罩工具測試。"""

from django.test import SimpleTestCase

from apps.scans.security.redaction import (
    mask_sensitive_value,
    redact_pii_in_text,
    redact_url_query_values,
    redact_warning_summary,
)


class SecurityRedactionTests(SimpleTestCase):
    def test_redacts_url_query_values_and_fragment(self):
        redacted = redact_url_query_values(
            "/api/items?token=secret&email=person@example.com#private"
        )

        self.assertEqual(
            redacted,
            "/api/items?token=%5BREDACTED%5D&email=%5BREDACTED%5D",
        )

    def test_redacts_pii_in_arbitrary_text(self):
        redacted = redact_pii_in_text(
            "email=person@example.com phone=0912-345-678 id=A123456789"
        )

        self.assertNotIn("person@example.com", redacted)
        self.assertNotIn("0912-345-678", redacted)
        self.assertNotIn("A123456789", redacted)

    def test_masks_short_sensitive_value_without_echoing_it(self):
        self.assertNotEqual(mask_sensitive_value("abc123"), "abc123")
        self.assertEqual(mask_sensitive_value(""), "")

    def test_redacts_nested_crawler_warning_before_persistence(self):
        warning = {
            "failed_urls": [
                {
                    "url": (
                        "https://example.com/account?"
                        "token=secret-value&email=person@example.com#private"
                    ),
                    "reason": "owner=person@example.com",
                }
            ]
        }

        redacted = redact_warning_summary(warning)
        rendered = str(redacted)

        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("person@example.com", rendered)
        self.assertNotIn("#private", rendered)
        self.assertIn("%5BREDACTED%5D", redacted["failed_urls"][0]["url"])


class CardRedactionPrecisionTests(SimpleTestCase):
    """卡號遮罩只遮通過 Luhn 與卡組織規則的數字串（2026-10-17 實掃：網址頁面編號被遮掉）。"""

    def test_page_number_in_url_is_not_masked(self):
        url = "https://example.com/p/404-1043-117736.php?Lang=zh-tw"
        self.assertEqual(redact_pii_in_text(f"失效連結：{url}"), f"失效連結：{url}")

    def test_real_card_number_still_masked(self):
        masked = redact_pii_in_text("卡號 4111 1111 1111 1111")
        self.assertNotIn("4111 1111 1111 1111", masked)
        self.assertIn("4111********1111", masked)
