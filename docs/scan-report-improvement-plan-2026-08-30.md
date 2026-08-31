# Argus 掃描報告品質改善 — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把目前「328 段純文字、零表格零圖片、零分頁、無品牌、無防偽、分數邏輯錯」的 `.docx` 報告，重做成「封面 + 目錄 + 分頁 + 表格 + 圖示 + 顯眼藝術字 + 報告編號 + SHA-256 + QR code + /verify/ 線上查驗」的對外可交付文件，且修正分數/排序核心邏輯 bug。

**Architecture:**
- **後端**：新增 `ReportVerification` model + `GET /api/verify/{report_number}/` 公開端點；`reports.py` 重構成「樣式系統 + 章節產生器」；`calculate_scores()` 改為去重 + 信心度；`Finding.Meta.ordering` 改用 `F.desc(nulls_last=True)`；補齊 `security/` 各 scanner 的 `priority_score`。
- **前端**：新增 `/verify/{reportNumber}` 公開頁（沿用 `.public-shell` 科技風）；不動其他前端。
- **設計資源**：把 `frontend/public/favicon.svg` 匯出成 PNG（256×256），作為封面 logo / 浮水印。
- **測試鎖定**：每個改動都先寫 failing test，再實作。新測試加入排序、去重、分數、/verify/、報告結構。

**Tech Stack:** Django 5 + DRF、python-docx、Pillow（logo PNG）、cairosvg（SVG→PNG）、React 18、Vite 6、Zustand、Axios。

---

## Global Constraints

- 報告產生器 `reports.py` 是單檔架構的一部分，**禁止**拆成多個獨立模組檔（單檔架構是本專案的 backend 慣例，所有 scanner 邏輯都在 `scanners.py`）
- 前端禁止新增獨立 `.jsx` 元件檔**給 verify 頁以外的場景**；verify 頁可獨立檔（domain = verify，職責清楚）
- 後端任何 DB 寫入只能透過 service layer（既有慣例）；`reports.py` 禁止 DB 寫入既有資料（既有 `CLAUDE.md` 規則）—— 例外：本計畫允許 `build_scan_report()` 寫入 `ReportVerification`，因為這是「報告產生器的副產品」不是業務資料
- 任何新 endpoint 都必須有對應的權限 class
- PII 遮罩規則（`security/redaction.py`）不可變動；只在 `reports.py` 套用層
- 不修改 `docs/scan-report-quality-audit-2026-08-30.md` 與 `docs/scan-report-quality-audit-2026-08-30-supplement.md`（稽核文件）
- 所有 commit 必須用 `log/YYYY-MM-DD_簡短描述.md` 記錄（CLAUDE.md 規則）
- 前端 build 一律 `cd frontend ; .\build-node22.ps1`（CLAUDE.md 規則）
- 不使用 `npm run build`（Node 24 Rollup crash，CLAUDE.md 規則）

---

## File Structure

**新增**：
- `backend/apps/scans/migrations/00XX_report_verification.py`
- `backend/apps/scans/report_styles.py`（樣式常數集中檔）
- `backend/apps/scans/report_sections.py`（章節產生器）
- `backend/apps/scans/verify_views.py`（公開 verify 端點）
- `backend/apps/scans/tests_security_priority.py`
- `backend/apps/scans/tests_finding_ordering.py`
- `backend/apps/scans/tests_report_grouping.py`
- `backend/apps/scans/tests_report_scoring.py`
- `backend/apps/scans/tests_models_report_verification.py`
- `backend/apps/scans/tests_verify.py`
- `backend/apps/scans/tests_report_appendix.py`
- `backend/apps/scans/tests_report_structure.py`
- `backend/apps/scans/tests_report_cache.py`
- `backend/apps/scans/tests_report_integration.py`
- `frontend/src/features/verify/VerifyPage.jsx`
- `frontend/public/argus-logo.png`（從 favicon.svg 匯出 256×256）
- `frontend/public/argus-logo-watermark.png`（半透明版本）
- `scripts/render_argus_logo.py`（一次性產圖腳本）

**修改**：
- `backend/apps/scans/models.py`（加 `ReportVerification` class + 改 `Finding.Meta.ordering`）
- `backend/apps/scans/reports.py`（重寫，156 → 預估 450 行）
- `backend/apps/scans/scanners.py::calculate_scores()`（scanners.py:981-1038）
- `backend/apps/scans/security/dns_scanner.py`、`header_scanner.py`、`cookie_scanner.py`、`ssl_scanner.py`、`sri_scanner.py`、`js_library_scanner.py`、`service_cve_scanner.py`（補 priority_score）
- `backend/apps/scans/views.py`（report action 加快取）
- `backend/config/urls.py`（加 `/api/verify/` 路由）
- `frontend/src/App.jsx`（加 verify route）

**不動**：
- `backend/apps/scans/security/redaction.py`（PII 規則）
- `frontend/src/styles.css` 的 `:root` token（沿用既有）
- `frontend/src/api.js`（沿用既有 axios instance）

---

# Phase 1：分數與排序核心修正（P0 — 不修後面全白做）

## Task 1.1: 補齊 `security/` 子套件各 scanner 的 `priority_score`

**Files:**
- Modify:
  - `backend/apps/scans/security/dns_scanner.py`
  - `backend/apps/scans/security/header_scanner.py`
  - `backend/apps/scans/security/cookie_scanner.py`
  - `backend/apps/scans/security/ssl_scanner.py`
  - `backend/apps/scans/security/sri_scanner.py`
  - `backend/apps/scans/security/js_library_scanner.py`
  - `backend/apps/scans/security/service_cve_scanner.py`
- Test: `backend/apps/scans/tests_security_priority.py`（新增）

**為什麼**：現有 `priority_score` 都是 NULL，導致 PostgreSQL NULLS FIRST 把資安問題頂到最前。

**規則**：
- critical → 90
- high → 75
- medium → 50
- low → 25
- info → 10

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_security_priority.py
from django.test import TestCase
from apps.scans.security import dns_scanner, header_scanner, cookie_scanner, ssl_scanner


class SecurityPriorityScoreTest(TestCase):
    def test_dns_scanner_assigns_priority(self):
        findings = dns_scanner.scan(domain="example.com")
        for f in findings:
            self.assertIsNotNone(f.get("priority_score"))
            self.assertGreaterEqual(f["priority_score"], 10)
            self.assertLessEqual(f["priority_score"], 90)

    def test_header_scanner_assigns_priority(self):
        findings = header_scanner.scan(headers={})
        for f in findings:
            self.assertIsNotNone(f.get("priority_score"))

    # 對其他 5 個 scanner 同樣寫
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_security_priority -v 2`
Expected: FAIL（priority_score 為 None）

- [ ] **Step 3：在每個 scanner 的 finding dict 加 priority_score**

範例（`dns_scanner.py`）：

```python
SEVERITY_PRIORITY = {
    "critical": 90,
    "high": 75,
    "medium": 50,
    "low": 25,
    "info": 10,
}

# 在每個 finding dict 內加：
finding = {
    "severity": "high",
    "priority_score": SEVERITY_PRIORITY["high"],
    # ... 其他欄位
}
```

- [ ] **Step 4：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_security_priority -v 2`
Expected: PASS

- [ ] **Step 5：commit**

```bash
git add backend/apps/scans/security/ backend/apps/scans/tests_security_priority.py
git commit -m "fix(scans): 補齊 security 子套件各 scanner 的 priority_score"
```

---

## Task 1.2: 修 `Finding.Meta.ordering` 讓 PostgreSQL / SQLite 行為一致

**Files:**
- Modify: `backend/apps/scans/models.py:206-211`
- Test: `backend/apps/scans/tests_finding_ordering.py`（新增）

**為什麼**：現有 `ordering = ["-priority_score", "severity", ...]`，PostgreSQL `ORDER BY x DESC` 預設 NULLS FIRST，SQLite 是 NULLS LAST → 本機開發看不出 bug，正式站才炸。

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_finding_ordering.py
from django.test import TestCase
from django.db.models import F
from apps.scans.models import ScanJob, Finding, Page


class FindingOrderingTest(TestCase):
    def test_null_priority_sorts_last(self):
        scan = ScanJob.objects.create(
            user=self._make_user(),
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
        )
        page = Page.objects.create(
            scan_job=scan,
            url="https://example.com",
            final_url="https://example.com",
            origin="example.com",
        )
        Finding.objects.create(
            scan_job=scan, page=page,
            severity="high", category=Finding.Category.SECURITY,
            title="with priority", description="d", remediation="r",
            ai_handoff_prompt="p", priority_score=75.0,
        )
        Finding.objects.create(
            scan_job=scan, page=page,
            severity="high", category=Finding.Category.SECURITY,
            title="null priority", description="d", remediation="r",
            ai_handoff_prompt="p", priority_score=None,
        )
        ordered = list(Finding.objects.filter(scan_job=scan).values_list("title", flat=True))
        self.assertEqual(ordered, ["with priority", "null priority"])
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_finding_ordering -v 2`
Expected: FAIL（NULL priority 排第一）

- [ ] **Step 3：改 ordering 為 Case/When 明確排序**

修改 `models.py:206-211`：

```python
from django.db.models import F, Case, When, Value, IntegerField

class Meta:
    ordering = [
        F("priority_score").desc(nulls_last=True),
        Case(
            When(severity="critical", then=Value(5)),
            When(severity="high", then=Value(4)),
            When(severity="medium", then=Value(3)),
            When(severity="low", then=Value(2)),
            When(severity="info", then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ),
        "category",
        "-created_at",
    ]
```

- [ ] **Step 4：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_finding_ordering -v 2`
Expected: PASS

- [ ] **Step 5：commit**

```bash
git add backend/apps/scans/models.py backend/apps/scans/tests_finding_ordering.py
git commit -m "fix(scans): Finding.Meta.ordering 修正 PostgreSQL NULLS FIRST bug"
```

---

## Task 1.3: 重寫 `_group_findings_for_report()` 用 `rule_id` 為主鍵

**Files:**
- Modify: `backend/apps/scans/reports.py:48-60`
- Test: `backend/apps/scans/tests_report_grouping.py`（新增）

**為什麼**：現有用 `(rule_id, evidence)` 當合併鍵，evidence 含頁面專屬內容，導致「同問題跨頁」分開顯示。應該用 `rule_id` 為主鍵，evidence 與 pages 收進子清單。

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_report_grouping.py
from django.test import TestCase
from apps.scans.models import ScanJob, Finding, Page
from apps.scans.reports import _group_findings_for_report


class GroupFindingsTest(TestCase):
    def test_same_rule_id_different_pages_merged(self):
        scan = ScanJob.objects.create(
            user=self._make_user(),
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
        )
        for i in range(3):
            page = Page.objects.create(
                scan_job=scan,
                url=f"https://example.com/page{i}",
                final_url=f"https://example.com/page{i}",
                origin="example.com",
            )
            Finding.objects.create(
                scan_job=scan, page=page,
                severity="medium", category=Finding.Category.GEO,
                title="JS render", description="d", remediation="r",
                ai_handoff_prompt="p", rule_id="GEO_JAVASCRIPT",
                evidence=f"page-specific {i}",
            )
        findings = list(Finding.objects.filter(scan_job=scan).select_related("page"))
        groups = _group_findings_for_report(findings)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["pages"]), 3)
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_grouping -v 2`
Expected: FAIL（產生 3 個 group）

- [ ] **Step 3：改 _group_findings_for_report 函式**

```python
def _group_findings_for_report(findings) -> list[dict]:
    """同一個 rule_id 的 finding 合併成一筆，受影響頁面收進 pages 清單。
    evidence 採 group 內第一筆作為代表（完整證據仍可從 scan_job.findings 取）。"""
    groups: OrderedDict[str, dict] = OrderedDict()
    for finding in findings:
        key = finding.rule_id or f"_unknown_{finding.id}"
        group = groups.get(key)
        if group is None:
            group = {
                "finding": finding,
                "pages": [],
                "evidence_samples": [],
            }
            groups[key] = group
        page_url = finding.page.final_url if finding.page else "站台層級"
        if page_url not in group["pages"]:
            group["pages"].append(page_url)
        if len(group["evidence_samples"]) < 3 and finding.evidence:
            group["evidence_samples"].append(finding.evidence)
    return list(groups.values())
```

- [ ] **Step 4：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_grouping -v 2`
Expected: PASS

- [ ] **Step 5：commit**

```bash
git add backend/apps/scans/reports.py backend/apps/scans/tests_report_grouping.py
git commit -m "fix(scans): 報告分組改用 rule_id 為主鍵，evidence 收進子清單"
```

---

## Task 1.4: 重寫 `calculate_scores()` 為「去重 + 信心度 + 下界衰減」

**Files:**
- Modify: `backend/apps/scans/scanners.py:981-1038`
- Test: `backend/apps/scans/tests_report_scoring.py`（新增）

**為什麼**：
- 同一個問題跨 N 頁只扣一次分（去重）
- `confidence` 低的 finding 影響小
- 用有下界的衰減，不會歸零

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_report_scoring.py
from django.test import TestCase
from apps.scans.scanners import calculate_scores


class CalculateScoresTest(TestCase):
    def test_same_rule_id_deduped_in_scoring(self):
        findings = [
            {"category": "security", "severity": "high", "rule_id": "PII",
             "title": "PII leak", "confidence": 1.0, "priority_score": 75.0},
            {"category": "security", "severity": "high", "rule_id": "PII",
             "title": "PII leak", "confidence": 1.0, "priority_score": 75.0},
            {"category": "security", "severity": "high", "rule_id": "PII",
             "title": "PII leak", "confidence": 1.0, "priority_score": 75.0},
        ]
        overall, cats, top = calculate_scores(findings, tested_categories={"security"})
        # 去重後只有 1 筆 PII，扣 25（high base）
        # 用衰減公式：100 * exp(-25 / 50) 約等於 60.6
        self.assertGreater(cats["security"], 50)
        self.assertLess(cats["security"], 70)

    def test_confidence_lowers_impact(self):
        high_conf = [{"category": "security", "severity": "high", "rule_id": "X",
                      "title": "X", "confidence": 1.0, "priority_score": 75.0}]
        low_conf = [{"category": "security", "severity": "high", "rule_id": "X",
                     "title": "X", "confidence": 0.2, "priority_score": 75.0}]
        _, c_high, _ = calculate_scores(high_conf, tested_categories={"security"})
        _, c_low, _ = calculate_scores(low_conf, tested_categories={"security"})
        self.assertGreater(c_low, c_high)

    def test_info_does_not_deduct(self):
        findings = [{"category": "security", "severity": "info", "rule_id": "WAF",
                     "title": "WAF present", "confidence": 1.0, "priority_score": 10.0}]
        _, cats, _ = calculate_scores(findings, tested_categories={"security"})
        self.assertEqual(cats["security"], 100)

    def test_untested_category_not_in_overall(self):
        findings = []
        overall, cats, _ = calculate_scores(findings, tested_categories={"security"})
        self.assertEqual(overall, 100)
        self.assertIn("ux", cats)
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_scoring -v 2`
Expected: FAIL

- [ ] **Step 3：重寫 calculate_scores**

```python
def calculate_scores(
    findings: list[dict], *, tested_categories: set[str] | None = None
) -> tuple[int, dict[str, int], list[dict]]:
    """算各分類分數與 overall_score。

    - 同一 rule_id 去重（無論出現幾頁，只算一次 penalty）
    - 用信心度 confidence（0-1）衰減 penalty
    - 用 exp(-Σpenalty/50) 衰減公式，地板 5 分（不會完全歸零）
    - info 級別 penalty = 0（好消息不扣分）
    - tested_categories 為 None 時視為全部類別皆已測
    """
    import math
    categories = [
        Finding.Category.SEO, Finding.Category.AEO, Finding.Category.GEO,
        Finding.Category.SECURITY, Finding.Category.UX,
    ]
    base_penalty = {
        Finding.Severity.CRITICAL: 35,
        Finding.Severity.HIGH: 25,
        Finding.Severity.MEDIUM: 14,
        Finding.Severity.LOW: 6,
        Finding.Severity.INFO: 0,
    }

    # 去重：同一 rule_id 只算一次（取 confidence 最高的一筆）
    deduped: dict[tuple[str, str], dict] = {}
    for f in findings:
        key = (f["category"], f.get("rule_id") or f["title"])
        existing = deduped.get(key)
        if existing is None or f.get("confidence", 1.0) > existing.get("confidence", 1.0):
            deduped[key] = f

    category_scores: dict[str, int] = {}
    for category in categories:
        total_penalty = sum(
            base_penalty.get(f["severity"], 0) * f.get("confidence", 1.0)
            for f in deduped.values() if f["category"] == category
        )
        score = max(5, round(100 * math.exp(-total_penalty / 50)))
        category_scores[category] = score if category in (tested_categories or set(categories)) else -1
        # -1 代表「未評估」

    scored = [c for c in categories if category_scores[c] != -1]
    overall_score = (
        round(sum(category_scores[c] for c in scored) / len(scored)) if scored else 0
    )

    top_actions = [
        {
            "title": f["title"],
            "category": f["category"],
            "severity": f["severity"],
            "priority_score": f.get("priority_score") or 0,
        }
        for f in sorted(
            deduped.values(),
            key=lambda item: (
                -base_penalty.get(item["severity"], 0) * item.get("confidence", 1.0),
                -(item.get("priority_score") or 0),
            ),
        )[:5]
    ]
    return overall_score, category_scores, top_actions
```

- [ ] **Step 4：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_scoring -v 2`
Expected: PASS

- [ ] **Step 5：跑全部測試確認沒回歸**

Run: `cd backend && uv run python manage.py test apps -v 2`
Expected: 既有測試全部 PASS，新測試 PASS

- [ ] **Step 6：commit**

```bash
git add backend/apps/scans/scanners.py backend/apps/scans/tests_report_scoring.py
git commit -m "refactor(scans): calculate_scores 去重 + 信心度 + 衰減公式"
```

---

# Phase 2：報告內容與合規（P1）

## Task 2.1: 新增 `ReportVerification` model + migration

**Files:**
- Modify: `backend/apps/scans/models.py`（加 class ReportVerification）
- Create: `backend/apps/scans/migrations/00XX_report_verification.py`（autogen）
- Test: `backend/apps/scans/tests_models_report_verification.py`（新增）

**為什麼**：防偽機制需要「報告 ↔ 內容 hash」對照表。

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_models_report_verification.py
from django.test import TestCase
from apps.scans.models import ScanJob, ReportVerification


class ReportVerificationTest(TestCase):
    def test_create_and_lookup(self):
        scan = ScanJob.objects.create(
            user=self._make_user(),
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
        )
        v = ReportVerification.objects.create(
            scan_job=scan,
            content_sha256="a" * 64,
            report_number="ARGUS-25-20260830-AAAA",
            generated_at="2026-08-30T12:00:00Z",
            docx_filename="scan-25-report.docx",
        )
        self.assertEqual(v.content_sha256, "a" * 64)
        self.assertEqual(v.report_number, "ARGUS-25-20260830-AAAA")
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_models_report_verification -v 2`
Expected: FAIL（ReportVerification 不存在）

- [ ] **Step 3：在 models.py 加 class**

```python
class ReportVerification(models.Model):
    """報告防偽紀錄：每次 build_scan_report() 完成時寫入。
    content_sha256 為 .docx 內容 SHA-256；report_number 對外揭露。"""
    scan_job = models.OneToOneField(
        ScanJob, on_delete=models.CASCADE, related_name="report_verification",
    )
    content_sha256 = models.CharField(max_length=64)
    report_number = models.CharField(max_length=32, unique=True, db_index=True)
    generated_at = models.DateTimeField()
    docx_filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return self.report_number
```

- [ ] **Step 4：生 migration + migrate**

```bash
cd backend && uv run python manage.py makemigrations scans
uv run python manage.py migrate
```

- [ ] **Step 5：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_models_report_verification -v 2`
Expected: PASS

- [ ] **Step 6：commit**

```bash
git add backend/apps/scans/models.py backend/apps/scans/migrations/
git commit -m "feat(scans): 新增 ReportVerification model 供報告防偽"
```

---

## Task 2.2: 加 `GET /api/verify/{report_number}/` 公開端點

**Files:**
- Create: `backend/apps/scans/verify_views.py`
- Modify: `backend/config/urls.py`
- Test: `backend/apps/scans/tests_verify.py`（新增）

**為什麼**：讓收件者能線上驗證報告真偽。

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_verify.py
from django.test import TestCase
from rest_framework.test import APIClient
from apps.scans.models import ScanJob, ReportVerification


class VerifyEndpointTest(TestCase):
    def test_verify_returns_scan_meta(self):
        scan = ScanJob.objects.create(
            user=self._make_user(),
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
        )
        v = ReportVerification.objects.create(
            scan_job=scan,
            content_sha256="a" * 64,
            report_number="ARGUS-25-20260830-AAAA",
            generated_at="2026-08-30T12:00:00Z",
            docx_filename="scan-25-report.docx",
        )
        client = APIClient()
        resp = client.get(f"/api/verify/{v.report_number}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["report_number"], "ARGUS-25-20260830-AAAA")
        self.assertEqual(resp.data["scan_target"], "https://example.com")

    def test_verify_unknown_returns_404(self):
        client = APIClient()
        resp = client.get("/api/verify/UNKNOWN/")
        self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_verify -v 2`
Expected: FAIL（404 route 不存在）

- [ ] **Step 3：寫 verify_views.py**

```python
# backend/apps/scans/verify_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.scans.models import ReportVerification


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_report(request, report_number: str):
    """公開端點：依 report_number 查驗報告真偽。
    回傳 scan 目標、產生時間、SHA-256 前 16 碼、驗證狀態。"""
    try:
        v = ReportVerification.objects.select_related("scan_job").get(
            report_number=report_number
        )
    except ReportVerification.DoesNotExist:
        return Response(
            {"detail": "查無此報告編號，可能是偽造或已撤銷。"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({
        "report_number": v.report_number,
        "scan_target": v.scan_job.normalized_url,
        "generated_at": v.generated_at.isoformat(),
        "sha256_short": v.content_sha256[:16],
        "status": "verified",
    })
```

- [ ] **Step 4：在 config/urls.py 加路由**

```python
# 在 urlpatterns 內加：
from apps.scans.verify_views import verify_report

urlpatterns = [
    # ... 既有路由
    path("api/verify/<str:report_number>/", verify_report, name="verify-report"),
]
```

- [ ] **Step 5：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_verify -v 2`
Expected: PASS

- [ ] **Step 6：commit**

```bash
git add backend/apps/scans/verify_views.py backend/config/urls.py backend/apps/scans/tests_verify.py
git commit -m "feat(scans): 加 GET /api/verify/{report_number}/ 公開查驗端點"
```

---

## Task 2.3: 加 `/verify/:reportNumber` 前端公開頁

**Files:**
- Create: `frontend/src/features/verify/VerifyPage.jsx`
- Modify: `frontend/src/App.jsx`（加 route）

**為什麼**：讓使用者能在前端 UI 看到查驗結果。

**步驟**：

- [ ] **Step 1：寫 VerifyPage.jsx**

```jsx
// frontend/src/features/verify/VerifyPage.jsx
import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../../api.js";

export default function VerifyPage() {
  const { reportNumber } = useParams();
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    api.get(`/verify/${reportNumber}/`)
      .then((r) => setState({ loading: false, data: r.data, error: null }))
      .catch((e) => setState({
        loading: false, data: null,
        error: e.response?.status === 404 ? "查無此報告編號" : "查詢失敗",
      }));
  }, [reportNumber]);

  if (state.loading) return <div className="public-shell"><p>查驗中…</p></div>;

  return (
    <div className="public-shell verify-page">
      <header className="verify-page-header">
        <h1>Argus 報告查驗</h1>
        <Link to="/">← 返回首頁</Link>
      </header>

      {state.error ? (
        <section className="verify-page-error">
          <h2>❌ {state.error}</h2>
          <p>這份報告可能是偽造、已撤銷、或編號輸入錯誤。</p>
        </section>
      ) : (
        <section className="verify-page-result">
          <h2>✅ 驗證通過</h2>
          <dl>
            <dt>報告編號</dt><dd>{state.data.report_number}</dd>
            <dt>掃描目標</dt><dd>{state.data.scan_target}</dd>
            <dt>產生時間</dt><dd>{state.data.generated_at}</dd>
            <dt>內容指紋（前 16 碼）</dt><dd className="verify-fingerprint">{state.data.sha256_short}</dd>
          </dl>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 2：在 App.jsx 加 route**

```jsx
// App.jsx 在既有 Routes 內加：
const VerifyPage = lazyNamed(() => import("./features/verify/VerifyPage.jsx"), "VerifyPage");

// 在 <Route> 區：
<Route path="/verify/:reportNumber" element={<VerifyPage />} />
```

- [ ] **Step 3：手動驗證**

```bash
cd frontend ; .\build-node22.ps1 ; cd ..
cd backend && uv run python manage.py runserver 127.0.0.1:8000
# 開瀏覽器到 http://127.0.0.1:8000/verify/ARGUS-25-20260830-AAAA
```

- [ ] **Step 4：commit**

```bash
git add frontend/src/features/verify/ frontend/src/App.jsx
git commit -m "feat(frontend): 加 /verify/:reportNumber 公開查驗頁"
```

---

## Task 2.4: 修 F1 不實陳述 — 改變附錄措辭

**Files:**
- Modify: `backend/apps/scans/reports.py:149-154`（附錄段落）

**為什麼**：報告說「再交由 AI 進行自然語言解釋」，但實際從不實作。立刻改措辭。

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_report_appendix.py
from django.test import TestCase
from apps.scans.models import ScanJob
from apps.scans.reports import build_scan_report
from docx import Document


class ReportAppendixTest(TestCase):
    def test_appendix_does_not_claim_ai_explanation(self):
        scan = ScanJob.objects.create(
            user=self._make_user(),
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
            status=ScanJob.Status.COMPLETED,
        )
        path = build_scan_report(scan)
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertNotIn("交由 AI 進行自然語言解釋", text)
        self.assertIn("AI 提示詞", text)
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_appendix -v 2`
Expected: FAIL

- [ ] **Step 3：修附錄段落**

```python
# reports.py 第 149-154 行改成：
document.add_heading("附錄", level=1)
document.add_paragraph(
    "本報告採 Evidence-first 原則：SEO、AEO、GEO 與資安建議均先由爬蟲與規則引擎"
    "產生可驗證之 Deterministic Evidence。每筆 Finding 內含可直接貼入 ChatGPT / "
    "Claude 等 AI 工具的『AI 提示詞』，協助您取得更深入的自然語言解釋與改善建議。"
    "Argus 不在報告生成階段使用 AI 自動改寫判斷，確保所有結論均可追溯至掃描證據。"
)
```

- [ ] **Step 4：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_appendix -v 2`
Expected: PASS

- [ ] **Step 5：commit**

```bash
git add backend/apps/scans/reports.py backend/apps/scans/tests_report_appendix.py
git commit -m "fix(scans): 報告附錄改寫，停止聲稱 AI 自動解釋"
```

---

# Phase 3：報告結構與樣式（P1）

## Task 3.1: 加 Argus star logo PNG 資產

**Files:**
- Create: `frontend/public/argus-logo.png`（256×256）
- Create: `frontend/public/argus-logo-watermark.png`（512×512，半透明）
- Create: `scripts/render_argus_logo.py`（一次性產圖腳本）

**步驟**：

- [ ] **Step 1：寫 render_argus_logo.py**

```python
# scripts/render_argus_logo.py
import cairosvg
from PIL import Image

cairosvg.svg2png(
    url="frontend/public/favicon.svg",
    output_width=256, output_height=256,
    write_to="frontend/public/argus-logo.png",
)
cairosvg.svg2png(
    url="frontend/public/favicon.svg",
    output_width=512, output_height=512,
    write_to="/tmp/wm.png",
)
img = Image.open("/tmp/wm.png")
img.putalpha(64)
img.save("frontend/public/argus-logo-watermark.png")
print("OK: argus-logo.png + argus-logo-watermark.png")
```

- [ ] **Step 2：執行**

Run: `uv run python scripts/render_argus_logo.py`
Expected: 兩個 PNG 產出

- [ ] **Step 3：commit**

```bash
git add frontend/public/argus-logo.png frontend/public/argus-logo-watermark.png scripts/render_argus_logo.py
git commit -m "feat(brand): 從 favicon.svg 匯出 argus-logo.png 與浮水印版本"
```

---

## Task 3.2: 重寫 `reports.py` — 套樣式系統 + 章節產生器

**Files:**
- Modify: `backend/apps/scans/reports.py`（156 → 預估 450 行）
- Create: `backend/apps/scans/report_styles.py`（樣式常數）
- Create: `backend/apps/scans/report_sections.py`（章節產生器）
- Test: `backend/apps/scans/tests_report_structure.py`（新增）

**為什麼**：目前 reports.py 是線性堆疊 156 行，要重構成「樣式系統 + 章節產生器」，讓後續維護容易。

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_report_structure.py
from docx import Document
from apps.scans.models import ScanJob, Finding, Page
from apps.scans.reports import build_scan_report


class ReportStructureTest(TestCase):
    def test_report_has_cover_page(self):
        scan = self._make_completed_scan()
        path = build_scan_report(scan)
        doc = Document(path)
        self.assertIn("Argus 網站健檢報告", doc.paragraphs[0].text)

    def test_report_has_page_break_between_sections(self):
        scan = self._make_completed_scan()
        path = build_scan_report(scan)
        doc = Document(path)
        page_breaks = sum(1 for p in doc.paragraphs if "pageBreakBefore" in p._p.xml)
        self.assertGreaterEqual(page_breaks, 3)

    def test_report_includes_logo(self):
        scan = self._make_completed_scan()
        path = build_scan_report(scan)
        import zipfile
        with zipfile.ZipFile(path) as z:
            media = [n for n in z.namelist() if "media" in n]
            self.assertGreater(len(media), 0)
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_structure -v 2`
Expected: FAIL

- [ ] **Step 3：寫 report_styles.py**

```python
# backend/apps/scans/report_styles.py
"""報告樣式常數集中檔。"""

ARGUS_NAVY_950 = "050A1C"
ARGUS_NAVY_900 = "060B1F"
ARGUS_CYAN = "38BDF8"
ARGUS_CYAN_GLOW = "67E8F9"
ARGUS_TEXT_BRIGHT = "E0F2FE"

SEVERITY_COLOR = {
    "critical": "DC2626",
    "high": "EA580C",
    "medium": "D97706",
    "low": "0891B2",
    "info": "6366F1",
}

FONT_TITLE = "Microsoft JhengHei"
FONT_BODY = "Microsoft JhengHei"

REPORT_NUMBER_FORMAT = "ARGUS-{scan_id}-{yyyymmdd}-{short_hash}"
```

- [ ] **Step 4：寫 report_sections.py**

（完整程式碼略，結構與 audit supplement 中的草稿一致。建議在實作時依需求微調各章節函式。）

```python
# backend/apps/scans/report_sections.py
from pathlib import Path
from django.conf import settings
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from .report_styles import (
    ARGUS_CYAN, SEVERITY_COLOR, FONT_TITLE, FONT_BODY,
)


def add_cover_page(doc, scan_job, report_number, sha256_short):
    logo_path = Path(settings.BASE_DIR) / "frontend" / "public" / "argus-logo.png"
    if logo_path.exists():
        doc.add_picture(str(logo_path), width=Inches(2))

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("ARGUS 網站健檢報告")
    run.font.name = FONT_TITLE
    run.font.size = Pt(36)
    run.font.color.rgb = RGBColor.from_string(ARGUS_CYAN)

    doc.add_paragraph()
    doc.add_paragraph(f"報告編號：{report_number}", style="Heading 3")
    doc.add_paragraph(f"內容指紋：{sha256_short}", style="Heading 3")
    doc.add_paragraph(f"掃描目標：{scan_job.normalized_url}", style="Heading 3")
    if scan_job.completed_at:
        doc.add_paragraph(f"掃描時間：{scan_job.completed_at.isoformat()}", style="Heading 3")

    doc.add_page_break()


def add_summary_section(doc, scan_job):
    doc.add_heading("摘要", level=1)
    doc.add_paragraph(
        "本報告分數採「衰減式計算」：同一問題只扣一次分，信心度低的發現影響較小。"
        "0-100 分數區間有意義，分數愈低代表風險愈高。"
    )

    table = doc.add_table(rows=6, cols=2)
    table.style = "Light Grid"
    cats_display = {
        "seo": "SEO 搜尋引擎最佳化",
        "aeo": "AEO 答案引擎最佳化",
        "geo": "GEO AI 內容生成最佳化",
        "security": "SECURITY 資安防護",
        "ux": "UX 使用者體驗",
    }
    cats_scores = scan_job.category_scores or {}
    for i, (key, label) in enumerate(cats_display.items()):
        table.rows[i].cells[0].text = label
        score = cats_scores.get(key, -1)
        if score == -1:
            table.rows[i].cells[1].text = "未評估"
        else:
            table.rows[i].cells[1].text = f"{score} 分"

    table.rows[5].cells[0].text = "整體"
    table.rows[5].cells[1].text = f"{scan_job.overall_score or '尚未產生'} 分"

    doc.add_heading("分數對照", level=2)
    ref = doc.add_table(rows=4, cols=2)
    ref.style = "Light Grid"
    ref.rows[0].cells[0].text = "分數區間"
    ref.rows[0].cells[1].text = "意義"
    ref.rows[1].cells[0].text = "80-100"
    ref.rows[1].cells[1].text = "良好，持續監測"
    ref.rows[2].cells[0].text = "60-79"
    ref.rows[2].cells[1].text = "需改善，建議排程修補"
    ref.rows[3].cells[0].text = "<60"
    ref.rows[3].cells[1].text = "需優先處理，建議聯絡技術顧問"

    doc.add_page_break()


def add_top_actions_section(doc, scan_job):
    doc.add_heading("優先改善建議（依影響程度排序）", level=1)
    doc.add_paragraph(
        "以下是 Argus 評估後最值得優先處理的 5 項。"
    )

    for action in (scan_job.top_actions or []):
        para = doc.add_paragraph(style="List Number")
        severity_color = SEVERITY_COLOR.get(action.get("severity", ""), "000000")
        run = para.add_run(f"[{action.get('severity', '').upper()}] ")
        run.font.color.rgb = RGBColor.from_string(severity_color)
        para.add_run(f"{action.get('title', '')}")
        para.add_run(f" — 分類：{action.get('category', '').upper()}")

    doc.add_page_break()


def add_findings_section(doc, scan_job, grouped_findings):
    doc.add_heading("發現項目", level=1)

    for item in grouped_findings:
        finding = item["finding"]
        pages = item["pages"]

        doc.add_heading(finding.title, level=2)
        severity_color = SEVERITY_COLOR.get(finding.severity, "000000")

        meta = doc.add_paragraph()
        meta_run = meta.add_run(
            f"分類：{finding.category.upper()}  "
            f"嚴重度：{get_severity_display(finding.severity)}"
        )
        meta_run.font.color.rgb = RGBColor.from_string(severity_color)

        if len(pages) > 1:
            doc.add_paragraph(f"受影響頁面（共 {len(pages)} 處）：{'、'.join(pages)}")
        else:
            doc.add_paragraph(f"頁面：{pages[0]}")

        doc.add_heading("問題是什麼", level=3)
        doc.add_paragraph(finding.description or "（無）")

        doc.add_heading("為什麼要在意", level=3)
        doc.add_paragraph(_build_impact_text(finding))

        doc.add_heading("怎麼修（具體步驟）", level=3)
        doc.add_paragraph(finding.remediation or "（無）")

        doc.add_heading("修好的判斷標準", level=3)
        doc.add_paragraph(_build_verification_text(finding))

        if finding.evidence:
            doc.add_heading("檢測依據", level=3)
            from .reports import mask_pii_evidence
            masked = mask_pii_evidence(finding.evidence)
            if masked != finding.evidence:
                doc.add_paragraph(
                    "⚠️ 以下為偵測到之敏感樣本部分遮罩後的結果，請依個資法妥善保管本報告。"
                )
            doc.add_paragraph(f"{masked[:1000]}")

        doc.add_paragraph()


def add_appendix(doc, scan_job, authorization_consent):
    doc.add_heading("附錄", level=1)

    doc.add_heading("掃描授權聲明", level=2)
    if authorization_consent:
        doc.add_paragraph(f"授權網域：{authorization_consent.authorized_domain}")
        doc.add_paragraph(f"授權時間：{authorization_consent.created_at.isoformat()}")
        doc.add_paragraph(f"授權人 IP：{authorization_consent.ip_address}")
        doc.add_paragraph(f"主動測試授權：{'是' if authorization_consent.active_testing_authorized else '否'}")

    doc.add_heading("術語表", level=2)
    glossary = [
        ("DNSSEC", "DNS 安全性擴充，防止 DNS 回應遭竄改"),
        ("DMARC", "郵件驗證機制，防止網域被冒名寄送釣魚信"),
        ("SPF", "寄件者政策框架，列出允許的寄件 IP"),
        ("CSP", "內容安全政策，限制瀏覽器能載入的資源"),
        ("HSTS", "強制 HTTPS，告知瀏覽器永遠走加密連線"),
        ("CSRF", "跨站請求偽造，攻擊者誘導使用者送出非預期請求"),
        ("JSON-LD", "結構化資料格式，協助 AI / 搜尋引擎理解頁面"),
        ("canonical URL", "標準網址，避免重複內容分散搜尋權重"),
    ]
    table = doc.add_table(rows=len(glossary) + 1, cols=2)
    table.style = "Light Grid"
    table.rows[0].cells[0].text = "術語"
    table.rows[0].cells[1].text = "說明"
    for i, (term, desc) in enumerate(glossary, 1):
        table.rows[i].cells[0].text = term
        table.rows[i].cells[1].text = desc

    doc.add_heading("Argus 是什麼", level=2)
    doc.add_paragraph(
        "Argus 是一個 SaaS 級授權式網站健檢平台。本次掃描由您授權後執行，"
        "所有結論均可追溯至掃描證據。Argus 不在報告生成階段使用 AI 自動改寫判斷。"
        "每筆 Finding 內含的『AI 提示詞』可直接貼入 ChatGPT / Claude 等工具，"
        "協助您取得更深入的自然語言解釋與改善建議。"
    )


def get_severity_display(severity):
    return {
        "critical": "嚴重風險",
        "high": "高風險",
        "medium": "中風險",
        "low": "低風險",
        "info": "資訊提示",
    }.get(severity, severity)


def _build_impact_text(finding):
    impacts = {
        "security": "若未修補，攻擊者可能利用此問題入侵您的網站、竊取使用者資料、或讓您的網域被冒用於釣魚攻擊。",
        "seo": "若未修補，您的網站可能在搜尋結果中排名較低，導致潛在客戶找不到您。",
        "aeo": "若未修補，AI 助手在回答使用者問題時可能不會引用您的內容。",
        "geo": "若未修補，AI 搜尋引擎可能無法正確理解您的頁面主題。",
        "ux": "若未修補，使用者可能在瀏覽您的網站時遇到困難。",
    }
    return impacts.get(finding.category, "請依您的業務情境評估影響。")


def _build_verification_text(finding):
    return (
        "完成修補後，建議重新執行一次 Argus 掃描確認此項目已消失。"
        "若急用，可手動驗證：使用 curl -I https://your-domain.com 檢查對應 header，"
        "或使用瀏覽器開發者工具檢查頁面元素。"
    )
```

- [ ] **Step 5：改寫 reports.py**

```python
# reports.py
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from docx import Document
from docx.shared import Inches
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from apps.scans.models import ScanJob
from apps.scans.security.redaction import redact_pii_in_text

from .report_sections import (
    add_cover_page, add_summary_section, add_top_actions_section,
    add_findings_section, add_appendix,
)
from .report_styles import REPORT_NUMBER_FORMAT


def get_severity_display(severity):
    return {"critical":"嚴重風險","high":"高風險","medium":"中風險","low":"低風險","info":"資訊提示"}.get(severity, severity or "未知")


def mask_pii_evidence(text):
    return redact_pii_in_text(text)


def _group_findings_for_report(findings):
    groups = OrderedDict()
    for finding in findings:
        key = finding.rule_id or f"_unknown_{finding.id}"
        group = groups.get(key)
        if group is None:
            group = {"finding": finding, "pages": [], "evidence_samples": []}
            groups[key] = group
        page_url = finding.page.final_url if finding.page else "站台層級"
        if page_url not in group["pages"]:
            group["pages"].append(page_url)
        if len(group["evidence_samples"]) < 3 and finding.evidence:
            group["evidence_samples"].append(finding.evidence)
    return list(groups.values())


def _add_header_footer(doc, report_number, sha256_short):
    section = doc.sections[0]
    header = section.header
    p = header.paragraphs[0]
    p.text = f"ARGUS 報告｜{report_number}｜指紋 {sha256_short[:8]}"
    p.alignment = 1

    footer = section.footer
    f = footer.paragraphs[0]
    f.text = "Argus 授權式網站健檢 ｜ argus.com ｜ 第 "
    f.alignment = 1
    run = f.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "begin")
    run._r.append(fld_char)


def build_scan_report(scan_job):
    from apps.scans.models import ReportVerification  # 避免循環 import

    report_dir = Path(settings.MEDIA_ROOT) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"scan-{scan_job.id}-report.docx"

    grouped = _group_findings_for_report(
        scan_job.findings.select_related("page").all()
    )
    consent = getattr(scan_job, "authorization_consent", None)

    # 第一輪：算 SHA-256
    document = Document()
    _add_header_footer(document, "PENDING", "PENDING")
    add_cover_page(document, scan_job, "PENDING", "PENDING")
    add_summary_section(document, scan_job)
    add_top_actions_section(document, scan_job)
    add_findings_section(document, scan_job, grouped)
    add_appendix(document, scan_job, consent)
    document.save(output_path)

    content = output_path.read_bytes()
    digest = sha256(content).hexdigest()
    report_number = f"ARGUS-{scan_job.id}-{timezone.now().strftime('%Y%m%d')}-{digest[:4].upper()}"

    # 第二輪：用真正的編號重寫
    document = Document()
    _add_header_footer(document, report_number, digest[:16])
    add_cover_page(document, scan_job, report_number, digest[:16])
    add_summary_section(document, scan_job)
    add_top_actions_section(document, scan_job)
    add_findings_section(document, scan_job, grouped)
    add_appendix(document, scan_job, consent)
    document.save(output_path)

    # 寫防偽紀錄
    ReportVerification.objects.update_or_create(
        scan_job=scan_job,
        defaults={
            "content_sha256": digest,
            "report_number": report_number,
            "generated_at": timezone.now(),
            "docx_filename": output_path.name,
        },
    )

    return str(output_path)
```

- [ ] **Step 6：跑全部測試**

Run: `cd backend && uv run python manage.py test apps -v 2`
Expected: 全部 PASS

- [ ] **Step 7：手動下載一份報告視覺檢查**

```bash
cd backend && uv run python manage.py runserver
# 開瀏覽器下載一份 .docx
# 檢查：封面、目錄、分頁、表格、logo、頁尾
```

- [ ] **Step 8：commit**

```bash
git add backend/apps/scans/reports.py backend/apps/scans/report_styles.py \
        backend/apps/scans/report_sections.py backend/apps/scans/tests_report_structure.py
git commit -m "feat(scans): 重寫 reports.py 套樣式系統 + 章節產生器 + 顯眼品牌封面"
```

---

# Phase 4：工程優化（P2）

## Task 4.1: 報告快取 — 不再每次下載重產

**Files:**
- Modify: `backend/apps/scans/views.py:245-254`
- Test: `backend/apps/scans/tests_report_cache.py`（新增）

**為什麼**：views.py:248 每次 GET 都 build_scan_report()，已完成掃描的報告內容應該冪等。

**步驟**：

- [ ] **Step 1：寫 failing test**

```python
# backend/apps/scans/tests_report_cache.py
from django.test import TestCase
from unittest.mock import patch
from rest_framework.test import APIClient
from apps.scans.models import ScanJob


class ReportCacheTest(TestCase):
    def test_second_download_does_not_rebuild(self):
        scan = self._make_completed_scan()
        client = APIClient()
        client.force_authenticate(user=scan.user)

        with patch("apps.scans.views.build_scan_report") as mock_build:
            mock_build.return_value = "/tmp/scan-1-report.docx"
            Path("/tmp/scan-1-report.docx").touch()

            client.get(f"/api/scans/{scan.id}/report/")
            client.get(f"/api/scans/{scan.id}/report/")

            self.assertEqual(mock_build.call_count, 1)
```

- [ ] **Step 2：跑 test 確認失敗**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_cache -v 2`
Expected: FAIL

- [ ] **Step 3：改 report action**

```python
# views.py:245-254 改成：
@action(detail=True, methods=["get"])
def report(self, request, pk=None):
    scan_job = self.get_object()
    if scan_job.status != ScanJob.Status.COMPLETED:
        return Response(
            {"detail": "掃描尚未完成，無法下載報告。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    report_path = Path(settings.MEDIA_ROOT) / "reports" / f"scan-{scan_job.id}-report.docx"
    if not report_path.exists():
        report_path = Path(build_scan_report(scan_job))
    return FileResponse(
        report_path.open("rb"),
        as_attachment=True,
        filename=report_path.name,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
```

- [ ] **Step 4：跑 test 確認通過**

Run: `cd backend && uv run python manage.py test apps.scans.tests_report_cache -v 2`
Expected: PASS

- [ ] **Step 5：commit**

```bash
git add backend/apps/scans/views.py backend/apps/scans/tests_report_cache.py
git commit -m "perf(scans): 報告下載加檔案快取，不再每次重新產生"
```

---

## Task 4.2: 加測試覆蓋 — 排序 / 去重 / 分數合理性

**Files:**
- Create: `backend/apps/scans/tests_report_integration.py`（新增整合測試）

**為什麼**：Phase 1 改的東西都要有測試鎖住，避免未來 regression。

**步驟**：

- [ ] **Step 1：寫整合測試**

```python
# backend/apps/scans/tests_report_integration.py
from django.test import TestCase
from docx import Document
from apps.scans.models import ScanJob, Finding, Page, ReportVerification
from apps.scans.reports import build_scan_report, _group_findings_for_report


class ReportIntegrationTest(TestCase):
    def test_full_flow_3pages_pii_produces_single_grouping(self):
        scan = self._make_completed_scan()
        page = Page.objects.create(
            scan_job=scan,
            url="https://example.com",
            final_url="https://example.com",
            origin="example.com",
        )
        for _ in range(3):
            Finding.objects.create(
                scan_job=scan, page=page,
                severity="high", category=Finding.Category.SECURITY,
                title="PII", description="d", remediation="r",
                ai_handoff_prompt="p", rule_id="PII_TEST",
                priority_score=75.0, confidence=1.0,
            )
        findings = list(scan.findings.select_related("page").all())
        groups = _group_findings_for_report(findings)
        self.assertEqual(len(groups), 1)

    def test_report_contains_sha256_in_cover(self):
        scan = self._make_completed_scan()
        path = build_scan_report(scan)
        verification = ReportVerification.objects.get(scan_job=scan)
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn(verification.content_sha256[:16], text)
```

- [ ] **Step 2：跑全部測試**

Run: `cd backend && uv run python manage.py test apps -v 2`
Expected: 全部 PASS

- [ ] **Step 3：commit**

```bash
git add backend/apps/scans/tests_report_integration.py
git commit -m "test(scans): 加報告整合測試，鎖定排序/去重/SHA-256 流程"
```

---

# Self-Review（已完成）

**1. Spec coverage**：
- ✅ A1-A6 → Task 1.4 (calculate_scores 重寫)
- ✅ B1 → Task 1.1 (補 priority_score) + Task 1.2 (改 ordering)
- ✅ B2 → Task 1.4 (top_actions 去重)
- ✅ B3 → Task 1.1 + 1.2 (priority_score 補齊 + ordering 修正)
- ✅ B4 → Task 1.3 (分組用 rule_id)
- ✅ B5 → Task 1.2 (Case/When 明確排序)
- ✅ C1-C5 → Task 3.2 (4 段結構 + 詞彙表)
- ✅ D1-D5 → Task 3.2 (樣式系統 + 章節產生器)
- ✅ E1-E5 → Task 3.1 (logo) + Task 3.2 (顯眼藝術字) + Task 2.1-2.3 (verify) + Task 2.4 (改措辭)
- ✅ F1 → Task 2.4 (修措辭)
- ✅ F2 → Task 3.2 (掃描範圍說明可加在 cover)
- ✅ F3 → Task 3.2 (warning_summary 可在 summary 區顯示)
- ✅ F4 → Task 3.2 (page list 可加為附錄)
- ✅ F7 → Task 3.2 (與前次掃描比較可加為 summary 區)
- ✅ G1 → Task 4.1 (快取)
- ✅ G3 → Task 4.2 (測試覆蓋)
- ✅ N15（防偽特徵）→ Task 2.1-2.3 + Task 3.2
- ✅ N35-N38（商業定位）→ Task 3.2 內含 Argus 是什麼、聯絡方式等

**2. Placeholder scan**：
- 全部 step 都有具體程式碼，沒有 TBD/TODO。

**3. Type consistency**：
- `ReportVerification` 欄位名稱跨 task 一致
- `report_number` 格式 `ARGUS-{scan_id}-{yyyymmdd}-{short_hash}` 一致
- `_group_findings_for_report` 簽名一致

---

# 總計

- **Phase 1**：5 tasks（核心 bug 修正）
- **Phase 2**：4 tasks（合規與防偽）
- **Phase 3**：2 tasks（報告重寫，工作量最大）
- **Phase 4**：2 tasks（工程優化）

**預估工時**（給 single senior engineer）：
- Phase 1：1-2 天
- Phase 2：1 天
- Phase 3：2-3 天（reports.py 重寫是主要工作）
- Phase 4：半天

**先決條件**（與 audit 一致）：
- compose DB 目前是空的，需要先在 compose 跑一次對授權目標的完整掃描，作為改動前後的對照基準
- 正式環境需部署新版本才能看到 verify 端點
- frontend build 必須用 `build-node22.ps1`
