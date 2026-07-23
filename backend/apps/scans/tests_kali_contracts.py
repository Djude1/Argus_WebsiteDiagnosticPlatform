"""Kali 共用結果契約、runner 邊界與 URL 遮罩測試。"""

import json

from django.test import SimpleTestCase, override_settings

from apps.scans.security.kali_contracts import (
    KaliResult,
    KaliResultContractError,
    ReservedSqlmapTarget,
    parse_runner_result,
    redact_url_query_values,
)


def _valid_result(**overrides):
    result = {
        "index": 0,
        "ok": True,
        "confirmed": True,
        "returncode": 0,
        "parameter": "id",
        "techniques": ["boolean-based blind"],
        "dbms": "PostgreSQL",
        "error_code": "",
    }
    result.update(overrides)
    return result


def _runner_payload(*, schema_version=1, tool="sqlmap", results=None):
    document = {
        "schema_version": schema_version,
        "tool": tool,
        "results": [_valid_result()] if results is None else results,
    }
    return json.dumps(document, separators=(",", ":")).encode()


def _target(index=0):
    return ReservedSqlmapTarget(
        index,
        f"https://example.test/?id={index}",
        f"fingerprint-{index}",
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

    def test_runner_payload_rejects_unknown_top_level_fields(self):
        with self.assertRaisesRegex(
            KaliResultContractError,
            "^invalid_top_level_fields$",
        ):
            parse_runner_result(
                b'{"schema_version":1,"tool":"sqlmap","results":[],"raw":"forbidden"}',
                [_target()],
            )

    def test_runner_payload_rejects_non_integer_schema_version(self):
        for schema_version in (True, 1.0):
            with self.subTest(schema_version=schema_version):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    "^unknown_schema$",
                ):
                    parse_runner_result(
                        _runner_payload(schema_version=schema_version),
                        [_target()],
                    )

    def test_runner_payload_maps_valid_result(self):
        payload = _runner_payload(
            results=[
                _valid_result(
                    ok=False,
                    confirmed=False,
                    returncode=None,
                    parameter="product.id",
                    techniques=["union query"],
                    dbms="MySQL 8.0",
                    error_code="runner_failed",
                )
            ]
        )

        result = parse_runner_result(payload, [_target()])[0]

        self.assertFalse(result.ok)
        self.assertFalse(result.confirmed)
        self.assertIsNone(result.returncode)
        self.assertEqual(result.error, "runner_failed")
        self.assertEqual(
            result.evidence_summary,
            {
                "parameter": "product.id",
                "techniques": ["union query"],
                "dbms": "MySQL 8.0",
            },
        )

    @override_settings(ARGUS_KALI_RESULT_MAX_BYTES=16384)
    def test_runner_payload_size_boundary_uses_valid_json(self):
        payload = _runner_payload()
        exact_limit = payload + b" " * (16384 - len(payload))
        one_byte_over = exact_limit + b" "

        self.assertEqual(len(exact_limit), 16384)
        self.assertEqual(len(one_byte_over), 16385)
        self.assertEqual(len(parse_runner_result(exact_limit, [_target()])), 1)
        self.assertIsInstance(json.loads(one_byte_over.decode()), dict)
        with self.assertRaisesRegex(
            KaliResultContractError,
            "^result_too_large$",
        ):
            parse_runner_result(one_byte_over, [_target()])

    def test_runner_payload_rejects_invalid_utf8_and_json(self):
        for payload in (b"\xff", b"not-json"):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    "^invalid_result$",
                ):
                    parse_runner_result(payload, [_target()])

    def test_runner_payload_rejects_unknown_schema_and_tool(self):
        cases = (
            _runner_payload(schema_version=2),
            _runner_payload(tool="nmap"),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    "^unknown_schema$",
                ):
                    parse_runner_result(payload, [_target()])

    def test_runner_payload_rejects_invalid_result_fields(self):
        missing_field = _valid_result()
        missing_field.pop("dbms")
        extra_field = {**_valid_result(), "raw": "forbidden"}
        for result in (missing_field, extra_field):
            with self.subTest(result=result):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    "^invalid_result_fields$",
                ):
                    parse_runner_result(_runner_payload(results=[result]), [_target()])

    def test_runner_payload_rejects_invalid_result_container_types(self):
        payloads = (
            _runner_payload(results={"index": 0}),
            _runner_payload(results=["invalid"]),
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    "^invalid_result_type$",
                ):
                    parse_runner_result(payload, [_target()])

    def test_runner_payload_rejects_missing_index(self):
        with self.assertRaisesRegex(
            KaliResultContractError,
            "^missing_index$",
        ):
            parse_runner_result(
                _runner_payload(results=[_valid_result(index=0)]),
                [_target(0), _target(1)],
            )

    def test_runner_payload_rejects_duplicate_index(self):
        with self.assertRaisesRegex(
            KaliResultContractError,
            "^duplicate_index$",
        ):
            parse_runner_result(
                _runner_payload(
                    results=[_valid_result(index=0), _valid_result(index=0)]
                ),
                [_target()],
            )

    def test_runner_payload_rejects_unexpected_and_boolean_indices(self):
        for index in (1, True):
            with self.subTest(index=index):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    "^unexpected_index$",
                ):
                    parse_runner_result(
                        _runner_payload(results=[_valid_result(index=index)]),
                        [_target()],
                    )

    def test_runner_payload_rejects_invalid_boolean_and_integer_fields(self):
        cases = (
            {"ok": 1},
            {"confirmed": 0},
            {"returncode": True},
            {"returncode": 0.0},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    "^invalid_result_type$",
                ):
                    parse_runner_result(
                        _runner_payload(results=[_valid_result(**overrides)]),
                        [_target()],
                    )

    def test_runner_payload_rejects_unsafe_result_content(self):
        cases = (
            ({"parameter": "id;drop"}, "unsafe_parameter"),
            ({"techniques": ["unknown"]}, "invalid_techniques"),
            ({"techniques": [{"raw": "forbidden"}]}, "invalid_techniques"),
            ({"dbms": "PostgreSQL\nraw"}, "unsafe_dbms"),
            ({"error_code": "Runner-Failed"}, "unsafe_error_code"),
        )
        for overrides, error_code in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(
                    KaliResultContractError,
                    f"^{error_code}$",
                ):
                    parse_runner_result(
                        _runner_payload(results=[_valid_result(**overrides)]),
                        [_target()],
                    )
