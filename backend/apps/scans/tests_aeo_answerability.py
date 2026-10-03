"""AEO 可回答性檢測（apps/scans/aeo/）。

GOLD_SITES 是人工校驗題集：每個網站的每一題都由人判讀內容後標註「應有的判定」。
規則修改後必須維持全部命中；新增規則時先在這裡補一個能說明該情境的網站與標註。
指標：判定準確率（與人工標註一致的比例）與「答案附有正確原文的比例」。
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase

from apps.scans import tasks
from apps.scans.aeo.content import extract_page_content, robots_directives
from apps.scans.aeo.evaluate import SitePage, evaluate_site
from apps.scans.aeo.markup import check_markup
from apps.scans.models import Finding, ScanJob
from apps.scans.scanners import PageAnalysisInput, analyze_aeo, calculate_scores, parse_html_signals

ADMISSION = """<html><body><nav>首頁 招生 聯絡</nav><main><h1>資訊管理系 招生資訊</h1>
<p>本系提供資訊管理學士學位課程，培養企業數位轉型所需的系統分析與資料應用人才。</p>
<h2>申請流程</h2><ol><li>線上填寫報名表</li><li>上傳成績單與自傳</li><li>繳交報名費</li></ol>
<p>招生名額與甄選方式依各年度招生簡章公告，詳情請洽招生組。</p></main>
<footer>聯絡電話：02-2322-6000　Email：imd@ntub.edu.tw</footer></body></html>"""
ADMISSION_NEWS = """<html><body><main><h1>最新消息</h1>
<p>碩士班招生報名日期：3月1日至3月20日止，逾期不受理，請留意各項時程安排。</p></main></body></html>"""

SHOP = """<html><body><main><h1>小島咖啡豆</h1>
<p>我們提供自家烘焙的精品咖啡豆與濾掛包，產地直送、每週新鮮烘焙，適合居家與辦公室沖煮。</p>
<h2>價格</h2><p>衣索比亞耶加雪菲 半磅 NT$480，一磅 NT$880。</p>
<h2>購買須知</h2>
<p>商品到貨享有 7 天鑑賞期，未拆封可申請退貨退款，請於收到商品後 7 日內聯絡客服。</p>
<p>付款完成後 3-5 個工作天出貨，宅配到府。</p>
<p>有任何問題歡迎來電洽詢，我們將竭誠為您服務。</p>
<p>加入購物車後即可結帳，訂單成立後會寄送確認信。</p></main></body></html>"""

CONFLICT_A = """<html><body><main><h1>招生簡章</h1>
<p>2026 學年度招生，網路報名截止日期為 2026年3月20日，逾期不予受理。</p>
<p>本系提供完整的資訊課程與實習機會，培養跨領域的數位人才，歡迎報名。</p>
<p>聯絡電話 (02)2345-6789，信箱 office@school.example。</p></main></body></html>"""
CONFLICT_B = """<html><body><main><h1>報名專區</h1>
<p>2026 學年度報名申請開放中，報名截止：2026年4月10日。請備妥文件後上傳。</p>
</main></body></html>"""

FAQ_SITE = """<html><body><main><h1>常見問題</h1>
<p>我們提供線上課程平台，讓學員隨時隨地學習程式設計與資料分析，課程由業界講師錄製。</p>
<dl><dt>可以線上付款嗎？</dt>
<dd>可以，支援信用卡、Apple Pay 與超商代碼繳費，付款後立即開通課程。</dd>
<dt>課程可以看多久？</dt><dd>詳情請洽客服。</dd></dl>
<p>客服信箱 help@learn.example</p></main></body></html>"""

# (網站, 頁面清單, {題目 key: 人工標註的判定})
GOLD_SITES = [
    (
        "招生：有流程、日期沒寫年度、沒寫資格",
        [
            SitePage("https://imd.example/admission", ADMISSION, ADMISSION),
            SitePage("https://imd.example/news", ADMISSION_NEWS),
        ],
        {
            "contact_phone": "answered",
            "contact_email": "answered",
            "about": "answered",
            "apply_how": "answered",
            "apply_deadline": "insufficient",
            "eligibility": "missing",
        },
    ),
    (
        "電商：價格、退貨、出貨都寫清楚，但電話只有「歡迎來電」",
        [SitePage("https://shop.example/", SHOP, SHOP)],
        {
            "contact_phone": "insufficient",
            "contact_email": "missing",
            "about": "answered",
            "price": "answered",
            "refund": "answered",
            "shipping": "answered",
        },
    ),
    (
        "兩頁截止日不同",
        [
            SitePage("https://school.example/brochure", CONFLICT_A),
            SitePage("https://school.example/apply", CONFLICT_B),
        ],
        {"contact_phone": "answered", "contact_email": "answered", "apply_deadline": "conflict"},
    ),
    (
        "網站自己的 FAQ：一題有答案、一題只有「詳情請洽」",
        [SitePage("https://learn.example/faq", FAQ_SITE)],
        {
            "contact_email": "answered",
            "about": "answered",
            "site:可以線上付款嗎？": "answered",
            "site:課程可以看多久？": "insufficient",
        },
    ),
]


def _by_key(evaluation):
    out = {}
    for r in evaluation.results:
        key = f"site:{r.question.text}" if r.question.source == "site" else r.question.key
        out[key] = r
    return out


class GoldQuestionSetTests(SimpleTestCase):
    def test_gold_set_accuracy_and_evidence(self):
        total = correct = 0
        mismatches = []
        answered = with_quote = 0
        for name, pages, expected in GOLD_SITES:
            evaluation = evaluate_site(pages)
            self.assertEqual(evaluation.status, "evaluated", name)
            results = _by_key(evaluation)
            for key, verdict in expected.items():
                total += 1
                got = results.get(key)
                if got and got.verdict == verdict:
                    correct += 1
                else:
                    mismatches.append(f"{name}／{key}：期望 {verdict}，得到 {got and got.verdict}")
            for r in evaluation.results:
                if r.verdict == "answered":
                    answered += 1
                    with_quote += r.value_in_quote
                # 每個判定都要有理由；非「無答案」一定附原文
                self.assertTrue(r.reason)
                if r.verdict != "missing":
                    self.assertTrue(r.evidence, f"{name}／{r.question.text} 沒有證據")
        self.assertEqual(mismatches, [], "\n".join(mismatches))
        self.assertEqual(correct, total)
        # 答案附有正確原文的比例：答案值必須真的出現在引用段落中
        self.assertEqual(with_quote, answered)

    def test_unrelated_intents_are_not_asked(self):
        # 咖啡豆電商不該被問招生問題
        results = _by_key(evaluate_site(GOLD_SITES[1][1]))
        self.assertNotIn("apply_deadline", results)
        self.assertNotIn("eligibility", results)

    def test_deadline_evidence_points_to_source_passage(self):
        results = _by_key(evaluate_site(GOLD_SITES[0][1]))
        deadline = results["apply_deadline"]
        self.assertIn("年度", deadline.reason)
        self.assertEqual(deadline.evidence[0].page_url, "https://imd.example/news")
        self.assertIn("3月1日", deadline.evidence[0].quote)

    def test_conflict_lists_both_pages(self):
        results = _by_key(evaluate_site(GOLD_SITES[2][1]))
        urls = {e.page_url for e in results["apply_deadline"].evidence}
        self.assertEqual(urls, {"https://school.example/brochure", "https://school.example/apply"})


class InsufficientContentTests(SimpleTestCase):
    def test_thin_site_is_not_scored(self):
        evaluation = evaluate_site(
            [SitePage("https://x.example/", "<html><body><p>即將上線</p></body></html>")]
        )
        self.assertEqual(evaluation.status, "insufficient")
        self.assertIsNone(evaluation.score)
        self.assertIn("未充分評估", evaluation.reason)
        self.assertEqual(evaluation.findings, [])

    def test_blocked_pages_are_ignored(self):
        evaluation = evaluate_site([SitePage("https://x.example/", SHOP, blocked=True)])
        self.assertEqual(evaluation.status, "insufficient")


class ContentLayerTests(SimpleTestCase):
    def test_main_text_excludes_navigation_hidden_and_scripts(self):
        html = (
            "<html><body><nav>選單一 選單二</nav><main><p>這是正文段落的內容。</p>"
            "<div hidden>隱藏的文字</div><p style='display:none'>看不到的段落</p>"
            "<div aria-hidden='true'>裝飾文字</div></main><script>var s='程式碼';</script>"
            "<footer><p>頁尾電話 02-1234-5678</p></footer></body></html>"
        )
        content = extract_page_content("https://x/", html)
        texts = [p.text for p in content.passages]
        self.assertIn("這是正文段落的內容。", texts)
        joined = "".join(texts)
        for hidden in ("選單一", "隱藏的文字", "看不到的段落", "裝飾文字", "程式碼"):
            self.assertNotIn(hidden, joined)
        footer = [p for p in content.passages if p.region == "footer"]
        self.assertEqual(len(footer), 1)
        # 頁尾不算正文字數
        self.assertEqual(content.text_chars, len("這是正文段落的內容。"))

    def test_js_dependent_pages_reported_without_claiming_google_cannot_see(self):
        raw = "<html><body><div id='app'></div></body></html>"
        evaluation = evaluate_site([SitePage("https://spa.example/", SHOP, raw)])
        render = [f for f in evaluation.findings if f["rule_id"] == "aeo-render-dependent"]
        self.assertEqual(len(render), 1)
        self.assertEqual(render[0]["severity"], "info")
        self.assertIn("Google 會執行", render[0]["description"])

    def test_robots_directives_from_meta_and_header(self):
        html = '<meta name="robots" content="max-snippet:0, noarchive">'
        found = robots_directives(html, {"X-Robots-Tag": "googlebot: noindex"})
        self.assertEqual(found, {"max-snippet:0": "meta robots", "noindex": "X-Robots-Tag"})


def _page_input(html, headers=None):
    return PageAnalysisInput(
        url="https://x.example/",
        final_url="https://x.example/",
        title="t",
        html=html,
        headers=headers or {},
        element_boxes={},
    )


class PageLevelAeoTests(SimpleTestCase):
    def test_noindex_and_nosnippet(self):
        html = (
            "<html><head><meta name='robots' content='noindex'></head>"
            "<body><p>內容</p></body></html>"
        )
        rules = {f["rule_id"] for f in analyze_aeo(_page_input(html), parse_html_signals(html))}
        self.assertIn("aeo-noindex", rules)
        html2 = "<html><body><p>內容</p></body></html>"
        rules2 = {
            f["rule_id"]
            for f in analyze_aeo(
                _page_input(html2, {"X-Robots-Tag": "nosnippet"}), parse_html_signals(html2)
            )
        }
        self.assertEqual(rules2, {"aeo-nosnippet"})

    def test_markup_syntax_and_mismatch(self):
        broken = '<script type="application/ld+json">{"@type": "FAQPage",}</script>'
        faq = (
            '<script type="application/ld+json">{"@type":"FAQPage","mainEntity":['
            '{"@type":"Question","name":"可以退款嗎？","acceptedAnswer":{"@type":"Answer",'
            '"text":"購買後七天內可全額退款。"}}]}</script>'
        )
        html = f"<html><head>{broken}{faq}</head><body><p>我們提供線上課程。</p></body></html>"
        findings = analyze_aeo(_page_input(html), parse_html_signals(html))
        rules = {f["rule_id"] for f in findings}
        self.assertEqual(rules, {"aeo-markup-syntax", "aeo-markup-mismatch"})

    def test_consistent_markup_has_no_findings(self):
        faq = (
            '<script type="application/ld+json">{"@type":"FAQPage","mainEntity":['
            '{"@type":"Question","name":"可以退款嗎？","acceptedAnswer":{"@type":"Answer",'
            '"text":"購買後七天內可全額退款。"}}]}</script>'
        )
        html = (
            f"<html><head>{faq}</head><body><h2>可以退款嗎？</h2>"
            "<p>購買後七天內可全額退款。</p></body></html>"
        )
        self.assertEqual(analyze_aeo(_page_input(html), parse_html_signals(html)), [])

    def test_telephone_markup_must_be_visible(self):
        issues = check_markup(
            ['{"@type":"Organization","telephone":"+886-2-2345-6789"}'], "電話 02-2345-6789"
        )
        self.assertEqual(issues, [])
        issues = check_markup(
            ['{"@type":"Organization","telephone":"+886-2-9999-0000"}'], "電話 02-2345-6789"
        )
        self.assertEqual([i["field"] for i in issues], ["telephone"])


class AeoScoringTests(SimpleTestCase):
    def test_answer_findings_are_not_double_counted_with_base_score(self):
        findings = [
            {
                "category": "aeo",
                "severity": "medium",
                "rule_id": "aeo-answer-missing",
                "title": "a",
            },
            {"category": "aeo", "severity": "medium", "rule_id": "aeo-noindex", "title": "b"},
        ]
        _, scores, _ = calculate_scores(
            findings, tested_categories={"aeo"}, base_scores={"aeo": 80}
        )
        # 只有 noindex（medium=12）扣分：80 × e^(−12/50)
        self.assertEqual(scores["aeo"], 63)
        _, scores, _ = calculate_scores(findings, tested_categories={"aeo"})
        self.assertEqual(scores["aeo"], 62)  # 沒有基準分時照舊扣兩次


User = get_user_model()


class AeoPipelineTests(TransactionTestCase):
    def _run(self, html):
        user = User.objects.create_user(username=f"aeo-{len(html)}", password="safe-test-password")
        scan = ScanJob.objects.create(
            user=user,
            original_url="https://shop.example/",
            normalized_url="https://shop.example/",
            origin="https://shop.example",
            status=ScanJob.Status.QUEUED,
            max_pages=1,
            max_depth=1,
            categories=["seo", "aeo"],
        )
        page = {
            "url": "https://shop.example/",
            "final_url": "https://shop.example/",
            "origin": "https://shop.example",
            "status_code": 200,
            "title": "t",
            "html": html,
            "rendered_dom": html,
            "html_only": html,
            "screenshot_path": "",
            "load_time_ms": 1,
            "depth": 0,
            "blocked_reason": "",
            "outgoing_links": [],
            "headers": {},
            "element_boxes": {},
        }
        for target, kwargs in [
            ("assert_public_http_url", {"return_value": "https://shop.example/"}),
            ("crawl_site", {"new": mock.AsyncMock(return_value=([page], {}, {}, []))}),
            ("analyze_ssl", {"return_value": []}),
            ("build_link_report", {"return_value": {}}),
            ("analyze_cookies", {"return_value": []}),
            ("analyze_headers", {"return_value": []}),
            ("analyze_sri", {"return_value": []}),
            ("analyze_dns", {"return_value": []}),
            ("analyze_js_libraries", {"return_value": []}),
            ("analyze_services", {"return_value": []}),
            ("owasp_mapper.backfill", {}),
            ("settle_scan_actual", {}),
            ("grant_fixgen_entitlement", {}),
        ]:
            mock.patch(f"apps.scans.tasks.{target}", **kwargs).start()
        self.addCleanup(mock.patch.stopall)
        tasks.run_scan_job.run(scan.id)
        scan.refresh_from_db()
        return scan

    def test_scored_from_answerability_with_report_saved(self):
        scan = self._run(SHOP)
        self.assertEqual(scan.status, ScanJob.Status.COMPLETED)
        report = scan.aeo_report
        self.assertEqual(report["status"], "evaluated")
        self.assertEqual(report["questions_total"], len(report["questions"]))
        self.assertLess(scan.category_scores["aeo"], 100)
        self.assertEqual(scan.category_scores["aeo"], report["score"])
        self.assertTrue(
            Finding.objects.filter(scan_job=scan, rule_id="aeo-answer-insufficient").exists()
        )
        self.assertIn(
            "aeo_answers",
            [m for m in ["aeo_answers"] if any("AEO 問答檢測" in e["msg"] for e in scan.scan_log)],
        )

    def test_thin_content_marks_aeo_not_evaluated(self):
        scan = self._run("<html><body><p>即將上線</p></body></html>")
        self.assertEqual(scan.aeo_report["status"], "insufficient")
        self.assertNotIn("aeo", scan.category_scores)
        self.assertIn("seo", scan.category_scores)


class AeoReportTests(TransactionTestCase):
    def test_report_has_scope_row_and_per_question_appendix(self):
        import json
        from pathlib import Path

        from jsonschema import Draft7Validator

        from apps.scans.reports import build_report_payload

        user = User.objects.create_user(username="aeo-report", password="safe-test-password")
        evaluation = evaluate_site(GOLD_SITES[0][1])
        scan = ScanJob.objects.create(
            user=user,
            original_url="https://imd.example/",
            normalized_url="https://imd.example/",
            origin="https://imd.example",
            status=ScanJob.Status.COMPLETED,
            category_scores={"aeo": evaluation.score},
            overall_score=evaluation.score,
            aeo_report=evaluation.summary,
        )
        payload = build_report_payload(scan)
        schema = json.loads(
            (Path(__file__).resolve().parent / "report_render" / "schema.json").read_text("utf-8")
        )
        self.assertEqual(list(Draft7Validator(schema).iter_errors(payload)), [])
        items = payload["appendix"]["aeo_items"]
        self.assertEqual(len(items), evaluation.summary["questions_total"])
        deadline = next(i for i in items if "截止" in i["question"])
        self.assertEqual(deadline["verdict"], "資訊不足")
        self.assertIn("年度", deadline["basis"])
        phone = next(i for i in items if "電話" in i["question"])
        self.assertIn("02-2322-6000", phone["basis"])
        scope_text = json.dumps(payload, ensure_ascii=False)
        self.assertIn("有答案的問題比例", scope_text)

    def test_insufficient_scan_says_not_evaluated(self):
        from apps.scans.reports import _aeo_items, _aeo_scope_text

        user = User.objects.create_user(username="aeo-thin", password="safe-test-password")
        evaluation = evaluate_site([SitePage("https://x.example/", "<p>即將上線</p>")])
        scan = ScanJob.objects.create(
            user=user,
            original_url="https://x.example/",
            normalized_url="https://x.example/",
            origin="https://x.example",
            status=ScanJob.Status.COMPLETED,
            aeo_report=evaluation.summary,
        )
        self.assertIn("未充分評估", _aeo_scope_text(scan))
        self.assertEqual(_aeo_items(scan), [])
