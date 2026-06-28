"""secret_scanner 單元測試。以靶機 CEKB 真實外洩內容當輸入，驗證偵測與遮罩。"""
from django.test import SimpleTestCase

from apps.scans.security import secret_scanner

# 取自靶機 /.env、/.git/config、/admin/index.html 的真實外洩字串（測試用）
ENV_SNIPPET = """
DATABASE_URL=mongodb://cekb_admin:R3dArch1ve2024@10.0.7.13:27017/cekb_prod
REDIS_URL=redis://:CacheP@ss2024@10.0.7.20:6379/0
JWT_SECRET=jwt_FAKEcekb_R3dArch1veJWT2024SuperSecret
STRIPE_API_KEY=sk_live_FAKE_51JhMx9KZvP2lXqA8bC3dE4fG
AWS_ACCESS_KEY_ID=AKIAFAKE7H9KZVPCEKB99
SENDGRID_API_KEY=SG.FAKEcekb_send_grid_api_key.do_not_use
GOOGLE_API_KEY=AIzaFAKEcekb_google_maps_2024_do_not_use
ADMIN_PASSWORD=SuperSecret2024!
"""

GIT_CONFIG_SNIPPET = (
    '[remote "origin"]\n'
    "\turl = https://oauth2:ghp_FAKEcekb_42cb91e7c0d6438e91c583079d177a5c@github.com/x/y.git\n"
)

ADMIN_INLINE_JS = """
<script>
const VALID_USERS = { "admin": "SuperSecret2024!", "root": "R00tCekb!2024" };
const API_KEY = "sk-test-cekb-FAKE1234567890abcdef";
</script>
"""

PLACEHOLDER_ENV = """
# .env.example
DATABASE_URL=postgres://user:changeme@localhost:5432/db
API_KEY=your_api_key_here
"""


class TestDetectSecrets(SimpleTestCase):
    def test_detects_connection_strings(self):
        kinds = {s["kind"] for s in secret_scanner.detect_secrets_in_text(ENV_SNIPPET)}
        self.assertIn("conn_string", kinds)

    def test_detects_cloud_keys(self):
        kinds = {s["kind"] for s in secret_scanner.detect_secrets_in_text(ENV_SNIPPET)}
        self.assertIn("aws_access_key", kinds)
        self.assertIn("stripe_live", kinds)
        self.assertIn("google_api_key", kinds)
        self.assertIn("sendgrid", kinds)

    def test_detects_plaintext_password_assignment(self):
        kinds = {s["kind"] for s in secret_scanner.detect_secrets_in_text(ENV_SNIPPET)}
        self.assertIn("credential_assignment", kinds)

    def test_detects_github_pat_in_git_config(self):
        kinds = {s["kind"] for s in secret_scanner.detect_secrets_in_text(GIT_CONFIG_SNIPPET)}
        self.assertIn("github_pat", kinds)

    def test_detects_inline_js_credentials(self):
        secrets = secret_scanner.detect_secrets_in_text(ADMIN_INLINE_JS)
        self.assertTrue(secrets)

    def test_conn_string_password_is_masked(self):
        secrets = secret_scanner.detect_secrets_in_text(ENV_SNIPPET)
        conn = next(s for s in secrets if s["kind"] == "conn_string")
        self.assertIn("****", conn["masked"])
        self.assertNotIn("R3dArch1ve2024", conn["masked"])

    def test_placeholders_not_reported(self):
        # changeme / your_api_key_here 屬佔位，賦值型不應誤報
        kinds = {s["kind"] for s in secret_scanner.detect_secrets_in_text(PLACEHOLDER_ENV)}
        self.assertNotIn("credential_assignment", kinds)

    def test_clean_text_returns_empty(self):
        clean = "<html><body><h1>Hello world</h1><p>正常內容</p></body></html>"
        self.assertEqual(secret_scanner.detect_secrets_in_text(clean), [])


class TestRedactSecrets(SimpleTestCase):
    def test_redact_masks_assignment(self):
        out = secret_scanner.redact_secrets_in_text("ADMIN_PASSWORD=SuperSecret2024!")
        self.assertNotIn("SuperSecret2024!", out)

    def test_redact_masks_value_even_with_placeholder_substring(self):
        # C-2 回歸：值含 'example' 子字串仍是真密碼，遮罩路徑不得豁免
        text = "DB_PASSWORD=realpass_example_2024_secret"
        out = secret_scanner.redact_secrets_in_text(text)
        self.assertNotIn("realpass_example_2024_secret", out)

    def test_redact_masks_conn_string_password(self):
        out = secret_scanner.redact_secrets_in_text(
            "mongodb://u:R3dArch1ve2024@10.0.7.13:27017/db"
        )
        self.assertIn("****", out)
        self.assertNotIn("R3dArch1ve2024", out)

    def test_redact_keeps_clean_text(self):
        clean = "正常內容 hello world"
        self.assertEqual(secret_scanner.redact_secrets_in_text(clean), clean)


class TestBuildSecretFinding(SimpleTestCase):
    def test_build_finding_severity_is_highest(self):
        secrets = secret_scanner.detect_secrets_in_text(ENV_SNIPPET)
        finding = secret_scanner.build_secret_finding(
            secrets, "https://htb.example/.env", source="exposure_probe"
        )
        self.assertIsNotNone(finding)
        self.assertEqual(finding["severity"], "critical")
        self.assertEqual(finding["rule_id"], "exposure-hardcoded-secret")
        self.assertNotIn("R3dArch1ve2024", finding["evidence"])

    def test_build_finding_none_when_empty(self):
        self.assertIsNone(
            secret_scanner.build_secret_finding([], "x", source="s")
        )
