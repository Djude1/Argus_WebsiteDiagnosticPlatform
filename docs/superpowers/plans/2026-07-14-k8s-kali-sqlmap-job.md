# K8s Kali SQLmap Job Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Argus 正式 Kubernetes 以受控、單工、可取消的 Job 恢復 SQLmap，讓 Hermes-Agent 優先決策、規則式 fallback 共用最多 3 個目標的政策，且 Secret at-rest encryption 通過前維持停用。

**Architecture:** 保留 kali_tools.py 作 public facade，新增契約／政策／Kubernetes executor 三個聚焦模組；AI 與 fallback 都先經同一個 Redis 原子預算，再由 docker 或 kubernetes executor 執行。Kubernetes 路徑用短效 Secret 傳入 URL、固定 digest runner 輸出安全 JSON，並以獨立 namespace、最小 RBAC、NetworkPolicy、ResourceQuota 與 ValidatingAdmissionPolicy 防止 worker 任意建立攻擊 Pod。

**Tech Stack:** Python 3.12、Django 5、Celery、redis-py 5、Kubernetes Python client 35.x、Kubernetes 1.35、Calico、Docker Buildx、GitHub Actions、Kustomize、Argo CD

## Global Constraints

- 以 docs/superpowers/specs/2026-07-14-k8s-kali-sqlmap-job-design.md 為唯一需求規格；若實作需要改需求，先停下回到 brainstorming 更新規格。
- 本輪只支援 SQLmap；Metasploit Kubernetes runner、Nmap、專用 controller、多 Job 排程與自動 key rotation 不加入實作。
- ARGUS_KALI_ENABLED 預設 false；ARGUS_KALI_BACKEND 預設 disabled。
- 每個 ScanJob 最多 3 個 SHA-256 指紋不同的目標；Redis 狀態 TTL 86400 秒。
- 單一 target timeout 120 秒；startup grace 30 秒；Job deadline 為 target_count × 120 + 30，最大 390 秒。
- worker Job watch timeout 為 active deadline + 30 秒，最大 420 秒。
- lock wait 最多 420 秒；lock lease 450 秒且需續租；每個 ScanJob Kali 累計 deadline 900 秒。
- runner 結果最大 16384 bytes，schema_version 固定 1；禁止保存 raw SQLmap stdout、完整 query value、HTTP body 或資料庫內容。
- Kubernetes Secret at-rest encryption 六項門檻完成前，正式 k8s/01-namespace-config.yaml 必須維持 disabled／false。
- Kubernetes API egress 只能是部署前重新確認的 Service /32:443 與 endpoint /32:6443；不得放寬到私網大網段。
- 使用者取消必須刪除 Job／Secret、釋放自己持有的 lock 並重新拋出 ScanCancelled；其餘 Kali 錯誤 silent-fail。
- 結構化錯誤碼固定為 kali_disabled、backend_misconfigured、scan_not_found、scan_mode_not_active、active_testing_unauthorized、invalid_target_url、target_not_public、cross_origin_forbidden、no_query_parameter、target_already_tested、scan_budget_exhausted、scan_deadline_exceeded、capacity_timeout、job_create_failed、secret_create_failed、job_deadline_exceeded、runner_failed、invalid_result、cleanup_failed、tool_not_supported_by_backend。
- 不新增 Django migration，不修改 billing、前端或無關 scanner。
- 每個 code task 先寫失敗測試，再做最小實作；每個 task 通過自己的驗證後單獨 review 與 commit。
- commit author 僅對該 commit 使用 SmallLoOwO <60470295+SmallLoOwO@users.noreply.github.com>；不得改 global Git config。
- 不執行 git push、Argo Sync、正式 apply 或 control-plane 變更，除非使用者在對應 checkpoint 明確同意。

---

## File Map

### Backend contracts and orchestration

- Create backend/apps/scans/security/kali_contracts.py — dataclass、URL 遮罩、safe result schema 與 Finding evidence。
- Create backend/apps/scans/security/kali_policy.py — 三重授權、公網／同源／query 驗證、Redis deadline／去重／預算。
- Create backend/apps/scans/security/kali_kubernetes.py — Redis global lock、Job／Secret lifecycle、watch、cleanup。
- Modify backend/apps/scans/security/kali_tools.py — public facade、disabled/docker/kubernetes dispatch、Docker 相容。
- Modify backend/apps/scans/tasks.py — Hermes 優先、fallback 後置、取消傳播、security Finding 進 scoring。
- Modify backend/apps/agent/tools.py — 動態 schema、共用 executor、AgentStep 安全結果。
- Modify backend/apps/agent/loop.py — 每次 run 使用 caller 提供的 schema，持久化前遮罩 tool arguments。
- Modify backend/apps/agent/runner.py — deep mode 才傳 SQLmap schema，維持 DB persistence 邊界。
- Modify backend/config/settings.py、.env.example、pyproject.toml、uv.lock — backend／timeout／budget／namespace／client 35.x。

### Tests

- Create backend/apps/scans/tests_kali_contracts.py。
- Create backend/apps/scans/tests_kali_policy.py。
- Create backend/apps/scans/tests_kali_policy_redis.py。
- Create backend/apps/scans/tests_kali_kubernetes.py。
- Create backend/apps/scans/tests_kali_pipeline.py。
- Modify backend/apps/scans/tests_kali_tools.py。
- Modify backend/apps/agent/tests.py。
- Create tests/test_kali_k8s_contract.py。
- Create tests/test_kali_image_promotion.py。
- Create tests/integration/test_kali_job.py。

### Runner, Kubernetes and CI

- Create kali-runner/Dockerfile、kali-runner/runner.py、kali-runner/tests/test_runner.py、kali-runner/README.md。
- Create k8s/10-kali-runtime.yaml — namespace、ServiceAccounts、Role／RoleBinding、quota／limits、runner policies。
- Create k8s/11-kali-admission.yaml — cluster-scoped ValidatingAdmissionPolicy／Binding。
- Modify k8s/01-namespace-config.yaml、k8s/04-backend.yaml、k8s/07-network-policies.yaml、k8s/kustomization.yaml。
- Create scripts/promote_kali_image.py。
- Create .github/workflows/build-kali-runner.yml、.github/workflows/kali-integration.yml。
- Modify .github/workflows/quality.yml。
- Create tests/integration/kind-config.yaml。
- Create tests/integration/kali-fixture/app.py、Dockerfile、fixture.yaml、network-policy-patch.yaml。

### Documentation

- Create docs/runbooks/kubernetes-secret-at-rest-encryption.md。
- Create docs/runbooks/kali-sqlmap-rollout.md。
- Modify CLAUDE.md、ONBOARDING.md、backend/apps/scans/CLAUDE.md、backend/apps/scans/security/CLAUDE.md、backend/apps/agent/CLAUDE.md、k8s/README.md、docs/capstone-roadmap.md。
- Create log/2026-07-14_k8s-kali-sqlmap-implementation.md。

## Shared Interfaces

backend/apps/scans/security/kali_contracts.py 必須產生：

~~~python
@dataclass(frozen=True)
class ReservedSqlmapTarget:
    index: int
    url: str
    fingerprint: str


@dataclass(frozen=True)
class KaliResult:
    ok: bool
    tool: str = "sqlmap"
    blocked_reason: str = ""
    returncode: int | None = None
    stdout: str = ""
    error: str = ""
    confirmed: bool = False
    evidence_summary: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "blocked_reason": self.blocked_reason,
            "returncode": self.returncode,
            "stdout": "",
            "error": self.error,
            "confirmed": self.confirmed,
            "evidence_summary": dict(self.evidence_summary),
        }


@dataclass(frozen=True)
class SqlmapExecution:
    target: ReservedSqlmapTarget
    result: KaliResult


@dataclass(frozen=True)
class ReservationOutcome:
    targets: tuple[ReservedSqlmapTarget, ...] = ()
    blocked_reason: str = ""


class SqlmapExecutor(Protocol):
    def execute(
        self,
        scan_job_id: int,
        targets: Sequence[ReservedSqlmapTarget],
    ) -> tuple[KaliResult, ...]: ...
~~~

其他 task 一律使用以下名稱，不另造同義 wrapper：

~~~python
def reserve_sqlmap_targets(
    scan_job_id: int,
    candidate_urls: Sequence[str],
    *,
    max_count: int,
) -> ReservationOutcome: ...


def run_sqlmap(target_url: str, scan_job_id: int) -> dict[str, object]: ...


def run_sqlmap_batch(
    target_urls: Sequence[str],
    scan_job_id: int,
    *,
    max_targets: int = 3,
) -> tuple[SqlmapExecution, ...]: ...


def parse_runner_result(
    payload: bytes,
    expected_targets: Sequence[ReservedSqlmapTarget],
) -> tuple[KaliResult, ...]: ...
~~~

## Preflight: establish the baseline

- [ ] **Step 1: Confirm the isolated worktree and user-owned changes**

Run:

~~~powershell
git status --short --branch
git worktree list
git diff --name-only
~~~

Expected: execution occurs in an isolated codex/* worktree; no unrelated file is staged. If AGENTS.md, .omc/, docker-compose.demo.yml or another user-owned change appears, do not touch it.

- [ ] **Step 2: Run the current backend and manifest baseline**

Run:

~~~powershell
$env:DJANGO_SECRET_KEY='ci-only-django-secret-key-at-least-32-bytes'
$env:JWT_SECRET_KEY='ci-only-jwt-secret-key-at-least-32-bytes'
$env:PASSWORD_RESET_TOKEN_PEPPER='ci-only-independent-reset-token-pepper'
$env:DJANGO_DEBUG='true'
uv run ruff check backend
uv run python backend/manage.py check
uv run python backend/manage.py test apps.scans.tests_kali_tools apps.agent
uv run python -m unittest discover -s tests
kubectl kustomize k8s
~~~

Expected: every command exits 0. Record the actual Django test count in the task log; do not copy an older count from documentation.

---

### Task 1: Safe result contracts, redaction and settings

**Files:**
- Create: backend/apps/scans/security/kali_contracts.py
- Create: backend/apps/scans/tests_kali_contracts.py
- Modify: backend/config/settings.py:297-306
- Modify: .env.example:79-83

**Interfaces:**
- Consumes: assert_public_http_url() and ScanJob origin from existing scans code.
- Produces: ReservedSqlmapTarget, KaliResult, SqlmapExecution, ReservationOutcome, SqlmapExecutor, redact_url_query_values(), parse_runner_result().

- [ ] **Step 1: Write failing contract tests**

~~~python
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
            evidence_summary={"parameter": "id", "techniques": ["boolean-based blind"]},
        ).as_dict()
        self.assertEqual(
            set(result),
            {
                "ok", "tool", "blocked_reason", "returncode", "stdout",
                "error", "confirmed", "evidence_summary",
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
~~~

- [ ] **Step 2: Verify the new tests fail**

Run: uv run python backend/manage.py test apps.scans.tests_kali_contracts -v 2

Expected: FAIL because kali_contracts cannot be imported.

- [ ] **Step 3: Implement the exact result and parser boundary**

The parser must:

- decode UTF-8 with errors=strict;
- reject payload length above settings.ARGUS_KALI_RESULT_MAX_BYTES;
- require exact top-level keys schema_version, tool, results;
- require schema_version == 1 and tool == sqlmap;
- require one result for every expected index, with no duplicates;
- allow only index, ok, confirmed, returncode, parameter, techniques, dbms, error_code in each result;
- sanitize parameter to the regex [A-Za-z0-9_.-]{0,64};
- map error_code to KaliResult.error;
- add correlation_id and tool_version only from trusted executor settings, never from runner text.

Implementation:

~~~python
MAX_RESULT_BYTES = 16_384
_RESULT_KEYS = {
    "index", "ok", "confirmed", "returncode",
    "parameter", "techniques", "dbms", "error_code",
}
SAFE_TECHNIQUES = {
    "boolean-based blind",
    "error-based",
    "inline query",
    "stacked queries",
    "time-based blind",
    "union query",
}


def redact_url_query_values(url: str) -> str:
    parsed = urlsplit(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode([(key, "[REDACTED]") for key, _value in pairs])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def parse_runner_result(payload: bytes, expected_targets):
    if len(payload) > settings.ARGUS_KALI_RESULT_MAX_BYTES:
        raise KaliResultContractError("result_too_large")
    try:
        document = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KaliResultContractError("invalid_result") from exc
    if not isinstance(document, dict):
        raise KaliResultContractError("invalid_result_type")
    if set(document) != {"schema_version", "tool", "results"}:
        raise KaliResultContractError("invalid_top_level_fields")
    if document["schema_version"] != 1 or document["tool"] != "sqlmap":
        raise KaliResultContractError("unknown_schema")
    if not isinstance(document["results"], list):
        raise KaliResultContractError("invalid_result_type")

    expected = {target.index: target for target in expected_targets}
    parsed: dict[int, KaliResult] = {}
    for item in document["results"]:
        if not isinstance(item, dict):
            raise KaliResultContractError("invalid_result_type")
        if set(item) != _RESULT_KEYS:
            raise KaliResultContractError("invalid_result_fields")
        index = item["index"]
        if not isinstance(index, int) or isinstance(index, bool) or index not in expected:
            raise KaliResultContractError("unexpected_index")
        if index in parsed:
            raise KaliResultContractError("duplicate_index")
        if not isinstance(item["ok"], bool) or not isinstance(item["confirmed"], bool):
            raise KaliResultContractError("invalid_result_type")
        returncode = item["returncode"]
        if returncode is not None and (
            not isinstance(returncode, int) or isinstance(returncode, bool)
        ):
            raise KaliResultContractError("invalid_result_type")
        parameter = item["parameter"]
        techniques = item["techniques"]
        dbms = item["dbms"]
        error_code = item["error_code"]
        if not isinstance(parameter, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{0,64}", parameter
        ):
            raise KaliResultContractError("unsafe_parameter")
        if not isinstance(techniques, list) or any(
            value not in SAFE_TECHNIQUES for value in techniques
        ):
            raise KaliResultContractError("invalid_techniques")
        if not isinstance(dbms, str) or not re.fullmatch(
            r"[A-Za-z0-9 ._-]{0,64}", dbms
        ):
            raise KaliResultContractError("unsafe_dbms")
        if not isinstance(error_code, str) or not re.fullmatch(
            r"[a-z0-9_]{0,64}", error_code
        ):
            raise KaliResultContractError("unsafe_error_code")
        parsed[index] = KaliResult(
            ok=item["ok"],
            returncode=returncode,
            confirmed=item["confirmed"],
            error=error_code,
            evidence_summary={
                "parameter": parameter,
                "techniques": techniques,
                "dbms": dbms,
            },
        )
    if set(parsed) != set(expected):
        raise KaliResultContractError("missing_index")
    return tuple(parsed[target.index] for target in expected_targets)
~~~

- [ ] **Step 4: Add exact settings with safe defaults**

~~~python
ARGUS_KALI_ENABLED = env_bool("ARGUS_KALI_ENABLED", default=False)
ARGUS_KALI_BACKEND = os.getenv("ARGUS_KALI_BACKEND", "disabled").strip().lower()
ARGUS_KALI_CONTAINER = os.getenv("ARGUS_KALI_CONTAINER", "argus-kali-1")
ARGUS_KALI_NAMESPACE = os.getenv("ARGUS_KALI_NAMESPACE", "argus-kali")
ARGUS_KALI_RUNNER_IMAGE = os.getenv("ARGUS_KALI_RUNNER_IMAGE", "").strip()
ARGUS_KALI_SQLMAP_VERSION = os.getenv("ARGUS_KALI_SQLMAP_VERSION", "1.10")
ARGUS_KALI_TIMEOUT = int(os.getenv("ARGUS_KALI_TIMEOUT", "120"))
ARGUS_KALI_STARTUP_GRACE_SECONDS = 30
ARGUS_KALI_MAX_TARGETS = 3
ARGUS_KALI_LOCK_WAIT_SECONDS = 420
ARGUS_KALI_LOCK_LEASE_SECONDS = 450
ARGUS_KALI_SCAN_DEADLINE_SECONDS = 900
ARGUS_KALI_STATE_TTL_SECONDS = 86400
ARGUS_KALI_TTL_AFTER_FINISHED_SECONDS = 300
ARGUS_KALI_RESULT_MAX_BYTES = 16384
ARGUS_KALI_REDIS_URL = os.getenv(
    "ARGUS_KALI_REDIS_URL",
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
~~~

Do not fail Django settings import for an invalid backend or missing runner image. The facade returns backend_misconfigured when Kali is enabled with disabled/unknown backend, or kubernetes lacks a repository@sha256 runner image. This preserves the structured silent-fail contract.

- [ ] **Step 5: Run focused tests and lint**

Run:

~~~powershell
uv run python backend/manage.py test apps.scans.tests_kali_contracts -v 2
uv run ruff check backend/apps/scans/security/kali_contracts.py backend/apps/scans/tests_kali_contracts.py backend/config/settings.py
~~~

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 6: Commit Task 1**

~~~powershell
git add backend/apps/scans/security/kali_contracts.py backend/apps/scans/tests_kali_contracts.py backend/config/settings.py .env.example
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "feat(kali): add safe execution contracts" -m "Define additive SQLmap result parsing, query-value redaction, and disabled-by-default runtime limits."
~~~

Expected: one commit containing only the four listed files.

---

### Task 2: Atomic authorization, deadline, dedupe and target budget

**Files:**
- Create: backend/apps/scans/security/kali_policy.py
- Create: backend/apps/scans/tests_kali_policy.py
- Create: backend/apps/scans/tests_kali_policy_redis.py
- Modify: .github/workflows/quality.yml:10-37

**Interfaces:**
- Consumes: ReservedSqlmapTarget, ReservationOutcome, ScanCancelled, assert_public_http_url(), get_origin().
- Produces: reserve_sqlmap_targets(scan_job_id, candidate_urls, max_count) and get_kali_redis().

- [ ] **Step 1: Write policy matrix tests**

~~~python
@override_settings(
    ARGUS_KALI_ENABLED=True,
    ARGUS_KALI_BACKEND="kubernetes",
    ARGUS_KALI_MAX_TARGETS=3,
)
class KaliPolicyTests(TestCase):
    def test_rejects_cross_origin_private_and_queryless_targets(self):
        scan = make_active_authorized_scan(origin="https://example.com")
        for target, reason in (
            ("https://other.example/?id=1", "cross_origin_forbidden"),
            ("https://127.0.0.1/?id=1", "target_not_public"),
            ("https://example.com/products", "no_query_parameter"),
        ):
            with self.subTest(target=target):
                outcome = reserve_sqlmap_targets(scan.id, [target], max_count=1)
                self.assertEqual(outcome.blocked_reason, reason)

    def test_cancel_is_propagated_before_redis_reservation(self):
        scan = make_active_authorized_scan()
        ScanJob.objects.filter(pk=scan.pk).update(status=ScanJob.Status.CANCELLED)
        with self.assertRaises(ScanCancelled):
            reserve_sqlmap_targets(scan.id, ["https://example.com/?id=1"], max_count=1)
~~~

Mock DNS resolution for example.com to a global documentation-safe test address in unit tests. Do not perform external DNS.

- [ ] **Step 2: Verify unit tests fail**

Run: uv run python backend/manage.py test apps.scans.tests_kali_policy -v 2

Expected: FAIL because reserve_sqlmap_targets is absent.

- [ ] **Step 3: Implement pre-Redis validation**

Validation order must be deterministic:

1. ARGUS_KALI_ENABLED, backend enum, ScanJob existence and cancellation.
2. active mode and active_testing_authorized.
3. assert_public_http_url().
4. exact get_origin(normalized) equality with scan.origin.
5. parse_qsl(..., keep_blank_values=True) contains at least one pair.
6. stable SHA-256 of normalized URL; Redis sees only the fingerprint.

Return the approved error strings from the spec; re-raise ScanCancelled unchanged. Do not log raw URLs.

- [ ] **Step 4: Implement the atomic Lua reservation**

Use Redis server TIME and exactly two keys: argus:kali:scan:{id}:targets and argus:kali:scan:{id}:started. ARGV contains deadline seconds, max budget, TTL and fingerprints. The script must return admitted zero-based argument indices, or -1 for scan_deadline_exceeded.

~~~lua
local now = tonumber(redis.call("TIME")[1])
local started = redis.call("GET", KEYS[2])
if not started then
  redis.call("SET", KEYS[2], now, "EX", ARGV[3], "NX")
  started = now
end
if now - tonumber(started) >= tonumber(ARGV[1]) then
  return {-1}
end

local used = redis.call("SCARD", KEYS[1])
local admitted = {}
for index = 4, #ARGV do
  if used >= tonumber(ARGV[2]) then break end
  if redis.call("SISMEMBER", KEYS[1], ARGV[index]) == 0 then
    redis.call("SADD", KEYS[1], ARGV[index])
    used = used + 1
    table.insert(admitted, index - 4)
  end
end
redis.call("EXPIRE", KEYS[1], ARGV[3])
redis.call("EXPIRE", KEYS[2], ARGV[3])
return admitted
~~~

Map an empty admitted list to target_already_tested if every candidate was already present; otherwise scan_budget_exhausted.

- [ ] **Step 5: Add a real Redis race test**

tests_kali_policy_redis.py must skip unless KALI_TEST_REDIS_URL is set, flush only its selected test DB, release two threads through one Barrier and assert exactly one reservation contains the shared fingerprint.

~~~python
@skipUnless(os.getenv("KALI_TEST_REDIS_URL"), "需要隔離 Redis test DB")
def test_two_workers_reserve_same_target_once(self):
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(self._reserve_after_barrier, barrier)
            for _ in range(2)
        ]
    allowed = sum(bool(item.result().targets) for item in futures)
    self.assertEqual(allowed, 1)
~~~

- [ ] **Step 6: Add Redis 7 to the backend quality job**

The quality backend job gets a service named redis using redis:7.4.2-alpine and KALI_TEST_REDIS_URL=redis://localhost:6379/15. Keep Django cache and broker defaults unchanged.

- [ ] **Step 7: Run policy tests**

Run:

~~~powershell
uv run python backend/manage.py test apps.scans.tests_kali_policy -v 2
docker run --rm -d --name argus-kali-test-redis -p 6389:6379 redis:7.4.2-alpine
$env:KALI_TEST_REDIS_URL='redis://localhost:6389/15'
uv run python backend/manage.py test apps.scans.tests_kali_policy_redis -v 2
docker stop argus-kali-test-redis
uv run ruff check backend/apps/scans/security/kali_policy.py backend/apps/scans/tests_kali_policy.py backend/apps/scans/tests_kali_policy_redis.py
~~~

Expected: unit and real Redis tests PASS; the race test reports one admitted reservation.

- [ ] **Step 8: Commit Task 2**

~~~powershell
git add backend/apps/scans/security/kali_policy.py backend/apps/scans/tests_kali_policy.py backend/apps/scans/tests_kali_policy_redis.py .github/workflows/quality.yml
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "feat(kali): enforce atomic target budgets" -m "Share authorization, public-target validation, per-scan deadline, SHA-256 dedupe, and a three-target Redis budget."
~~~

---

### Task 3: Facade dispatch and sanitized Docker compatibility

**Files:**
- Modify: backend/apps/scans/security/kali_tools.py
- Modify: backend/apps/scans/tests_kali_tools.py
- Modify: docker-compose.attack.yml

**Interfaces:**
- Consumes: reserve_sqlmap_targets(), KaliResult, SqlmapExecution, SqlmapExecutor.
- Produces: run_sqlmap(), run_sqlmap_batch(), DockerSqlmapExecutor and backend dispatch.

- [ ] **Step 1: Rewrite tests around the additive public contract**

~~~python
def test_docker_sqlmap_returns_safe_summary_without_raw_stdout(self):
    raw = (
        "Parameter: id (GET)\n"
        "    Type: boolean-based blind\n"
        "Parameter 'id' is vulnerable\n"
        "back-end DBMS: MySQL"
    )
    with mock.patch.object(kali_tools, "_docker_exec", return_value=(0, raw, "")):
        result = kali_tools.run_sqlmap("https://target.local/?id=1", self.scan.id)
    self.assertTrue(result["confirmed"])
    self.assertEqual(result["stdout"], "")
    self.assertEqual(result["evidence_summary"]["parameter"], "id")
    self.assertNotIn("raw", json.dumps(result))

@override_settings(ARGUS_KALI_ENABLED=True, ARGUS_KALI_BACKEND="kubernetes")
def test_metasploit_is_not_started_on_kubernetes(self):
    result = kali_tools.run_metasploit("exploit/example", {}, self.scan.id)
    self.assertEqual(result["blocked_reason"], "tool_not_supported_by_backend")
~~~

- [ ] **Step 2: Verify focused failures**

Run: uv run python backend/manage.py test apps.scans.tests_kali_tools -v 2

Expected: existing stdout assertions and new backend tests FAIL.

- [ ] **Step 3: Implement DockerSqlmapExecutor**

~~~python
class DockerSqlmapExecutor:
    def execute(self, scan_job_id, targets):
        return tuple(self._execute_one(scan_job_id, target) for target in targets)


def _executor_for_backend() -> SqlmapExecutor | None:
    backend = settings.ARGUS_KALI_BACKEND
    if backend == "docker":
        return DockerSqlmapExecutor()
    if backend == "kubernetes":
        from .kali_kubernetes import KubernetesSqlmapExecutor
        return KubernetesSqlmapExecutor()
    return None
~~~

The Docker executor may parse raw stdout only in process. It returns stdout="" and evidence_summary limited to parameter, techniques, dbms and settings.ARGUS_KALI_SQLMAP_VERSION. A target failure becomes one KaliResult and does not abort the batch.

- [ ] **Step 4: Implement facade reservation and batch behavior**

run_sqlmap reserves max_count=1. run_sqlmap_batch reserves max_count=min(max_targets, 3), executes every admitted target once and requires the executor result count to equal the target count. A count mismatch returns runner_failed for every admitted target.

validate_findings_with_kali calls run_sqlmap_batch once, trusts result.confirmed, redacts query values in description and serializes only evidence_summary into Finding evidence. It re-raises ScanCancelled before the silent-fail branch.

- [ ] **Step 5: Preserve Compose demo explicitly**

~~~yaml
ARGUS_KALI_ENABLED: "true"
ARGUS_KALI_BACKEND: "docker"
ARGUS_KALI_CONTAINER: "argus-kali-1"
~~~

Keep the Docker socket mount only in docker-compose.attack.yml.

- [ ] **Step 6: Run regressions**

~~~powershell
uv run python backend/manage.py test apps.scans.tests_kali_contracts apps.scans.tests_kali_policy apps.scans.tests_kali_tools -v 2
uv run ruff check backend/apps/scans/security/kali_tools.py backend/apps/scans/tests_kali_tools.py
docker compose -f docker-compose.yml -f docker-compose.attack.yml config
~~~

Expected: tests PASS; Compose config enables backend=docker only in the attack override.

- [ ] **Step 7: Commit Task 3**

~~~powershell
git add backend/apps/scans/security/kali_tools.py backend/apps/scans/tests_kali_tools.py docker-compose.attack.yml
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "refactor(kali): dispatch safe SQLmap executors" -m "Keep the isolated Docker demo while moving callers to budgeted, redacted, backend-neutral results."
~~~

---

### Task 4: Kubernetes Job executor and cancellation-safe lifecycle

**Files:**
- Create: backend/apps/scans/security/kali_kubernetes.py
- Create: backend/apps/scans/tests_kali_kubernetes.py
- Modify: pyproject.toml
- Modify: uv.lock

**Interfaces:**
- Consumes: ReservedSqlmapTarget, KaliResult, parse_runner_result(), get_kali_redis(), ScanCancelled.
- Produces: KubernetesSqlmapExecutor.execute(scan_job_id, targets).

- [ ] **Step 1: Add the API client through uv**

Run: uv add "kubernetes>=35.0,<36"

Expected: pyproject.toml and uv.lock change; no global pip package is installed.

- [ ] **Step 2: Write mocked lifecycle tests**

~~~python
def test_job_is_created_before_owned_secret_and_cleanup_is_finally(self):
    executor = self.make_executor()
    executor.execute(17, [self.target])
    self.assertLess(self.calls.index("create_job"), self.calls.index("create_secret"))
    self.assertIn("delete_job", self.calls)
    self.assertIn("delete_secret", self.calls)

def test_cancel_deletes_resources_and_propagates(self):
    self.cancel_check.side_effect = [None, ScanCancelled()]
    with self.assertRaises(ScanCancelled):
        self.make_executor().execute(17, [self.target])
    self.batch.delete_namespaced_job.assert_called()
    self.core.delete_namespaced_secret.assert_called()
~~~

Also cover capacity_timeout, owner-only renewal/release, stale Job cleanup, Secret create failure, Failed condition, watch timeout, invalid log, cleanup NotFound and cleanup_failed without API exception bodies.

- [ ] **Step 3: Verify tests fail**

Run: uv run python backend/manage.py test apps.scans.tests_kali_kubernetes -v 2

Expected: FAIL because KubernetesSqlmapExecutor is absent.

- [ ] **Step 4: Implement injectable clients**

~~~python
class KubernetesSqlmapExecutor:
    def __init__(
        self,
        *,
        batch_api=None,
        core_api=None,
        redis_client=None,
        watch_factory=watch.Watch,
        cancel_check=raise_if_cancelled,
        monotonic=time.monotonic,
    ):
        if batch_api is None or core_api is None:
            config.load_incluster_config()
        self.batch = batch_api or client.BatchV1Api()
        self.core = core_api or client.CoreV1Api()
        self.redis = redis_client or get_kali_redis()
        self.watch_factory = watch_factory
        self.cancel_check = cancel_check
        self.monotonic = monotonic
~~~

Production code has no automatic local kubeconfig fallback; integration tests inject configured clients.

- [ ] **Step 5: Implement global lock ownership**

Acquire argus:kali:global-lock with SET NX PX 450000, poll at most 420 seconds and call cancel_check each second. Renew every 60 seconds with compare-and-PEXPIRE Lua. Release with compare-and-DEL Lua. A mismatched token cannot renew or delete the lock.

- [ ] **Step 6: Implement Job-first / Secret-second lifecycle**

Names use HMAC-SHA256(settings.SECRET_KEY, "kali:{scan_id}")[:10] plus secrets.token_hex(6). Labels contain managed-by=argus and component=kali-sqlmap, never URL/domain.

~~~python
deadline = min(len(targets) * settings.ARGUS_KALI_TIMEOUT + 30, 390)
job = client.V1Job(
    metadata=client.V1ObjectMeta(name=job_name, namespace=namespace, labels=labels),
    spec=client.V1JobSpec(
        parallelism=1,
        completions=1,
        backoff_limit=0,
        ttl_seconds_after_finished=300,
        active_deadline_seconds=deadline,
        template=build_restricted_runner_pod(secret_name, labels),
    ),
)
~~~

Create the Job first. After its UID returns, create one owner-referenced Secret containing only targets.json in string_data. Never read or list Secret.

- [ ] **Step 7: Implement bounded watch and cleanup**

The overall watch limit is min(active deadline + 30, 420). append_log records only the correlation ID, lifecycle phase and safe error code.

Watch in at most five-second slices, check cancellation between slices, locate the one Job Pod, read pods/log with limit_bytes=16385, reject oversized output through parse_runner_result(), and add trusted correlation_id/tool_version to evidence_summary. In finally, foreground-delete Job and delete Secret; NotFound is success.

Before a new Job, list only managed-by=argus,component=kali-sqlmap and delete entries older than activeDeadlineSeconds plus 30.

- [ ] **Step 8: Run executor tests**

~~~powershell
uv run python backend/manage.py test apps.scans.tests_kali_kubernetes -v 2
uv run ruff check backend/apps/scans/security/kali_kubernetes.py backend/apps/scans/tests_kali_kubernetes.py
uv lock --check
~~~

Expected: lifecycle/cancellation tests PASS, Ruff and lock check exit 0.

- [ ] **Step 9: Commit Task 4**

~~~powershell
git add backend/apps/scans/security/kali_kubernetes.py backend/apps/scans/tests_kali_kubernetes.py pyproject.toml uv.lock
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "feat(kali): execute SQLmap in restricted Kubernetes jobs" -m "Add client 35.x, owned short-lived Secrets, bounded watches, single-owner Redis locks, cancellation, and cleanup."
~~~

---

### Task 5: Dedicated pinned SQLmap runner image

**Files:**
- Create: kali-runner/Dockerfile
- Create: kali-runner/runner.py
- Create: kali-runner/tests/test_runner.py
- Create: kali-runner/README.md

**Interfaces:**
- Consumes: /run/argus-targets/targets.json schema_version 1.
- Produces: one UTF-8 JSON document, maximum 16384 bytes, with exact schema_version/tool/results fields.

Input is exactly:

~~~json
{"schema_version":1,"scan_id":123,"targets":[{"index":0,"url":"https://authorized.example/path?parameter=value"}]}
~~~

- [ ] **Step 1: Write runner unit tests**

~~~python
def test_never_prints_raw_stdout_or_target_url(self):
    completed = subprocess.CompletedProcess(
        args=["sqlmap"],
        returncode=0,
        stdout=(
            "Parameter: id (GET)\n"
            "    Type: boolean-based blind\n"
            "Parameter 'id' is vulnerable\n"
            "back-end DBMS: MySQL\n"
            "secret-row-value"
        ),
        stderr="",
    )
    with mock.patch.object(runner.subprocess, "run", return_value=completed):
        result = runner.run_target(0, "https://fixture.test/?id=secret")
    encoded = json.dumps(result)
    self.assertTrue(result["confirmed"])
    self.assertNotIn("secret", encoded)
    self.assertNotIn("fixture.test", encoded)
~~~

Also cover timeout, malformed input, more than 3 targets, duplicate indices, cross-origin batch, private DNS, queryless URL, nonzero return code, size guard and self-test.

- [ ] **Step 2: Verify tests fail**

Run: uv run python -m unittest discover -s kali-runner/tests -v

Expected: FAIL because runner.py is absent.

- [ ] **Step 3: Implement the wrapper**

~~~python
def command_for(index: int, target_url: str) -> list[str]:
    return [
        sys.executable, "/opt/sqlmap/sqlmap.py", "-u", target_url,
        "--batch", "--flush-session", f"--output-dir=/tmp/sqlmap-{index}",
        "--disable-coloring", "--level=1", "--risk=1", "--threads=1",
        "--timeout=10", "--retries=1",
        "--user-agent=SiteSense-AI-Scanner/1.0 (authorized-audit)",
    ]
~~~

Validate public HTTP(S), ports 80/443, no userinfo, all DNS results global, query present and one shared origin. Capture stdout/stderr without echo. Parameter is [A-Za-z0-9_.-]{0,64}; techniques use a finite six-name whitelist; DBMS is safe text up to 64 characters.

main() serializes compact UTF-8. If over 16384 bytes, replace every item with runner_output_too_large. --self-test prints {"schema_version":1,"tool":"sqlmap","results":[]} without reading Secret or starting sqlmap.

- [ ] **Step 4: Create the pinned image**

~~~dockerfile
FROM python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49

ARG SQLMAP_COMMIT=ea8c6bdb63a3b2da1584f328836eb0d28116f7c4
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ADD https://github.com/sqlmapproject/sqlmap/archive/ea8c6bdb63a3b2da1584f328836eb0d28116f7c4.tar.gz /tmp/sqlmap.tar.gz
RUN mkdir -p /opt/sqlmap \
    && tar -xzf /tmp/sqlmap.tar.gz --strip-components=1 -C /opt/sqlmap \
    && rm /tmp/sqlmap.tar.gz \
    && case "$(/usr/local/bin/python /opt/sqlmap/sqlmap.py --version)" in 1.10*) true ;; *) false ;; esac
COPY --chown=65532:65532 runner.py /opt/argus/runner.py
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/python", "/opt/argus/runner.py"]
~~~

Do not install Metasploit, Nmap, kubectl, Docker CLI or application dependencies.

- [ ] **Step 5: Run image tests**

~~~powershell
uv run python -m unittest discover -s kali-runner/tests -v
docker build -t argus-kali-runner:test kali-runner
docker run --rm --read-only --user 65532:65532 --tmpfs /tmp:rw,nosuid,nodev,size=1g argus-kali-runner:test --self-test
docker run --rm --read-only --user 65532:65532 --tmpfs /tmp:rw,nosuid,nodev,size=1g --entrypoint /usr/local/bin/python argus-kali-runner:test /opt/sqlmap/sqlmap.py --version
~~~

Expected: tests PASS; self-test exact; version begins with 1.10 and may include the stable suffix.

- [ ] **Step 6: Commit Task 5**

~~~powershell
git add kali-runner/Dockerfile kali-runner/runner.py kali-runner/tests/test_runner.py kali-runner/README.md
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "feat(kali): add pinned SQLmap runner image" -m "Build SQLmap 1.10 from an immutable commit and emit only bounded, schema-validated summaries as a non-root user."
~~~

---

### Task 6: AI-first tool exposure, fallback order and scoring

**Files:**
- Modify: backend/apps/agent/tools.py:26-151,319-391
- Modify: backend/apps/agent/loop.py:33,59-82,192-199,218-234
- Modify: backend/apps/agent/runner.py:110-171
- Modify: backend/apps/agent/tests.py:235-401
- Modify: backend/apps/scans/tasks.py:280-305,389-432
- Create: backend/apps/scans/tests_kali_pipeline.py

**Interfaces:**
- Consumes: run_sqlmap(), validate_findings_with_kali(), redact_url_query_values(), AgentRunResult.security_findings.
- Produces: build_tool_schemas(allow_sqlmap), redacted AgentStep payloads and AI-first ordering.

- [ ] **Step 1: Add failing schema and redaction tests**

~~~python
def test_passive_schema_omits_sqlmap_tool(self):
    names = {item["function"]["name"] for item in build_tool_schemas(False)}
    self.assertNotIn("probe_sql_injection", names)

def test_authorized_active_schema_includes_sqlmap_tool(self):
    names = {item["function"]["name"] for item in build_tool_schemas(True)}
    self.assertIn("probe_sql_injection", names)

def test_probe_arguments_redact_query_values(self):
    clean = redact_tool_arguments(
        "probe_sql_injection",
        {"url": "https://example.com/search?q=secret&id=42"},
    )
    encoded = json.dumps(clean)
    self.assertIn("%5BREDACTED%5D", encoded)
    self.assertNotIn("secret", encoded)
~~~

- [ ] **Step 2: Add a failing pipeline regression**

Patch run_agent_for_scan, validate_findings_with_kali and calculate_scores around one active authorized ScanJob. Assert agent precedes fallback, agent_result.security_findings reaches calculate_scores, fallback still runs when Agent is disabled/fails, and ScanCancelled reaches the existing cancelled/refund branch. Reuse task dependency mocking from tests_cancel.py; no external scanner runs.

- [ ] **Step 3: Verify failures**

Run: uv run python backend/manage.py test apps.agent apps.scans.tests_kali_pipeline -v 2

Expected: schema omission, redaction, ordering and scoring assertions FAIL.

- [ ] **Step 4: Build tool schemas per run**

~~~python
def build_tool_schemas(allow_sqlmap: bool) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(schema)
        for schema in TOOL_SCHEMAS
        if allow_sqlmap or schema["function"]["name"] != "probe_sql_injection"
    ]
~~~

HermesAgent.__init__ accepts tool_schemas and _call_provider passes self.tool_schemas, never TOOL_SCHEMAS. run_agent_for_scan passes build_tool_schemas(deep_mode). ProviderChain's existing non-empty-tool rule keeps non-tool providers out.

- [ ] **Step 5: Redact persisted tool data**

loop._save_step calls redact_tool_arguments(tool_name, arguments) and redact_tool_result(tool_name, outcome.result). For probe_sql_injection, URL values use redact_url_query_values(); results contain confirmed, blocked/error and trusted correlation_id only. Remove target URL from tool result.

- [ ] **Step 6: Trust confirmed rather than stdout**

~~~python
res = await asyncio.to_thread(run_sqlmap, url, self.scan_job.id)
if res.get("blocked_reason"):
    return ToolOutcome(
        ok=False,
        result={"confirmed": False, "blocked": res["blocked_reason"]},
    )
if not res.get("confirmed"):
    return ToolOutcome(
        ok=True,
        result={"confirmed": False, "error": res.get("error", "")},
    )
~~~

The Finding description contains the redacted URL; evidence is json.dumps(evidence_summary, sort_keys=True); no stdout is stored.

- [ ] **Step 7: Move fallback after Hermes and before scoring**

Delete the old Kali block after Nuclei. After agent completion:

~~~python
if agent_result:
    all_findings.extend(agent_result.security_findings)

if deep_mode:
    raise_if_cancelled(scan_job_id)
    kali_findings = validate_findings_with_kali(scan_job_id, crawled_urls)
    for finding in kali_findings:
        Finding.objects.create(scan_job=scan_job, page=None, **finding)
    all_findings.extend(kali_findings)
~~~

Catch non-cancellation infrastructure failures only. Redis fingerprints make fallback consume remaining unique targets in one batch.

- [ ] **Step 8: Run regressions**

~~~powershell
uv run python backend/manage.py test apps.agent apps.scans.tests_kali_tools apps.scans.tests_kali_pipeline apps.scans.tests_cancel -v 2
uv run ruff check backend/apps/agent backend/apps/scans/tasks.py backend/apps/scans/tests_kali_pipeline.py
~~~

Expected: passive schema has no probe; AI precedes fallback; confirmed security Finding affects score; cancellation/refund tests PASS.

- [ ] **Step 9: Commit Task 6**

~~~powershell
git add backend/apps/agent/tools.py backend/apps/agent/loop.py backend/apps/agent/runner.py backend/apps/agent/tests.py backend/apps/scans/tasks.py backend/apps/scans/tests_kali_pipeline.py
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "feat(agent): prioritize budgeted SQLmap decisions" -m "Hide the attack tool outside authorized active scans, redact AgentStep data, run Hermes before fallback, and score confirmed findings."
~~~

---

### Task 7: Namespace isolation, RBAC, admission and NetworkPolicy

**Files:**
- Create: k8s/10-kali-runtime.yaml
- Create: k8s/11-kali-admission.yaml
- Create: tests/test_kali_k8s_contract.py
- Modify: k8s/01-namespace-config.yaml
- Modify: k8s/04-backend.yaml:118-164
- Modify: k8s/07-network-policies.yaml:133-217
- Modify: k8s/kustomization.yaml
- Modify: backend/apps/scans/tests_k8s_network_policy.py
- Modify: .github/workflows/quality.yml:70-93

**Interfaces:**
- Consumes: KubernetesSqlmapExecutor Job shape and approved runner digest.
- Produces: argus-worker-kali-orchestrator identity and the only admitted Job shape in argus-kali.

- [ ] **Step 1: Write failing manifest contracts**

Parse rendered YAML and assert restricted:v1.35 namespace labels; worker SA; exact Role verbs; tokenless runner SA; one Pod/Job quota; resource/limit values; DNS/public 80/443 only; exact API /32 rules; fail-closed VAP binding; no host access, privilege or app Secret.

- [ ] **Step 2: Verify contracts fail**

Run: uv run python -m unittest discover -s tests -p "test_kali_k8s_contract.py" -v

Expected: FAIL because the two manifests are absent.

- [ ] **Step 3: Add namespace, identities, quota and Role**

Use resource names argus-kali, argus-worker-kali-orchestrator, kali-runner, argus-kali-orchestrator, argus-kali-orchestrator-binding, argus-kali-single-runner and argus-kali-runner-limits.

~~~yaml
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["create", "get", "list", "watch", "delete"]
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["create", "delete"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
~~~

RoleBinding references ServiceAccount argus-worker-kali-orchestrator in namespace argus. The runner SA has no RoleBinding and automountServiceAccountToken=false.

- [ ] **Step 4: Add exact resource boundaries**

~~~yaml
hard:
  pods: "1"
  count/jobs.batch: "1"
  requests.cpu: "250m"
  requests.memory: "256Mi"
  requests.ephemeral-storage: "256Mi"
  limits.cpu: "1"
  limits.memory: "768Mi"
  limits.ephemeral-storage: "1Gi"
~~~

Admitted Pods use UID/GID/fsGroup 65532, RuntimeDefault, read-only root, no privilege escalation, drop ALL, one read-only Secret and emptyDir sizeLimit=1Gi at /tmp.

- [ ] **Step 5: Add NetworkPolicy**

Create argus-kali-default-deny and argus-kali-runner-egress. Runner egress is CoreDNS plus existing IPv4/IPv6 public exclusions on TCP 80/443 only.

Append exact worker API rules:

~~~yaml
- to:
    - ipBlock:
        cidr: 10.96.0.1/32
  ports:
    - protocol: TCP
      port: 443
- to:
    - ipBlock:
        cidr: 172.16.2.122/32
  ports:
    - protocol: TCP
      port: 6443
~~~

- [ ] **Step 6: Add the fail-closed admission policy**

Initial disabled sentinel:

~~~text
shijie85/argus-kali-runner@sha256:0000000000000000000000000000000000000000000000000000000000000000
~~~

~~~yaml
failurePolicy: Fail
matchConstraints:
  resourceRules:
    - apiGroups: ["batch"]
      apiVersions: ["v1"]
      operations: ["CREATE", "UPDATE"]
      resources: ["jobs"]
variables:
  - name: approvedImage
    expression: "'shijie85/argus-kali-runner@sha256:0000000000000000000000000000000000000000000000000000000000000000'"
validations:
  - expression: "object.spec.parallelism == 1 && object.spec.completions == 1 && object.spec.backoffLimit == 0"
  - expression: "object.spec.ttlSecondsAfterFinished == 300 && object.spec.activeDeadlineSeconds >= 150 && object.spec.activeDeadlineSeconds <= 390"
  - expression: "object.spec.template.spec.serviceAccountName == 'kali-runner' && object.spec.template.spec.automountServiceAccountToken == false"
  - expression: "object.spec.template.spec.containers.size() == 1 && object.spec.template.spec.containers[0].image == variables.approvedImage"
  - expression: "object.spec.template.spec.containers[0].command == ['/usr/local/bin/python'] && object.spec.template.spec.containers[0].args == ['/opt/argus/runner.py']"
~~~

Add explicit CEL for exact two volumes/mounts/resources/security contexts/restartPolicy and absence of hostNetwork, hostPID, hostIPC, hostPath, hostPort and privileged. Binding actions=[Deny] and namespaceSelector matches argus.io/kali-runner=true.

Use these concrete validations:

~~~yaml
  - expression: "object.metadata.name.matches('^argus-sqlmap-[a-f0-9]{10}-[a-f0-9]{12}$')"
    message: "Argus Kali Job 名稱不符合契約"
  - expression: "object.spec.template.spec.restartPolicy == 'Never' && (!has(object.spec.template.spec.hostNetwork) || object.spec.template.spec.hostNetwork == false) && (!has(object.spec.template.spec.hostPID) || object.spec.template.spec.hostPID == false) && (!has(object.spec.template.spec.hostIPC) || object.spec.template.spec.hostIPC == false)"
    message: "Argus Kali Pod 不得使用 host namespace"
  - expression: "object.spec.template.spec.volumes.size() == 2 && object.spec.template.spec.volumes.exists(v, v.name == 'targets' && has(v.secret) && v.secret.secretName.matches('^argus-targets-[a-f0-9]{10}-[a-f0-9]{12}$') && v.secret.defaultMode == 256) && object.spec.template.spec.volumes.exists(v, v.name == 'scratch' && has(v.emptyDir) && v.emptyDir.sizeLimit == quantity('1Gi')) && object.spec.template.spec.volumes.all(v, !has(v.hostPath))"
    message: "Argus Kali volume 不符合契約"
  - expression: "object.spec.template.spec.securityContext.runAsNonRoot == true && object.spec.template.spec.securityContext.runAsUser == 65532 && object.spec.template.spec.securityContext.runAsGroup == 65532 && object.spec.template.spec.securityContext.fsGroup == 65532 && object.spec.template.spec.securityContext.seccompProfile.type == 'RuntimeDefault'"
    message: "Argus Kali Pod securityContext 不符合契約"
  - expression: "object.spec.template.spec.containers[0].securityContext.runAsNonRoot == true && object.spec.template.spec.containers[0].securityContext.readOnlyRootFilesystem == true && object.spec.template.spec.containers[0].securityContext.allowPrivilegeEscalation == false && object.spec.template.spec.containers[0].securityContext.capabilities.drop == ['ALL'] && (!has(object.spec.template.spec.containers[0].securityContext.privileged) || object.spec.template.spec.containers[0].securityContext.privileged == false)"
    message: "Argus Kali container securityContext 不符合契約"
  - expression: "object.spec.template.spec.containers[0].volumeMounts.size() == 2 && object.spec.template.spec.containers[0].volumeMounts.exists(v, v.name == 'targets' && v.mountPath == '/run/argus-targets' && v.readOnly == true) && object.spec.template.spec.containers[0].volumeMounts.exists(v, v.name == 'scratch' && v.mountPath == '/tmp')"
    message: "Argus Kali volumeMount 不符合契約"
  - expression: "object.spec.template.spec.containers[0].resources.requests['cpu'] == quantity('250m') && object.spec.template.spec.containers[0].resources.requests['memory'] == quantity('256Mi') && object.spec.template.spec.containers[0].resources.requests['ephemeral-storage'] == quantity('256Mi') && object.spec.template.spec.containers[0].resources.limits['cpu'] == quantity('1') && object.spec.template.spec.containers[0].resources.limits['memory'] == quantity('768Mi') && object.spec.template.spec.containers[0].resources.limits['ephemeral-storage'] == quantity('1Gi')"
    message: "Argus Kali resources 不符合契約"
  - expression: "(!has(object.spec.template.spec.containers[0].ports) || object.spec.template.spec.containers[0].ports.size() == 0) && (!has(object.spec.template.spec.containers[0].env) || object.spec.template.spec.containers[0].env.size() == 0) && (!has(object.spec.template.spec.containers[0].envFrom) || object.spec.template.spec.containers[0].envFrom.size() == 0)"
    message: "Argus Kali runner 不得取得 host port 或 application envFrom"
~~~

- [ ] **Step 7: Wire worker while disabled**

~~~yaml
ARGUS_KALI_ENABLED: "false"
ARGUS_KALI_BACKEND: "disabled"
ARGUS_KALI_NAMESPACE: "argus-kali"
ARGUS_KALI_RUNNER_IMAGE: "shijie85/argus-kali-runner@sha256:0000000000000000000000000000000000000000000000000000000000000000"
~~~

Set worker serviceAccountName=argus-worker-kali-orchestrator and add both manifests to Kustomize. Do not modify Secret.

- [ ] **Step 8: Run render and server dry-run**

~~~powershell
uv run python -m unittest discover -s tests -p "test_kali_k8s_contract.py" -v
uv run python backend/manage.py test apps.scans.tests_k8s_network_policy -v 2
kubectl kustomize k8s
kubectl kustomize k8s | kubectl apply --dry-run=server -f -
~~~

Expected: PASS. If Argo project forbids cluster-scoped resources, stop for a separately reviewed cluster-admin change.

- [ ] **Step 9: Verify RBAC**

~~~powershell
kubectl auth can-i --as=system:serviceaccount:argus:argus-worker-kali-orchestrator create jobs.batch -n argus-kali
kubectl auth can-i --as=system:serviceaccount:argus:argus-worker-kali-orchestrator get pods/log -n argus-kali
kubectl auth can-i --as=system:serviceaccount:argus:argus-worker-kali-orchestrator create secrets -n argus-kali
kubectl auth can-i --as=system:serviceaccount:argus:argus-worker-kali-orchestrator get secrets -n argus-kali
kubectl auth can-i --as=system:serviceaccount:argus:argus-worker-kali-orchestrator create pods -n argus-kali
kubectl auth can-i --as=system:serviceaccount:argus:argus-worker-kali-orchestrator create deployments.apps -n argus-kali
kubectl auth can-i --as=system:serviceaccount:argus:argus-worker-kali-orchestrator get configmaps -n argus-kali
~~~

Expected: yes, yes, yes, no, no, no, no.

- [ ] **Step 10: Commit Task 7**

~~~powershell
git add k8s/10-kali-runtime.yaml k8s/11-kali-admission.yaml tests/test_kali_k8s_contract.py k8s/01-namespace-config.yaml k8s/04-backend.yaml k8s/07-network-policies.yaml k8s/kustomization.yaml backend/apps/scans/tests_k8s_network_policy.py .github/workflows/quality.yml
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "feat(k8s): isolate and admit SQLmap jobs" -m "Add restricted namespace resources, least-privilege RBAC, single-runner quota, exact API egress, and fail-closed admission while Kali remains disabled."
~~~

---

### Task 8: Immutable image promotion and CI write-back

**Files:**
- Create: scripts/promote_kali_image.py
- Create: tests/test_kali_image_promotion.py
- Create: .github/workflows/build-kali-runner.yml
- Modify: .github/workflows/quality.yml

**Interfaces:**
- Consumes: Docker build digest sha256:<64 lowercase hex>.
- Produces: the same repository@digest in argus-config and VAP approvedImage.

- [ ] **Step 1: Write failing promotion tests**

~~~python
def test_updates_config_and_policy_to_the_same_digest(self):
    image = "shijie85/argus-kali-runner@sha256:" + "a" * 64
    changed = promote_kali_image.update_repository(self.root, image)
    self.assertTrue(changed)
    self.assertEqual(promote_kali_image.read_config_image(self.root), image)
    self.assertEqual(promote_kali_image.read_policy_image(self.root), image)

def test_rejects_tags(self):
    with self.assertRaises(ValueError):
        promote_kali_image.update_repository(
            self.root, "shijie85/argus-kali-runner:latest"
        )
~~~

- [ ] **Step 2: Implement deterministic promotion**

~~~python
IMAGE_RE = re.compile(
    r"^shijie85/argus-kali-runner@sha256:[0-9a-f]{64}$"
)
~~~

update_repository(root, image) replaces exactly one ARGUS_KALI_RUNNER_IMAGE value in 01-namespace-config.yaml and exactly one approvedImage CEL string in 11-kali-admission.yaml. Zero/multiple matches raise ValueError. check_repository(root) exits nonzero when values differ.

- [ ] **Step 3: Verify promotion**

~~~powershell
uv run python -m unittest discover -s tests -p "test_kali_image_promotion.py" -v
uv run python scripts/promote_kali_image.py --check
uv run ruff check scripts/promote_kali_image.py tests/test_kali_image_promotion.py
~~~

Expected: PASS and both disabled sentinel values match.

- [ ] **Step 4: Add runner build workflow**

Trigger on main changes to kali-runner/**, this workflow, promotion script/test and workflow_dispatch. Share concurrency group argus-gitops-cd.

~~~yaml
- name: Build and push immutable runner
  id: build
  uses: docker/build-push-action@v6
  with:
    context: ./kali-runner
    file: ./kali-runner/Dockerfile
    platforms: linux/amd64
    push: true
    tags: |
      ${{ vars.DOCKERHUB_USERNAME }}/argus-kali-runner:sha-${{ github.sha }}
    cache-from: type=gha
    cache-to: type=gha,mode=max
~~~

Before push, run runner unit tests, read-only self-test and sqlmap version. After push:

~~~yaml
- name: Promote digest into GitOps contracts
  env:
    IMAGE_DIGEST: ${{ steps.build.outputs.digest }}
  run: |
    set -euo pipefail
    IMAGE="${{ vars.DOCKERHUB_USERNAME }}/argus-kali-runner@${IMAGE_DIGEST}"
    uv run python scripts/promote_kali_image.py --image "${IMAGE}"
    uv run python scripts/promote_kali_image.py --check
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git fetch origin main
    git rebase origin/main
    git add k8s/01-namespace-config.yaml k8s/11-kali-admission.yaml
    git diff --cached --quiet && exit 0
    git commit -m "ci(cd): promote argus-kali-runner digest"
    git push origin HEAD:main
~~~

Reject Docker Hub username other than shijie85 until a separate review migrates the admission repository.

- [ ] **Step 5: Add Quality Gate checks**

Run promote_kali_image.py --check in backend and kubernetes-manifests jobs. Add runner unit tests to a dedicated runner job; ordinary Python contracts do not require Docker.

- [ ] **Step 6: Validate workflow and image**

~~~powershell
uv run python -m unittest discover -s tests -p "test_kali_image_promotion.py" -v
uv run python scripts/promote_kali_image.py --check
docker build -t argus-kali-runner:test kali-runner
docker run --rm --read-only --user 65532:65532 --tmpfs /tmp:rw,nosuid,nodev,size=1g argus-kali-runner:test --self-test
git diff --check
~~~

Expected: PASS; promotion check finds one matching digest per file.

- [ ] **Step 7: Commit Task 8**

~~~powershell
git add scripts/promote_kali_image.py tests/test_kali_image_promotion.py .github/workflows/build-kali-runner.yml .github/workflows/quality.yml
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "ci(kali): promote immutable runner digests" -m "Build and smoke-test the image, then atomically update worker configuration and the admission allowlist to one digest."
~~~

---

### Task 9: Isolated Calico integration attack chain

**Files:**
- Create: tests/integration/kind-config.yaml
- Create: tests/integration/kali-fixture/app.py
- Create: tests/integration/kali-fixture/Dockerfile
- Create: tests/integration/kali-fixture/fixture.yaml
- Create: tests/integration/kali-fixture/network-policy-patch.yaml
- Create: tests/integration/test_kali_job.py
- Create: .github/workflows/kali-integration.yml

**Interfaces:**
- Consumes: real Redis, kind Kubernetes, Calico, locally built runner digest and ToolExecutor.
- Produces: confirmed kali-sqlmap-sqli Finding, changed security score, single runner and clean namespace.

- [ ] **Step 1: Build a repo-owned vulnerable fixture**

app.py uses only http.server and sqlite3, listens on 0.0.0.0:8080 and deliberately interpolates q into:

~~~python
sql = f"SELECT id, name FROM products WHERE name LIKE '%{query}%'"
rows = connection.execute(sql).fetchall()
~~~

This file must begin with a warning that it is intentionally vulnerable, test-only and must never be deployed outside the ephemeral workflow. The Deployment has one replica, no public Ingress and a ClusterIP Service with externalIPs=[93.184.216.34], port 80 to targetPort 8080.

- [ ] **Step 2: Configure public-looking DNS without external traffic**

The workflow patches CoreDNS so fixture.argus.test resolves to 93.184.216.34, and appends the same mapping to the CI host /etc/hosts. kube-proxy externalIPs interception routes 93.184.216.34:80 to the fixture Service.

Before the attack test, run from a disposable Pod:

~~~bash
wget -qO- 'http://fixture.argus.test/?q=phone'
~~~

Expected: local fixture JSON. Then verify a different public IP is blocked by the test-only runner NetworkPolicy. If either assertion fails, stop; never let the test fall through to the Internet.

- [ ] **Step 3: Create a kind 1.35 cluster with Calico 3.32**

kind-config.yaml sets disableDefaultCNI: true and podSubnet: 192.168.0.0/16. The workflow installs the official v3.32.0 Calico manifest and waits for calico-node Ready before applying Argus resources.

Use a local registry, push the runner, obtain its sha256 digest, run promote_kali_image.py against the checkout without committing, then apply the minimal argus namespace/config, 10-kali-runtime, 11-kali-admission and fixture overlay.

- [ ] **Step 4: Write the real executor and Agent tool integration test**

~~~python
@override_settings(
    ARGUS_KALI_ENABLED=True,
    ARGUS_KALI_BACKEND="kubernetes",
    ARGUS_KALI_RUNNER_IMAGE=os.environ["KALI_INTEGRATION_IMAGE"],
    ARGUS_KALI_REDIS_URL=os.environ["KALI_TEST_REDIS_URL"],
)
def test_agent_tool_creates_real_job_finding_and_score(self):
    executor = ToolExecutor(
        page=self.page,
        screenshot_dir=self.tempdir,
        scan_job=self.scan,
    )
    real_executor = KubernetesSqlmapExecutor(
        batch_api=client.BatchV1Api(),
        core_api=client.CoreV1Api(),
        redis_client=self.redis,
    )
    with mock.patch(
        "apps.scans.security.kali_tools._executor_for_backend",
        return_value=real_executor,
    ):
        outcome = asyncio.run(
            executor.run(
                "probe_sql_injection",
                {"url": "http://fixture.argus.test/?q=phone"},
            )
        )
    self.assertTrue(outcome.result["confirmed"])
    created = persist_agent_security_findings(
        self.scan, [outcome.security_finding]
    )
    self.assertEqual(created[0].rule_id, "kali-sqlmap-sqli")
    overall, categories, _actions = calculate_scores([outcome.security_finding])
    self.assertLess(categories["security"], 100)
    self.assertLess(overall, 100)
~~~

Load kubeconfig explicitly in the test setup. Production executor code must still use in-cluster config by default.

- [ ] **Step 5: Add concurrency, cancellation and cleanup assertions**

Start two active ScanJobs in two threads, sample Pods with app=kali-sqlmap and assert maximum concurrent Running count is 1. Cancel one ScanJob after its Job appears and assert ScanCancelled, no Job/Secret remains and the existing cancellation/refund unit tests still pass.

After every test:

~~~bash
test "$(kubectl -n argus-kali get jobs -l argus.io/managed-by=argus --no-headers | wc -l)" -eq 0
test "$(kubectl -n argus-kali get secrets -l argus.io/managed-by=argus --no-headers | wc -l)" -eq 0
test "$(kubectl -n argus-kali get pods -l app=kali-sqlmap --no-headers | wc -l)" -eq 0
~~~

- [ ] **Step 6: Run the isolated workflow locally or in Actions**

Run: gh workflow run kali-integration.yml

Expected: fixture-only positive SQLi, one runner at a time, cancellation cleanup PASS. The workflow always deletes the kind cluster and local registry in its final cleanup step.

- [ ] **Step 7: Commit Task 9**

~~~powershell
git add tests/integration/kind-config.yaml tests/integration/kali-fixture/app.py tests/integration/kali-fixture/Dockerfile tests/integration/kali-fixture/fixture.yaml tests/integration/kali-fixture/network-policy-patch.yaml tests/integration/test_kali_job.py .github/workflows/kali-integration.yml
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "test(kali): exercise the isolated K8s attack chain" -m "Use a repo-owned vulnerable fixture, Calico boundaries, a real SQLmap Job, concurrent scans, cancellation, scoring, and zero-resource cleanup."
~~~

---

### Task 10: Documentation synchronization and disabled software release

**Files:**
- Create: docs/runbooks/kubernetes-secret-at-rest-encryption.md
- Create: docs/runbooks/kali-sqlmap-rollout.md
- Create: log/2026-07-14_k8s-kali-sqlmap-implementation.md
- Modify: CLAUDE.md
- Modify: ONBOARDING.md
- Modify: backend/apps/scans/CLAUDE.md
- Modify: backend/apps/scans/security/CLAUDE.md
- Modify: backend/apps/agent/CLAUDE.md
- Modify: k8s/README.md
- Modify: docs/capstone-roadmap.md

**Interfaces:**
- Consumes: verified source code, settings, manifests, workflows and live prerequisites.
- Produces: accurate operator handoff, encryption gate, rollback and backlog.

- [ ] **Step 1: Update subsystem truth from code**

Document:

- Kubernetes and Docker backends with defaults;
- AI-first order and schema omission;
- three-target Redis budget and one-runner quota;
- Secret/result redaction contract;
- cancellation propagation;
- exact RBAC and network boundaries;
- image digest promotion;
- disabled-until-encryption state.

Correct the scans CLAUDE cancellation wording to match the actual DB-status CancellationToken rather than claiming Redis cancellation flags.

- [ ] **Step 2: Update package/settings onboarding**

Because kubernetes 35.x is a new dependency and ARGUS_KALI_* settings changed, update the root technical stack and ONBOARDING installation／environment appendix in the same commit. Do not write any live Secret, key, SSH path or machine-specific value.

- [ ] **Step 3: Record the explicit backlog**

docs/capstone-roadmap.md gets separate unchecked future items for Metasploit runner, Nmap runner, controller service, multi-Job scheduler, async ScanJob continuation, SIEM/Prometheus alerts, automatic encryption-key rotation and Compose-only Docker CLI image split. None is presented as implemented.

- [ ] **Step 4: Write the two operator runbooks**

kubernetes-secret-at-rest-encryption.md includes backup, key custody, apiserver manifest, sentinel raw-etcd verification, Secret rewrite, health checks and recovery. kali-sqlmap-rollout.md includes digest promotion, server dry-run, RBAC/admission/network checks, disabled smoke, enablement, positive test authorization and rollback.

Both runbooks start with a warning that cluster-admin commands require a maintenance window and fresh backup.

- [ ] **Step 5: Run the full verification suite**

Run:

~~~powershell
$env:DJANGO_SECRET_KEY='ci-only-django-secret-key-at-least-32-bytes'
$env:JWT_SECRET_KEY='ci-only-jwt-secret-key-at-least-32-bytes'
$env:PASSWORD_RESET_TOKEN_PEPPER='ci-only-independent-reset-token-pepper'
$env:DJANGO_DEBUG='true'
uv sync --frozen
uv run ruff check backend scripts tests kali-runner
uv run python backend/manage.py check
uv run python backend/manage.py makemigrations --check --dry-run
uv run python -m unittest discover -s tests
uv run python -m unittest discover -s kali-runner/tests
uv run python backend/manage.py test apps
uv run python scripts/promote_kali_image.py --check
kubectl kustomize k8s
kubectl kustomize k8s | kubectl apply --dry-run=server -f -
docker build -t argus-kali-runner:test kali-runner
docker run --rm --read-only --user 65532:65532 --tmpfs /tmp:rw,nosuid,nodev,size=1g argus-kali-runner:test --self-test
git diff --check
~~~

Expected: every command exits 0; makemigrations reports no changes; Kali config remains false／disabled; no untracked sensitive file is staged.

- [ ] **Step 6: Perform documentation and secret hygiene checks**

Run:

~~~powershell
rg -n "docker exec|ARGUS_KALI_|probe_sql_injection|Kali|SQLmap|CancellationToken" CLAUDE.md ONBOARDING.md backend/apps/scans/CLAUDE.md backend/apps/scans/security/CLAUDE.md backend/apps/agent/CLAUDE.md k8s/README.md docs
rg -n "BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|password=|token=|api[_-]?key=" docs k8s kali-runner backend scripts tests log
git status --short
git diff --stat
~~~

Expected: old K8s=docker-only statements are gone; Compose Docker wording remains scoped to the attack override; sensitive-pattern scan finds only deliberate test literals or documentation warnings, never a real credential.

- [ ] **Step 7: Commit Task 10**

~~~powershell
git add docs/runbooks/kubernetes-secret-at-rest-encryption.md docs/runbooks/kali-sqlmap-rollout.md log/2026-07-14_k8s-kali-sqlmap-implementation.md CLAUDE.md ONBOARDING.md backend/apps/scans/CLAUDE.md backend/apps/scans/security/CLAUDE.md backend/apps/agent/CLAUDE.md k8s/README.md docs/capstone-roadmap.md
git -c user.name=SmallLoOwO -c user.email=60470295+SmallLoOwO@users.noreply.github.com commit -m "docs(kali): hand off the controlled K8s attack chain" -m "Synchronize runtime contracts, encryption and rollout gates, rollback steps, verified tests, and the explicitly deferred attack-tool backlog."
~~~

- [ ] **Step 8: Request review before any push**

Present the exact commit list, changed files, full verification output summary, known untested items and the fact that Kali is still disabled. Wait for the user's explicit push instruction.

---

### Task 11: Control-plane encryption gate and production enablement

**Files:**
- Modify after the gate only: k8s/01-namespace-config.yaml
- Modify after live endpoint discovery only: k8s/07-network-policies.yaml
- Modify: log/2026-07-14_k8s-kali-sqlmap-implementation.md
- Never commit: /etc/kubernetes/enc/encryption-config.yaml, backup archives, encryption keys, sentinel value.

**Interfaces:**
- Consumes: pushed disabled software, promoted real runner digest, cluster-admin access, Argo manual sync.
- Produces: verified Secret at-rest encryption and an explicitly enabled Kubernetes backend.

This task is a mandatory stop gate. Start only after the user approves the maintenance window and confirms a backup destination.

- [ ] **Step 1: Re-discover live topology**

Run:

~~~bash
kubectl version
kubectl get nodes -o wide
kubectl -n default get service kubernetes -o jsonpath='{.spec.clusterIP}{"\n"}'
kubectl -n default get endpointslice -l kubernetes.io/service-name=kubernetes -o jsonpath='{range .items[*].endpoints[*].addresses[*]}{.}{"\n"}{end}'
kubectl get nodes -l node-role.kubernetes.io/control-plane -o name
~~~

Expected: Kubernetes 1.35.x, at least one control-plane node, and explicit API Service/endpoint values. If they differ from 10.96.0.1 and 172.16.2.122, update only the two /32 rules, rerun tests and create a separate reviewed commit before Sync.

- [ ] **Step 2: Create and verify an etcd snapshot**

On every required control-plane procedure, use the actual kubeadm etcd certificates:

~~~bash
sudo mkdir -p -m 700 /var/backups/etcd
SNAPSHOT="/var/backups/etcd/argus-pre-secret-encryption-$(date +%Y%m%d-%H%M%S).db"
sudo ETCDCTL_API=3 etcdctl snapshot save "$SNAPSHOT" \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key
sudo ETCDCTL_API=3 etcdctl snapshot status "$SNAPSHOT" --write-out=table
~~~

Expected: snapshot save succeeds and status shows a nonzero key count. Copy the snapshot and encryption configuration to the approved encrypted backup location; do not paste either into chat or git.

- [ ] **Step 3: Generate and install EncryptionConfiguration**

Generate and install the exact file without printing the key:

~~~bash
umask 077
ARGUS_ENCRYPTION_KEY="$(head -c 32 /dev/urandom | base64 | tr -d '\n')"
export ARGUS_ENCRYPTION_KEY
sudo --preserve-env=ARGUS_ENCRYPTION_KEY python3 - <<'PY'
import os
from pathlib import Path

key = os.environ["ARGUS_ENCRYPTION_KEY"]
directory = Path("/etc/kubernetes/enc")
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
path = directory / "encryption-config.yaml"
path.write_text(
    "apiVersion: apiserver.config.k8s.io/v1\n"
    "kind: EncryptionConfiguration\n"
    "resources:\n"
    "  - resources:\n"
    "      - secrets\n"
    "    providers:\n"
    "      - aesgcm:\n"
    "          keys:\n"
    "            - name: key1\n"
    f"              secret: {key}\n"
    "      - identity: {}\n",
    encoding="utf-8",
)
path.chmod(0o600)
PY
unset ARGUS_ENCRYPTION_KEY
~~~

Expected: /etc/kubernetes/enc/encryption-config.yaml is root-owned mode 600. Confirm the key and snapshot are stored in the approved encrypted custody location and the recovery runbook is accessible before continuing. Do not print, copy into chat or commit its contents.

- [ ] **Step 4: Update kube-apiserver static Pod one control plane at a time**

Add:

~~~yaml
- --encryption-provider-config=/etc/kubernetes/enc/encryption-config.yaml
~~~

and exact volume wiring:

~~~yaml
volumeMounts:
  - name: encryption-config
    mountPath: /etc/kubernetes/enc
    readOnly: true
volumes:
  - name: encryption-config
    hostPath:
      path: /etc/kubernetes/enc
      type: DirectoryOrCreate
~~~

Wait for each kube-apiserver to return Ready and kubectl get --raw=/readyz to report ok before touching the next control plane. If readiness fails, restore the backed-up static Pod manifest immediately.

- [ ] **Step 5: Prove new Secret data is encrypted in raw etcd**

Generate a random sentinel in a shell variable, create it in argus-kali, then query the exact raw etcd key without printing the value:

~~~bash
SENTINEL="argus-encryption-$(date +%s)-$(openssl rand -hex 8)"
kubectl -n argus-kali create secret generic argus-encryption-sentinel \
  --from-literal=value="$SENTINEL"
sudo ETCDCTL_API=3 etcdctl get \
  /registry/secrets/argus-kali/argus-encryption-sentinel \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  --print-value-only | grep -a -q "$SENTINEL" && exit 1 || true
unset SENTINEL
kubectl -n argus-kali delete secret argus-encryption-sentinel
~~~

Expected: grep does not find plaintext. kubectl can still read the sentinel through the API. Delete it immediately.

- [ ] **Step 6: Rewrite existing Secrets and verify services**

During the maintenance window:

~~~bash
kubectl get secrets --all-namespaces -o json | kubectl replace -f -
kubectl get --raw=/readyz
kubectl -n argocd get pods
kubectl -n argus get job,pod,deploy
kubectl -n argus get secret argus-secret -o jsonpath='{.metadata.resourceVersion}{"\n"}'
~~~

Expected: replace succeeds, API Ready, Argo pods Ready, web/worker/frontend Ready and migrate completed. Check only key presence for argus-secret; never print values.

- [ ] **Step 7: Apply disabled infrastructure and smoke orchestration**

With Kali still disabled, obtain user approval for push and manual Argo Sync. Verify Synced/Healthy. Passive and unauthorized active scans must create zero Jobs. Run only runner --self-test/version in a manually admitted Job that contains no user target.

- [ ] **Step 8: Enable through a reviewed Git commit**

Only after Steps 1-7 pass, change:

~~~yaml
ARGUS_KALI_ENABLED: "true"
ARGUS_KALI_BACKEND: "kubernetes"
~~~

Run the Task 10 full suite, commit only k8s/01-namespace-config.yaml and the updated log, show diff/verification to the user and wait for explicit push.

- [ ] **Step 9: Perform one authorized positive acceptance**

After manual Argo Sync:

1. confirm worker ServiceAccount and API egress;
2. confirm passive and unauthorized scans expose no SQLmap tool and create no Job;
3. use only a user-confirmed owned test target;
4. confirm Hermes tool call precedes fallback;
5. confirm one runner maximum, confirmed Finding, changed scoring and clean Job/Secret state;
6. confirm ScanJob completes only after Kali stage resolves.

No third-party target is permitted.

- [ ] **Step 10: Exercise rollback**

Set false／disabled, restart worker, verify no new Job, delete only resources labeled argus.io/managed-by=argus and remove the cross-namespace RoleBinding only if needed. Secret encryption remains enabled. Record commands, outcomes and any untested branch in the log.

## Final Review Gates

- [ ] Every approved spec requirement maps to a task above.
- [ ] No code path can create a Kubernetes Job while disabled, passive or unauthorized.
- [ ] AI and fallback share one Redis target budget and one executor facade.
- [ ] ScanCancelled is never converted to a silent Kali error.
- [ ] Runner, AgentStep, Finding and scan log contain no raw URL query value or SQLmap output.
- [ ] Admission rejects image, command, identity, host access, privilege, missing resources and excessive deadline changes.
- [ ] Real Redis race and isolated Calico integration pass.
- [ ] Full backend tests, Ruff, Django check, migration drift, root contracts, Kustomize, server dry-run and runner smoke pass.
- [ ] Software can be merged and deployed disabled before the control-plane gate.
- [ ] Encryption key, snapshot, Secret data, SSH details and user information never enter git or logs.
- [ ] The final handoff lists any functionality still not live-tested.
