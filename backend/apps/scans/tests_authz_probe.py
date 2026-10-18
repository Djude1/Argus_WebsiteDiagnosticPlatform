"""未授權存取探測分析測試（security/authz_probe.py）。

重點在誤報防線：公開 JSON API 很常見，只有「成批記錄＋身分欄位＋內部帳號欄位」才算。
"""

from __future__ import annotations

import json

from django.test import SimpleTestCase

from apps.scans.security.authz_probe import (
    analyze_idor_results,
    analyze_unauthorized_results,
    expand_idor_candidates,
)


def _result(body, *, status=200, ctype="application/json", url="https://site.example.test/svc/members/all"):
    return {"url": url, "status": status, "content_type": ctype,
            "body": body if isinstance(body, str) else json.dumps(body)}


# 成批成員記錄：身分（name）＋內部（memberId／roleId／啟用狀態）→ 應報
_MEMBER_DUMP = {
    "result": True,
    "data": [
        {"memberId": "M001", "name": "甲", "roleId": 1, "roleName": "管理員", "isActive": True},
        {"memberId": "M002", "name": "乙", "roleId": 2, "roleName": "助理", "isActive": False},
    ],
}


class AnalyzeUnauthorizedResultsTests(SimpleTestCase):
    def test_member_dump_flagged(self):
        findings = analyze_unauthorized_results([_result(_MEMBER_DUMP)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "security-unauth-api-records")
        # 名單無 email／電話 → medium（保守）
        self.assertEqual(findings[0]["severity"], "medium")

    def test_pii_escalates_to_high(self):
        body = {
            "data": [
                {"memberId": "M001", "name": "甲", "roleName": "師", "email": "a@x.example.test"},
                {"memberId": "M002", "name": "乙", "roleName": "師", "email": "b@x.example.test"},
            ]
        }
        findings = analyze_unauthorized_results([_result(body)])
        self.assertEqual(findings[0]["severity"], "high")

    def test_password_field_escalates_to_high(self):
        body = [
            {"userId": 1, "username": "a", "password": "x"},
            {"userId": 2, "username": "b", "password": "y"},
        ]
        findings = analyze_unauthorized_results([_result(body)])
        self.assertEqual(findings[0]["severity"], "high")

    def test_sensitive_keys_alone_flagged_without_identity_internal(self):
        # 只有 token 欄位、沒有一般身分／內部欄位，也必須報（絕不可能刻意成批公開）
        body = [{"token": "aaa"}, {"token": "bbb"}]
        findings = analyze_unauthorized_results([_result(body)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_national_id_in_body_flagged_without_internal_keys(self):
        # 成批身分證（強個資）即使欄位名看不出內部性質也要報
        body = [{"n": "甲", "pid": "A123456789"}, {"n": "乙", "pid": "A123456789"}]
        findings = analyze_unauthorized_results([_result(body)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    # —— 誤報防線 ——
    def test_public_directory_without_internal_keys_not_flagged(self):
        # 公開人員目錄：只有姓名職稱、沒有內部 id／帳號狀態 → 不報
        body = [
            {"name": "張老師", "title": "教授"},
            {"name": "李老師", "title": "副教授"},
        ]
        self.assertEqual(analyze_unauthorized_results([_result(body)]), [])

    def test_name_email_without_internal_keys_not_flagged(self):
        # 只有姓名＋email、沒有內部帳號欄位 → 與公開聯絡清單無法區分，不報（弱個資不單獨成立）
        body = [
            {"name": "張三", "email": "a@x.example.test"},
            {"name": "李四", "email": "b@x.example.test"},
        ]
        self.assertEqual(analyze_unauthorized_results([_result(body)]), [])

    def test_public_product_list_not_flagged(self):
        # 公開商品清單：有 id 但沒有身分欄位 → 不報
        body = {"data": [{"id": 1, "price": 100}, {"id": 2, "price": 200}]}
        self.assertEqual(analyze_unauthorized_results([_result(body)]), [])

    def test_single_record_not_flagged(self):
        # 單筆（例如自己的個人資料端點）不是成批外洩
        body = [{"memberId": "M001", "name": "甲", "roleName": "師"}]
        self.assertEqual(analyze_unauthorized_results([_result(body)]), [])

    def test_non_200_not_flagged(self):
        self.assertEqual(
            analyze_unauthorized_results([_result(_MEMBER_DUMP, status=401)]), []
        )

    def test_non_json_not_flagged(self):
        self.assertEqual(
            analyze_unauthorized_results([_result("<html>hi</html>", ctype="text/html")]), []
        )

    def test_empty_results(self):
        self.assertEqual(analyze_unauthorized_results([]), [])


def _obj(body, *, status=200, ctype="application/json", url=""):
    return {"url": url, "status": status, "content_type": ctype,
            "body": body if isinstance(body, str) else json.dumps(body)}


class ExpandIdorCandidatesTests(SimpleTestCase):
    def test_parent_collection_and_neighbor_ids(self):
        extra = expand_idor_candidates(["https://site.example.test/svc/users/29"])
        # 父集合（成批外洩）
        self.assertIn("https://site.example.test/svc/users", extra)
        # 鄰近 id（IDOR 枚舉）＋觀察到的 29
        for i in (1, 2, 3, 29):
            self.assertIn(f"https://site.example.test/svc/users/{i}", extra)

    def test_non_numeric_tail_ignored(self):
        # 結尾非純數字（slug／uuid）不展開，避免誤報與請求量爆開
        self.assertEqual(expand_idor_candidates(["https://site.example.test/svc/about"]), [])
        self.assertEqual(expand_idor_candidates(["https://site.example.test/svc/u/abc-def"]), [])

    def test_each_template_expanded_once(self):
        extra = expand_idor_candidates([
            "https://site.example.test/svc/users/1",
            "https://site.example.test/svc/users/2",  # 同模板，不重複展開
        ])
        self.assertEqual(extra.count("https://site.example.test/svc/users"), 1)


class AnalyzeIdorResultsTests(SimpleTestCase):
    def _id(self, ident, body):
        return _obj(body, url=f"https://site.example.test/svc/users/{ident}")

    def test_enumerable_user_objects_flagged(self):
        # 兩個不同 id 未授權都回內容互異、帶身分＋內部欄位的單筆物件 → IDOR
        results = [
            self._id(1, {"id": 1, "username": "a", "roleId": 1, "isActive": True}),
            self._id(2, {"id": 2, "username": "b", "roleId": 2, "isActive": False}),
        ]
        findings = analyze_idor_results(results)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "security-idor-enumerable-object")

    def test_pii_escalates_to_high(self):
        results = [
            self._id(1, {"id": 1, "name": "甲", "roleName": "師", "email": "a@x.example.test"}),
            self._id(2, {"id": 2, "name": "乙", "roleName": "師", "email": "b@x.example.test"}),
        ]
        self.assertEqual(analyze_idor_results(results)[0]["severity"], "high")

    def test_wrapped_single_object(self):
        # {data:{...}} 包一層的單筆物件也算
        results = [
            self._id(1, {"data": {"id": 1, "account": "a", "memberId": "M1", "status": "on"}}),
            self._id(2, {"data": {"id": 2, "account": "b", "memberId": "M2", "status": "off"}}),
        ]
        self.assertEqual(len(analyze_idor_results(results)), 1)

    # —— 誤報防線 ——
    def test_public_product_by_id_not_flagged(self):
        # 公開 /產品/:id 目錄：無身分／內部／個資欄位 → 不報
        results = [
            self._id(1, {"id": 1, "name": "蘋果", "price": 100}),
            self._id(2, {"id": 2, "name": "香蕉", "price": 50}),
        ]
        self.assertEqual(analyze_idor_results(results), [])

    def test_same_body_for_all_ids_not_flagged(self):
        # 所有 id 回同一頁（SPA／靜態）→ 不是逐物件資料，不報
        same = {"id": 0, "username": "x", "roleId": 1, "isActive": True}
        results = [self._id(1, same), self._id(2, same)]
        self.assertEqual(analyze_idor_results(results), [])

    def test_single_id_not_flagged(self):
        # 只有一個 id 回 200 → 無法證明可枚舉
        results = [
            self._id(1, {"id": 1, "username": "a", "roleId": 1, "isActive": True}),
            self._id(2, {"x": 1}, ),
        ]
        results[1]["status"] = 401
        self.assertEqual(analyze_idor_results(results), [])

    def test_top_level_list_left_to_batch_check(self):
        # 頂層陣列（成批名單）不在 IDOR 範圍，交給 analyze_unauthorized_results
        results = [
            self._id(1, [{"username": "a", "roleId": 1}, {"username": "b", "roleId": 2}]),
            self._id(2, [{"username": "c", "roleId": 3}, {"username": "d", "roleId": 4}]),
        ]
        self.assertEqual(analyze_idor_results(results), [])

    def test_non_200_ignored(self):
        results = [
            self._id(1, {"id": 1, "username": "a", "roleId": 1}),
            _obj({"id": 2, "username": "b", "roleId": 2}, status=403,
                 url="https://site.example.test/svc/users/2"),
        ]
        self.assertEqual(analyze_idor_results(results), [])


class MaxEndpointsSettingTests(SimpleTestCase):
    def test_default_and_override(self):
        from django.test import override_settings

        from apps.scans.security.authz_probe import _max_endpoints

        self.assertEqual(_max_endpoints(), 60)  # 預設放寬值
        with override_settings(ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS=10):
            self.assertEqual(_max_endpoints(), 10)
        with override_settings(ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS=0):
            self.assertEqual(_max_endpoints(), 1)  # 下限 1
