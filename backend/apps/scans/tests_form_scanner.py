"""密碼欄位未遮蔽（security/form_scanner.py，2026-10-16）。"""

from django.test import SimpleTestCase

from apps.scans.security import owasp_mapper
from apps.scans.security.finding_kind import security_kind
from apps.scans.security.form_scanner import (
    RULE_ID,
    analyze_password_fields,
    find_unmasked_password_fields,
)

# ntubimdbirc.tw /management/login 實際的標記（2026-10-16 抓取，class 名稱節錄）
NTUB_LOGIN = (
    '<div class="Login_wrap"><p class="Login_title">登入</p>'
    '<div class="InputField_wrap"><p class="InputField_title">帳號</p>'
    '<input type="text" class="InputField_field"/></div>'
    '<div class="InputField_wrap"><p class="InputField_title">密碼</p>'
    '<input type="text" class="InputField_field"/></div>'
    '<button class="Login_button">登入</button>'
    '<a href="/management/register">沒有帳號?立即註冊</a></div>'
)


class UnmaskedPasswordFieldTests(SimpleTestCase):
    def test_caption_before_field_counts(self):
        fields = find_unmasked_password_fields(NTUB_LOGIN)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["caption"], "密碼")

    def test_detected_by_name_label_placeholder_or_autocomplete(self):
        for html in (
            '<input name="user_password">',
            '<input type="text" id="pwd">',
            '<label for="p">Password</label><input id="p" type="text">',
            '<input type="text" placeholder="請輸入密碼">',
            '<input type="text" autocomplete="current-password" name="x">',
        ):
            with self.subTest(html=html):
                self.assertEqual(len(find_unmasked_password_fields(html)), 1)

    def test_masked_or_unrelated_fields_ignored(self):
        for html in (
            '<input type="password" name="password">',
            '<input type="hidden" name="password_reset_token" value="x">',
            '<input type="email" placeholder="密碼重設信會寄到這裡">',
            '<input type="text" name="passport_no">',
            '<input type="text" name="bypass">',
            '<p>密碼</p><input type="text" placeholder="請輸入簡訊驗證碼">',
            # 欄位前是整段說明文字，不是欄位標題
            '<p>忘記密碼時，請先輸入註冊時填寫的 Email 地址，我們會寄送重設連結。</p>'
            '<input type="text" name="email">',
            '<p>密碼</p><input type="password"><input type="text" name="nickname">',
        ):
            with self.subTest(html=html):
                self.assertEqual(find_unmasked_password_fields(html), [])

    def test_finding_shape(self):
        findings = analyze_password_fields(NTUB_LOGIN, "https://ntubimdbirc.tw/management/login")
        self.assertEqual(len(findings), 1)
        finding = owasp_mapper.tag(findings[0])
        self.assertEqual(finding["rule_id"], RULE_ID)
        self.assertEqual(finding["category"], "security")
        self.assertEqual(finding["severity"], "medium")
        self.assertEqual((finding["owasp_category"], finding["cwe_id"]), ("A06", "CWE-549"))
        self.assertIn("欄位標題：密碼", finding["evidence"])
        self.assertEqual(security_kind(category="security", rule_id=RULE_ID), "config")
        self.assertEqual(analyze_password_fields("<input type='password'>", "u"), [])
