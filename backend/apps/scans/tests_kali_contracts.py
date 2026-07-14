"""Kali 共用結果契約、runner 邊界與 URL 遮罩測試。"""

from django.test import SimpleTestCase

from apps.scans.security.kali_contracts import (
    KaliResult,
    KaliResultContractError,
    ReservedSqlmapTarget,
    parse_runner_result,
    redact_url_query_values,
)


class KaliContractTests(SimpleTestCase):
    def test_query_values_are_redacted_but_keys_and_origin_remain(self):
        value = redact_url_query_values(
            "https://shop.example/search?q=secret&id=42#fragment"
        )
        self.assertEqual(
            value,
            "https://shop.example/search?q=%5BREDACTED%5D&id=%5BREDACTED%5D",
        )

    def test_result_dict_is_additive_and_never_exposes_raw_stdout(self):
        result = KaliResult(
            ok=True,
            returncode=0,
            stdout="raw sqlmap output",
            confirmed=True,
            evidence_summary={
                "parameter": "id",
                "techniques": ["boolean-based blind"],
            },
        ).as_dict()
        self.assertEqual(
            set(result),
            {
                "ok",
                "tool",
                "blocked_reason",
                "returncode",
                "stdout",
                "error",
                "confirmed",
                "evidence_summary",
            },
        )
        self.assertEqual(result["stdout"], "")

    def test_runner_payload_rejects_unknown_fields_and_oversize(self):
        target = ReservedSqlmapTarget(0, "https://example.test/?id=1", "abc")
        with self.assertRaises(KaliResultContractError):
            parse_runner_result(
                b'{"schema_version":1,"tool":"sqlmap","results":[],"raw":"forbidden"}',
                [target],
            )
        with self.assertRaises(KaliResultContractError):
            parse_runner_result(b"x" * 16385, [target])
