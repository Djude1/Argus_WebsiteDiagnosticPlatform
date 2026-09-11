"""修正產出（Fix Output）產生引擎——以假 provider 測服務邊界（spec Seam 1）。

spec：docs/specs/0002-fix-output.md。核心承諾是「絕不編造」：
- 識別類欄位（機構名、電話、地址、社群連結）只能用爬到的事實，
  假 LLM 輸出爬不到的值 → 驗證步驟取代為佔位符【請填寫：…】。
- 文案類只能改寫爬到的內文，新增的硬事實（數字／網址）會被攔截，
  改用爬取內容的逐字摘錄（extracted）。
- 站上無 FAQ 依據 → 不產 FAQPage Schema。
- 冪等：同 ScanJob 重複觸發不重複執行。
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.agent.providers import ChatResponse, ProviderChain, ProviderError
from apps.scans.fixgen.services import run_fix_output, start_fix_output
from apps.scans.models import FixOutput, Page, ScanJob

HOME_URL = "https://sunshine.example/"
FAQ_URL = "https://sunshine.example/faq"

HOME_HTML = """
<html><head>
<title>陽光咖啡 Sunshine Coffee｜手沖咖啡與自製甜點</title>
<meta name="description" content="陽光咖啡提供單一產區手沖咖啡與每日自製甜點，位於台北市中正區。">
<meta property="og:site_name" content="陽光咖啡">
</head><body>
<h1>陽光咖啡 Sunshine Coffee</h1>
<p>陽光咖啡提供單一產區手沖咖啡與每日自製甜點。營業時間為週二至週日 09:00-18:00。</p>
<p>地址：100台北市中正區重慶南路一段10號</p>
<p>電話：02-2311-1234</p>
<img src="/images/shop.jpg" alt="店內座位區">
<a href="https://www.facebook.com/sunshinecoffee/">Facebook</a>
<a href="https://www.instagram.com/sunshinecoffee/">Instagram</a>
</body></html>
"""

FAQ_HTML = """
<html><head><title>常見問題 - 陽光咖啡</title></head><body>
<details><summary>你們有提供素食甜點嗎？</summary><p>我們每日提供至少兩款素食甜點，部分為全素。</p></details>
<details><summary>可以預約座位嗎？</summary><p>週末提供線上預約，平日現場排隊。</p></details>
</body></html>
"""

LLM_PAYLOAD = {
    "json_ld": {
        "name": "陽光咖啡",
        "telephone": "02-2311-1234",
        "address": "100台北市中正區重慶南路一段10號",
        "same_as": [
            "https://www.facebook.com/sunshinecoffee/",
            "https://www.instagram.com/sunshinecoffee/",
        ],
    },
    "og_meta": {
        "og_description": "陽光咖啡提供單一產區手沖咖啡與每日自製甜點，位於台北市中正區。",
        "og_image": "https://sunshine.example/images/shop.jpg",
    },
    "llms_txt": {
        "summary": "陽光咖啡是位於台北市中正區的手沖咖啡店，提供單一產區咖啡與自製甜點。",
        "sections": [
            {
                "path": "/",
                "title": "陽光咖啡 Sunshine Coffee｜手沖咖啡與自製甜點",
                "description": "首頁：菜單與店家資訊。",
            },
            {
                "path": "/faq",
                "title": "常見問題 - 陽光咖啡",
                "description": "常見問題與預約說明。",
            },
        ],
    },
    "faq_schema": {
        "main_entity": [
            {
                "question": "你們有提供素食甜點嗎？",
                "answer": "我們每日提供至少兩款素食甜點，部分為全素。",
            },
            {"question": "可以預約座位嗎？", "answer": "週末提供線上預約，平日現場排隊。"},
        ]
    },
}


class FakeProvider:
    """注入用假 provider：回固定 JSON，或丟 ProviderError。"""

    name = "fake"
    default_model = "fake-model"

    def __init__(self, content: str = "", error: ProviderError | None = None):
        self.content = content
        self.error = error
        self.prompts: list[str] = []

    def chat_with_tools(self, *args, **kwargs):
        raise ProviderError(self.name, "unsupported", "fake 不支援 tool calling")

    def chat_text(self, prompt, model=None, temperature=0.2, max_tokens=2048):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return ChatResponse(
            provider=self.name,
            model=model or self.default_model,
            content=self.content,
            total_tokens=123,
        )


def _fake_chain(payload: dict | None = None, error: ProviderError | None = None) -> ProviderChain:
    content = json.dumps(payload if payload is not None else LLM_PAYLOAD, ensure_ascii=False)
    return ProviderChain(providers=[FakeProvider(content=content, error=error)])


class FixOutputGenerationTests(TestCase):
    def setUp(self):
        self.user = None  # ScanJob.user 需要使用者，見 _make_scan
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(
            username="fixgen-tester",
            email="fixgen@example.com",
            password="safe-test-password",
        )
        self.scan = ScanJob.objects.create(
            user=self.user,
            original_url=HOME_URL,
            normalized_url=HOME_URL,
            origin="https://sunshine.example",
            status=ScanJob.Status.COMPLETED,
        )
        self.home = Page.objects.create(
            scan_job=self.scan,
            url=HOME_URL,
            final_url=HOME_URL,
            origin="https://sunshine.example",
            status_code=200,
            title="陽光咖啡 Sunshine Coffee｜手沖咖啡與自製甜點",
            html=HOME_HTML,
            depth=0,
        )
        self.faq = Page.objects.create(
            scan_job=self.scan,
            url=FAQ_URL,
            final_url=FAQ_URL,
            origin="https://sunshine.example",
            status_code=200,
            title="常見問題 - 陽光咖啡",
            html=FAQ_HTML,
            depth=1,
        )

    def _run(self, chain) -> FixOutput:
        with patch("apps.scans.fixgen.services.run_fix_output_task"):
            start_fix_output(self.scan)
        run_fix_output(self.scan.id, chain=chain)
        return FixOutput.objects.get(scan_job=self.scan)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_happy_path_produces_four_artifacts_ready(self):
        fix_output = self._run(_fake_chain())

        self.assertEqual(fix_output.status, FixOutput.Status.READY)
        self.assertEqual(fix_output.provider, "fake")
        self.assertEqual(fix_output.model_id, "fake-model")
        self.assertEqual(fix_output.total_tokens, 123)
        self.assertEqual(
            set(fix_output.artifacts.keys()),
            {"json_ld", "og_meta", "llms_txt", "faq_schema"},
        )

        json_ld = fix_output.artifacts["json_ld"]
        self.assertIn('"Organization"', json_ld["content"])
        self.assertIn("陽光咖啡", json_ld["content"])
        self.assertIn("02-2311-1234", json_ld["content"])
        self.assertNotIn("【請填寫", json_ld["content"])
        # 逐欄位來源標註：電話確實出現在首頁
        self.assertEqual(
            json_ld["fields"]["telephone"],
            {"status": "verified", "source_url": HOME_URL},
        )

        og = fix_output.artifacts["og_meta"]["content"]
        self.assertIn('property="og:title"', og)
        self.assertIn("陽光咖啡 Sunshine Coffee｜手沖咖啡與自製甜點", og)
        self.assertIn('property="og:image"', og)
        self.assertIn("https://sunshine.example/images/shop.jpg", og)
        self.assertIn('name="twitter:card"', og)
        self.assertIn('name="description"', og)

        llms = fix_output.artifacts["llms_txt"]["content"]
        self.assertTrue(llms.startswith("# 陽光咖啡"))
        self.assertIn("https://sunshine.example/faq", llms)

        faq = fix_output.artifacts["faq_schema"]["content"]
        self.assertIn("FAQPage", faq)
        self.assertIn("你們有提供素食甜點嗎？", faq)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_fabricated_identity_replaced_by_placeholder(self):
        payload = json.loads(json.dumps(LLM_PAYLOAD, ensure_ascii=False))
        payload["json_ld"]["telephone"] = "0912-345-678"  # 語料裡沒有
        payload["json_ld"]["address"] = "月球靜海基地"  # 語料裡沒有

        fix_output = self._run(_fake_chain(payload))

        self.assertEqual(fix_output.status, FixOutput.Status.READY)
        content = fix_output.artifacts["json_ld"]["content"]
        self.assertIn("【請填寫：電話】", content)
        self.assertIn("【請填寫：地址】", content)
        self.assertNotIn("0912-345-678", content)
        self.assertNotIn("月球靜海基地", content)
        # 通過驗證的欄位不受影響
        self.assertIn("陽光咖啡", content)
        fields = fix_output.artifacts["json_ld"]["fields"]
        self.assertEqual(fields["telephone"]["status"], "placeholder")
        self.assertEqual(fields["address"]["status"], "placeholder")
        self.assertEqual(fields["name"]["status"], "verified")

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_no_faq_basis_means_no_faq_schema(self):
        # 拿掉 FAQ 頁，僅留首頁（無 FAQ 結構）
        self.faq.delete()

        fix_output = self._run(_fake_chain())

        self.assertEqual(fix_output.status, FixOutput.Status.READY)
        self.assertNotIn("faq_schema", fix_output.artifacts)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_ungrounded_faq_question_dropped(self):
        payload = json.loads(json.dumps(LLM_PAYLOAD, ensure_ascii=False))
        payload["faq_schema"]["main_entity"].append(
            {"question": "你們有停車場嗎？", "answer": "附近有收費停車場。"}  # 語料裡沒有
        )

        fix_output = self._run(_fake_chain(payload))

        faq_content = fix_output.artifacts["faq_schema"]["content"]
        self.assertNotIn("停車場", faq_content)
        self.assertIn("你們有提供素食甜點嗎？", faq_content)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_copy_with_new_hard_facts_falls_back_to_extracted(self):
        payload = json.loads(json.dumps(LLM_PAYLOAD, ensure_ascii=False))
        # 「2025」與「世界大賽」不在語料——新增事實，必須被攔截
        payload["og_meta"]["og_description"] = "陽光咖啡榮獲 2025 世界咖啡大賽冠軍。"

        fix_output = self._run(_fake_chain(payload))

        og = fix_output.artifacts["og_meta"]
        self.assertNotIn("2025", og["content"])
        # 退回爬取內容的逐字摘錄：首頁 meta description
        self.assertIn("陽光咖啡提供單一產區手沖咖啡與每日自製甜點", og["content"])
        self.assertEqual(og["fields"]["og_description"]["status"], "extracted")

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_llms_txt_link_not_crawled_dropped_and_sameas_partial(self):
        payload = json.loads(json.dumps(LLM_PAYLOAD, ensure_ascii=False))
        payload["llms_txt"]["sections"].append(
            {"path": "/not-crawled", "title": "不存在的頁面", "description": "x"}
        )
        payload["json_ld"]["same_as"].append("https://twitter.com/sunshine")  # 沒爬到

        fix_output = self._run(_fake_chain(payload))

        llms = fix_output.artifacts["llms_txt"]["content"]
        self.assertNotIn("/not-crawled", llms)
        self.assertIn(HOME_URL, llms)
        json_ld = fix_output.artifacts["json_ld"]
        self.assertNotIn("https://twitter.com/sunshine", json_ld["content"])
        self.assertEqual(json_ld["fields"]["same_as"]["status"], "partial")

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_start_is_idempotent_and_dispatches_once(self):
        with patch("apps.scans.fixgen.services.run_fix_output_task") as task:
            fix_output, dispatched = start_fix_output(self.scan)
            self.assertTrue(dispatched)
            self.assertEqual(fix_output.status, FixOutput.Status.GENERATING)
            # 產生中再觸發：不重複派工
            fix_output, dispatched = start_fix_output(self.scan)
            self.assertFalse(dispatched)
            self.assertEqual(task.delay.call_count, 1)

        run_fix_output(self.scan.id, chain=_fake_chain())

        with patch("apps.scans.fixgen.services.run_fix_output_task") as task:
            # ready 後再觸發：回既有結果，不重複派工
            fix_output, dispatched = start_fix_output(self.scan)
            self.assertFalse(dispatched)
            self.assertEqual(fix_output.status, FixOutput.Status.READY)
            task.delay.assert_not_called()
        self.assertIn("json_ld", FixOutput.objects.get(scan_job=self.scan).artifacts)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_llm_failure_marks_failed_with_public_reason(self):
        fix_output = self._run(
            _fake_chain(error=ProviderError("fake", 500, "non-200"))
        )

        self.assertEqual(fix_output.status, FixOutput.Status.FAILED)
        self.assertNotEqual(fix_output.error, "")
        self.assertNotIn("api", fix_output.error.lower())  # 不帶金鑰類資訊
        self.assertEqual(fix_output.artifacts, {})

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_invalid_json_response_marks_failed(self):
        fix_output = self._run(_fake_chain(payload={"not": "the contract"}))

        self.assertEqual(fix_output.status, FixOutput.Status.FAILED)
        self.assertNotEqual(fix_output.error, "")

    def test_disabled_by_default_marks_failed(self):
        # 不 override ARGUS_FIXGEN_ENABLED（預設 False）
        fix_output = self._run(_fake_chain())

        self.assertEqual(fix_output.status, FixOutput.Status.FAILED)
        self.assertIn("未啟用", fix_output.error)
