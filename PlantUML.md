# Argus UML 圖集

本文件收錄 `Argus_系統手冊_第三章優化版.docx` 與後續系統手冊圖說可使用的 PlantUML 原始碼。為了相容 PlantUML 1.2026.4beta4，本文件不在圖內使用 `title` 指令，圖名統一放在 Markdown 標題中。

## 圖 3-1-1 Argus SaaS 分層系統架構圖

```plantuml
@startuml
' 圖名由 Markdown 標題呈現，避免 PlantUML beta 版本 title 語法相容性問題
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 10
skinparam componentStyle rectangle
skinparam packageStyle rectangle
skinparam ArrowColor #374151
skinparam ArrowThickness 1.2
skinparam BackgroundColor #FFFFFF
skinparam NoteBackgroundColor #FFF7ED
skinparam NoteBorderColor #F97316
skinparam package {
  BorderColor #334155
  FontColor #111827
}
skinparam component {
  BorderColor #334155
  BackgroundColor #F8FAFC
  FontColor #111827
}

actor "網站擁有者 / 分析人員" as User #E0F2FE

package "用戶端層\nReact 18 / Vite / Tailwind / Zustand" as Client #E0F2FE {
  component "React SPA" as React
  component "Scan Wizard\n授權聲明 / 任務送出" as Wizard
  component "Report UI\n弱點 / GEO / 拓撲" as ReportUI
  component "Zustand Stores\nAuth / Scan / Billing" as Stores
}

package "入口與 API 層" as Edge #ECFDF5 {
  component "Nginx / Static Server" as Nginx
  component "Django 5 + DRF" as API
  component "JWT / OAuth / CSRF" as Auth
}

package "後端領域模組" as Domain #F8FAFC {
  component "accounts\n身份 / OAuth / 使用者" as Accounts
  component "scans\nScanJob / Page / Finding" as Scans
  component "billing\n點數 / 訂單 / 交易" as Billing
  component "reviews\n平台評論 / 管理回覆" as Reviews
  component "content\n首頁內容 / FAQ / 公告" as Content
  component "admin_api\n審計 / 管理介面 API" as AdminAPI
}

package "非同步掃描執行層" as Runtime #FEF3C7 {
  queue "Redis\nCelery Broker / Cache" as Redis
  component "Celery Worker" as Worker
  component "Playwright Async Crawler\nsame-origin / robots / depth" as Crawler
  component "Passive Scanners\nSEO / Security / Performance / GEO" as Passive
  component "Active Probes\n需額外授權與 RPS 限制" as Active
  component "Hermes Agent Pipeline\nAI 分析 / 攻擊路徑假設" as Agent
}

package "資料與外部資源層" as Data #EEF2FF {
  database "PostgreSQL / SQLite dev" as DB
  folder "Report Artifacts\nDOCX / JSON / Screenshots" as Artifacts
  cloud "OAuth Providers" as OAuth
  cloud "AI Providers\nMiniMax / GLM / Gemini" as AI
  node "授權目標網站" as Target
}

User --> React : 使用瀏覽器操作
React --> Wizard
React --> ReportUI
React --> Stores
React --> Nginx : HTTPS
Nginx --> API : /api/*
API --> Auth
API --> Accounts
API --> Scans
API --> Billing
API --> Reviews
API --> Content
API --> AdminAPI
Scans --> Redis : enqueue scan job
Billing --> DB : reserve / settle / refund
Accounts --> OAuth : OAuth callback
Worker --> Redis : consume task
Worker --> Crawler
Crawler --> Target : 授權範圍內瀏覽
Crawler --> Passive
Passive --> Active : 僅在 active 授權後
Passive --> Agent : 彙整訊號
Active --> Target : 速率限制探測
Agent --> AI : 模型推理
Scans --> DB
Worker --> DB : 寫入 Page / Finding / 狀態
Worker --> Artifacts
ReportUI --> API : 讀取報告與圖譜資料

note right of Scans
ScanJob 狀態遷移集中由
tasks.py / service 層控管，
避免前端或管理端直接改狀態。
end note

note bottom of Billing
點數流程採 reserve -> settle / refund，
取消、失敗、逾時皆需可追蹤。
end note
@enduml
```

## 圖 3-1-2 掃描任務執行資料流圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 12
skinparam BackgroundColor #FFFFFF
skinparam ArrowColor #374151
skinparam ActivityBorderColor #334155
skinparam ActivityBackgroundColor #F8FAFC
skinparam ActivityDiamondBackgroundColor #FEF3C7
skinparam ActivityDiamondBorderColor #D97706
skinparam partitionBorderColor #CBD5E1
skinparam partitionBackgroundColor #FAFAFA

start
partition "使用者與前端" {
  :輸入目標 URL、掃描深度與頁數限制;
  :確認網站授權、robots.txt 與掃描模式;
  :送出 POST /api/scans/scan-jobs/;
}

partition "Django API / 領域服務" {
  if (URL 格式與 same-origin 規則有效?) then (是)
    :建立 AuthorizationConsent 記錄;
  else (否)
    :回傳 400 與可修正原因;
    stop
  endif

  if (點數足夠?) then (是)
    :BillingService.reserve_cost();
  else (否)
    :回傳 402 / 需要儲值;
    stop
  endif

  :建立 ScanJob = queued;
  :寫入任務參數、授權摘要、成本快照;
  :送入 Redis / Celery queue;
}

partition "Celery Worker / 掃描執行" {
  :ScanJob -> crawling;
  :Playwright 依深度與頁數限制爬取;
  if (使用者取消?) then (是)
    :停止瀏覽器與待處理佇列;
    :BillingService.refund_unused();
    :ScanJob -> cancelled;
    stop
  else (否)
    :萃取 Page、連結、截圖、HTTP metadata;
  endif

  :ScanJob -> scanning;
  :執行 SEO / Security / Performance / GEO 被動掃描;

  if (Active 掃描已額外授權?) then (是)
    :套用 RPS 限制與安全探測白名單;
    :執行低風險 Active Probe;
  else (否)
    :略過 Active Probe，保留未授權註記;
  endif

  if (Agent 分析啟用?) then (是)
    :ScanJob -> agent_testing;
    :整理 Findings 與頁面拓撲;
    :呼叫 AI Provider 產生攻擊路徑與修復建議;
  else (否)
    :直接彙整規則掃描結果;
  endif
}

partition "資料庫與報告" {
  :寫入 Page / Finding / AgentSession;
  :產生報告摘要、拓撲資料、DOCX 匯出素材;
  :BillingService.settle_actual_cost();
  :ScanJob -> completed;
}

stop
@enduml
```

## 圖 3-1-3 ScanJob 核心狀態與橫切機制圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 12
skinparam BackgroundColor #FFFFFF
skinparam StateBorderColor #334155
skinparam StateBackgroundColor #F8FAFC
skinparam StateFontColor #111827
skinparam ArrowColor #374151
skinparam NoteBackgroundColor #EFF6FF
skinparam NoteBorderColor #2563EB

[*] --> queued : 建立任務 / reserve 點數
queued --> crawling : Celery worker 取得任務
crawling --> scanning : 頁面擷取完成
scanning --> agent_testing : 啟用 AI/Agent 分析
scanning --> completed : 規則掃描完成
agent_testing --> completed : AI 分析完成

queued --> cancelled : 使用者取消
crawling --> cancelled : 使用者取消 / 超出授權範圍
scanning --> cancelled : 使用者取消
agent_testing --> cancelled : 使用者取消

queued --> failed : 建立後派送失敗
crawling --> failed : Playwright / 網站錯誤
scanning --> failed : 掃描器未處理例外
agent_testing --> failed : Provider 不可用且無備援

completed --> [*]
cancelled --> [*]
failed --> [*]

state "橫切控制" as CrossCutting {
  [*] --> Consent
  Consent : AuthorizationConsent\n法律授權與掃描範圍
  Consent --> Robots
  Robots : robots.txt / same-origin\n深度與頁數限制
  Robots --> Cost
  Cost : reserve / settle / refund\n點數交易審計
  Cost --> Audit
  Audit : AdminAuditLog\n管理操作留痕
  Audit --> [*]
}

note right of queued
queued 之後不得由前端直接推進狀態；
狀態轉換由後端任務流程集中處理。
end note

note bottom of failed
failed 必須保留 error_code、可重試性、
已扣/未扣點數與最後成功階段。
end note
@enduml
```

## 圖 5-2-1 使用個案圖

```plantuml
@startuml
left to right direction
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 12
skinparam BackgroundColor #FFFFFF
skinparam ActorBorderColor #334155
skinparam ActorBackgroundColor #E0F2FE
skinparam UsecaseBorderColor #334155
skinparam UsecaseBackgroundColor #F8FAFC
skinparam PackageBorderColor #CBD5E1
skinparam PackageBackgroundColor #FAFAFA
skinparam ArrowColor #374151

actor "訪客" as Guest
actor "一般使用者" as Member
actor "Staff 管理員" as Staff
actor "Superuser" as Super
actor "Celery Worker" as Worker
actor "OAuth Provider" as OAuth
actor "AI Provider" as AI

rectangle "Argus SaaS 平台" {
  package "公開與帳號" {
    usecase "瀏覽公開內容" as UC_Public
    usecase "註冊 / 登入" as UC_Login
    usecase "OAuth 登入" as UC_OAuth
  }

  package "掃描任務" {
    usecase "建立掃描任務" as UC_CreateScan
    usecase "確認網站授權" as UC_Consent
    usecase "啟用 Active 掃描" as UC_Active
    usecase "查看進度" as UC_Progress
    usecase "取消任務" as UC_Cancel
  }

  package "報告與知識輸出" {
    usecase "查看掃描報告" as UC_Report
    usecase "查看網站拓撲" as UC_Topology
    usecase "匯出 DOCX 報告" as UC_Docx
    usecase "提交平台評論" as UC_Review
  }

  package "計費" {
    usecase "購買點數" as UC_Buy
    usecase "查詢交易紀錄" as UC_Tx
    usecase "任務成本結算" as UC_Settle
  }

  package "管理端" {
    usecase "管理使用者與角色" as UC_AdminUsers
    usecase "管理掃描任務" as UC_AdminScans
    usecase "管理公開內容" as UC_CMS
    usecase "檢視審計紀錄" as UC_Audit
  }

  package "背景執行" {
    usecase "執行爬取與規則掃描" as UC_WorkerScan
    usecase "執行 Agent 分析" as UC_Agent
  }
}

Guest --> UC_Public
Guest --> UC_Login
UC_Login --> UC_OAuth
OAuth --> UC_OAuth

Member --> UC_CreateScan
UC_CreateScan --> UC_Consent
UC_CreateScan --> UC_Buy
Member --> UC_Active
Member --> UC_Progress
Member --> UC_Cancel
Member --> UC_Report
UC_Report --> UC_Topology
UC_Report --> UC_Docx
Member --> UC_Review
Member --> UC_Tx

Worker --> UC_WorkerScan
UC_WorkerScan --> UC_Settle
UC_WorkerScan --> UC_Agent
AI --> UC_Agent

Staff --> UC_AdminScans
Staff --> UC_CMS
Staff --> UC_Audit
Super --> UC_AdminUsers
Super --> UC_AdminScans
Super --> UC_CMS
Super --> UC_Audit
@enduml
```

## 圖 5-3-1 活動圖：提交掃描任務

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 12
skinparam BackgroundColor #FFFFFF
skinparam ActivityBorderColor #334155
skinparam ActivityBackgroundColor #F8FAFC
skinparam ActivityDiamondBackgroundColor #FEF3C7
skinparam ActivityDiamondBorderColor #D97706
skinparam ArrowColor #374151
skinparam partitionBorderColor #CBD5E1
skinparam partitionBackgroundColor #FAFAFA

start
partition "使用者" {
  :輸入目標網站 URL;
  :選擇掃描深度、頁數上限、掃描模式;
  :勾選授權與責任聲明;
}

partition "React SPA" {
  :前端格式檢查;
  :顯示預估成本與授權提醒;
  :呼叫 POST /api/scans/scan-jobs/;
}

partition "Django API" {
  if (JWT 有效?) then (是)
    :解析請求與序列化驗證;
  else (否)
    :回傳 401;
    stop
  endif

  if (URL、same-origin、授權欄位有效?) then (是)
    :寫入 AuthorizationConsent;
  else (否)
    :回傳 400 與欄位錯誤;
    stop
  endif

  if (點數餘額足夠?) then (是)
    :保留預估點數;
  else (否)
    :回傳 402 與儲值提示;
    stop
  endif

  :建立 ScanJob = queued;
  :送入 Celery 任務佇列;
  :回傳 task_id / scan_job_id;
}

partition "React SPA" {
  :導向任務進度頁;
  :開始輪詢或訂閱任務狀態;
}

partition "Celery Worker" {
  :取得 queued 任務;
  :更新 ScanJob = crawling;
  :啟動 Playwright 爬取;
}

stop
@enduml
```

## 圖 5-4-1 分析類別圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 10
skinparam classAttributeIconSize 0
skinparam BackgroundColor #FFFFFF
skinparam ClassBorderColor #334155
skinparam ClassBackgroundColor #F8FAFC
skinparam ArrowColor #374151
skinparam NoteBackgroundColor #ECFDF5
skinparam NoteBorderColor #10B981

class User {
  +id
  +email
  +role
  +is_staff
  +is_superuser
}

class ScanJob {
  +id
  +target_url
  +status
  +scan_mode
  +depth_limit
  +page_limit
  +estimated_cost
  +actual_cost
  +created_at
  +completed_at
}

class AuthorizationConsent {
  +id
  +scope_summary
  +robots_policy
  +active_scan_allowed
  +ip_address
  +accepted_at
}

class Page {
  +id
  +url
  +status_code
  +content_type
  +depth
  +load_time_ms
}

class Finding {
  +id
  +category
  +severity
  +rule_id
  +title
  +evidence
  +recommendation
}

class AgentSession {
  +id
  +provider
  +model_name
  +status
  +capability_summary
  +token_usage
}

class CoinWallet {
  +id
  +balance
  +reserved_balance
}

class CoinTransaction {
  +id
  +type
  +amount
  +status
  +reference
}

class PricingPlan {
  +id
  +name
  +coins
  +price
  +is_active
}

class PurchaseOrder {
  +id
  +provider
  +amount
  +status
  +paid_at
}

class PlatformReview {
  +id
  +rating
  +content
  +status
}

class ReviewMessage {
  +id
  +message
  +is_staff_reply
}

class AdminAuditLog {
  +id
  +actor
  +action
  +target_type
  +target_id
  +created_at
}

User "1" -- "0..*" ScanJob : owns
User "1" -- "1" CoinWallet : has
User "1" -- "0..*" PlatformReview : writes
User "1" -- "0..*" ReviewMessage : sends
User "1" -- "0..*" AdminAuditLog : performs

ScanJob "1" -- "1" AuthorizationConsent : requires
ScanJob "1" -- "0..*" Page : crawls
ScanJob "1" -- "0..*" Finding : produces
ScanJob "1" -- "0..*" AgentSession : analyzes
ScanJob "1" -- "0..*" CoinTransaction : reserves / settles

Page "1" -- "0..*" Finding : evidence on
CoinWallet "1" -- "0..*" CoinTransaction : records
PricingPlan "1" -- "0..*" PurchaseOrder : purchased as
PurchaseOrder "1" -- "0..*" CoinTransaction : credits
PlatformReview "1" -- "0..*" ReviewMessage : discussion

note right of AuthorizationConsent
記錄授權聲明、掃描範圍、
Active 額外授權與來源 IP，
支撐法律與審計需求。
end note
@enduml
```

## 圖 6-1-1 掃描任務循序圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 10
skinparam sequence {
  ArrowColor #374151
  LifeLineBorderColor #CBD5E1
  LifeLineBackgroundColor #F8FAFC
  ParticipantBorderColor #334155
  ParticipantBackgroundColor #E0F2FE
  ActorBorderColor #334155
  ActorBackgroundColor #ECFDF5
}
hide footbox
autonumber

actor "使用者" as User
participant "React SPA" as SPA
participant "ScanJobViewSet\nDjango DRF" as API #E0F2FE
participant "BillingService" as Billing #FEF3C7
database "PostgreSQL" as DB #EEF2FF
queue "Redis / Celery Broker" as Redis #FCE7F3
participant "run_scan_job\nCelery Task" as Task #FEF3C7
participant "Playwright\nChromium" as Browser #ECFDF5
participant "四維掃描器\nSEO/Security/Performance/GEO" as Scanners #ECFDF5
participant "Hermes Agent\n可選" as Agent #F3E8FF
participant "AI Provider" as AI #F3E8FF

User -> SPA : 填寫 URL、限制、授權聲明
SPA -> API : POST /api/scans/scan-jobs/
API -> API : Serializer 驗證 URL / same-origin / 授權欄位
API -> Billing : reserve_cost(user, estimated_cost)
Billing -> DB : 建立 reserved CoinTransaction
API -> DB : 建立 ScanJob = queued
API -> Redis : enqueue run_scan_job(scan_job_id)
API --> SPA : 201 Created + scan_job_id
SPA --> User : 顯示進度頁

Redis -> Task : 派送任務
Task -> DB : ScanJob = crawling
Task -> Browser : 啟動 browser context
Browser -> Browser : robots.txt / depth / page limit 控制
Browser --> Task : pages + screenshots + network metadata
Task -> DB : 寫入 Page

Task -> DB : ScanJob = scanning
Task -> Scanners : 執行被動規則掃描
Scanners --> Task : Finding candidates

alt Active 掃描已額外授權
  Task -> Scanners : 執行低風險 Active Probe / RPS 限制
  Scanners --> Task : Active findings
else 未授權 Active
  Task -> DB : 記錄 skipped_active_scan_reason
end

opt 啟用 Agent 分析
  Task -> DB : ScanJob = agent_testing
  Task -> Agent : 彙整 pages / findings / topology
  Agent -> AI : 呼叫可用模型
  AI --> Agent : 風險敘事與修復建議
  Agent --> Task : AgentSession + enriched findings
end

Task -> DB : 寫入 Finding / AgentSession / report summary
Task -> Billing : settle_actual_cost(scan_job_id)
Billing -> DB : 完成點數結算
Task -> DB : ScanJob = completed
SPA -> API : GET /api/scans/scan-jobs/{id}/
API -> DB : 讀取報告資料
API --> SPA : report JSON
SPA --> User : 呈現報告、拓撲與匯出入口
@enduml
```

## 圖 6-2-1 設計類別圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 10
skinparam classAttributeIconSize 0
skinparam BackgroundColor #FFFFFF
skinparam ClassBorderColor #334155
skinparam ClassBackgroundColor #F8FAFC
skinparam ArrowColor #374151
skinparam NoteBackgroundColor #FEF3C7
skinparam NoteBorderColor #D97706

class ScanJobViewSet <<DRF Controller>> {
  +create(request)
  +retrieve(request, pk)
  +cancel(request, pk)
  +export_docx(request, pk)
}

class ScanJobCreateSerializer <<Serializer>> {
  +validate_target_url()
  +validate_authorization()
  +create(validated_data)
}

class BillingService <<Domain Service>> {
  +estimate_cost(params)
  +reserve_cost(user, amount)
  +settle_actual_cost(scan_job)
  +refund_unused(scan_job)
}

class RunScanJobTask <<Celery Task>> {
  +run(scan_job_id)
  -transition(status)
  -handle_failure(error)
}

class Crawler <<Runtime Adapter>> {
  +crawl(target_url, limits)
  +respect_robots_txt()
  +enforce_same_origin()
}

class StaticScanners <<Scanner Facade>> {
  +scan_seo(page)
  +scan_security(page)
  +scan_performance(page)
  +scan_geo(page)
}

class ActiveProbes <<Optional Scanner>> {
  +probe_headers()
  +probe_common_paths()
  +throttle_rps()
}

class AgentRunner <<AI Orchestrator>> {
  +select_provider()
  +summarize_capabilities()
  +analyze_attack_paths()
}

class ReportBuilder <<Application Service>> {
  +build_json(scan_job)
  +build_topology(scan_job)
  +export_docx(scan_job)
}

class AdminAuditService <<Cross-cutting Service>> {
  +record(actor, action, target)
}

ScanJobViewSet --> ScanJobCreateSerializer : validates
ScanJobViewSet --> BillingService : estimate / reserve / refund
ScanJobViewSet --> ReportBuilder : report / export
ScanJobViewSet --> AdminAuditService : admin actions
ScanJobViewSet --> RunScanJobTask : enqueue

RunScanJobTask --> Crawler : crawl pages
RunScanJobTask --> StaticScanners : passive scan
RunScanJobTask --> ActiveProbes : when authorized
RunScanJobTask --> AgentRunner : optional analysis
RunScanJobTask --> BillingService : settle / refund
RunScanJobTask --> ReportBuilder : materialize report summary

Crawler --> StaticScanners : normalized page snapshots
StaticScanners --> AgentRunner : findings context
ActiveProbes --> AgentRunner : active evidence

note right of ActiveProbes
ActiveProbes 僅在使用者明確授權後執行，
且必須套用 RPS 限制與低風險探測集合。
end note
@enduml
```

## 圖 7-1-1 Docker Compose 佈署圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 12
skinparam componentStyle rectangle
skinparam BackgroundColor #FFFFFF
skinparam NodeBorderColor #334155
skinparam NodeBackgroundColor #F8FAFC
skinparam ArtifactBorderColor #334155
skinparam ArtifactBackgroundColor #E0F2FE
skinparam DatabaseBorderColor #334155
skinparam DatabaseBackgroundColor #EEF2FF
skinparam ArrowColor #374151

node "使用者裝置" as Client {
  artifact "Browser" as Browser
}

node "Docker Host" as Host {
  node "frontend container" as Frontend {
    artifact "React static assets\nserved by Nginx" as FE
  }

  node "web container" as Web {
    artifact "Django + DRF\nGunicorn/Uvicorn" as Django
  }

  node "worker container" as Worker {
    artifact "Celery Worker" as Celery
    artifact "Playwright Chromium" as PW
  }

  database "postgres service" as Postgres
  queue "redis service" as Redis
  folder "media / reports volume" as Media
}

cloud "OAuth Providers" as OAuth
cloud "AI Providers" as AI
node "授權目標網站" as Target

Browser --> FE : HTTPS / static files
Browser --> Django : HTTPS /api/*
Django --> Postgres : ORM
Django --> Redis : cache / enqueue
Django --> Media : report artifacts
Django --> OAuth : OAuth callback
Celery --> Redis : consume jobs
Celery --> Postgres : update ScanJob / Findings
Celery --> Media : screenshots / exports
Celery --> PW : browser automation
PW --> Target : same-origin crawl
Celery --> AI : agent analysis

note bottom of Worker
Playwright browser binaries 必須放在專案內 .ms-playwright，
避免污染使用者層級環境。
end note
@enduml
```

## 圖 7-2-1 套件架構圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 10
skinparam packageStyle rectangle
skinparam BackgroundColor #FFFFFF
skinparam PackageBorderColor #334155
skinparam PackageBackgroundColor #F8FAFC
skinparam ArrowColor #374151
skinparam NoteBackgroundColor #EFF6FF
skinparam NoteBorderColor #2563EB

package "frontend/src" #E0F2FE {
  package "pages" as FE_Pages
  package "components" as FE_Components
  package "stores\nZustand" as FE_Stores
  package "api\nAxios clients" as FE_API
}

package "backend/config" #ECFDF5 {
  package "settings" as Settings
  package "urls" as URLs
  package "celery" as CeleryConfig
}

package "backend/apps" #F8FAFC {
  package "accounts" as Accounts
  package "scans" as Scans
  package "billing" as Billing
  package "reviews" as Reviews
  package "content" as Content
  package "admin_api" as AdminAPI
  package "agent" as Agent
  package "insights" as Insights
}

package "runtime" #FEF3C7 {
  package "playwright crawler" as RuntimeCrawler
  package "scanner rules" as RuntimeRules
  package "report export" as RuntimeReport
}

FE_Pages --> FE_Components
FE_Pages --> FE_Stores
FE_Stores --> FE_API
FE_API --> URLs : /api/*

URLs --> Accounts
URLs --> Scans
URLs --> Billing
URLs --> Reviews
URLs --> Content
URLs --> AdminAPI
CeleryConfig --> Scans

Scans --> Billing : cost reserve / settle
Scans --> Agent : optional analysis
Scans --> Insights : GEO / AEO insights
Scans --> RuntimeCrawler
Scans --> RuntimeRules
Scans --> RuntimeReport
AdminAPI --> Accounts
AdminAPI --> Scans
AdminAPI --> Content
Reviews --> Accounts
Billing --> Accounts

note right of Scans
scans 是掃描流程核心邊界：
任務狀態、頁面、Finding、取消與報告查詢
都應集中在此模組協調。
end note
@enduml
```

## 圖 7-3-1 系統元件圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 10
skinparam componentStyle rectangle
skinparam BackgroundColor #FFFFFF
skinparam ComponentBorderColor #334155
skinparam ComponentBackgroundColor #F8FAFC
skinparam InterfaceBorderColor #334155
skinparam ArrowColor #374151

component "React SPA" as SPA #E0F2FE
component "Django REST API" as API #ECFDF5
component "Domain Services" as Services #F8FAFC
component "Celery Scan Runtime" as Runtime #FEF3C7
component "Report Builder" as Report #EEF2FF
database "Relational Database" as DB #EEF2FF
queue "Redis Broker / Cache" as Redis #FCE7F3
component "Playwright Browser" as Playwright #ECFDF5
component "Scanner Rules" as Rules #ECFDF5
component "Agent Orchestrator" as Agent #F3E8FF
cloud "AI Providers" as AI #F3E8FF
node "Authorized Target Site" as Target

interface "REST JSON API" as IRest
interface "Task Queue" as IQueue
interface "ORM Models" as IOrm
interface "Browser Automation" as IBrowser
interface "Report Export" as IReport

SPA --> IRest
IRest --> API
API --> Services
API --> IQueue
IQueue --> Redis
Redis --> Runtime
Services --> IOrm
Runtime --> IOrm
IOrm --> DB
Runtime --> IBrowser
IBrowser --> Playwright
Playwright --> Target
Runtime --> Rules
Runtime --> Agent
Agent --> AI
Runtime --> IReport
Services --> IReport
IReport --> Report
Report --> DB

note bottom of API
API 僅負責同步請求、權限、序列化與任務派送；
長時間掃描必須交由 Celery Runtime。
end note
@enduml
```

## 圖 7-4-1 ScanJob 狀態機圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam roundcorner 12
skinparam BackgroundColor #FFFFFF
skinparam StateBorderColor #334155
skinparam StateBackgroundColor #F8FAFC
skinparam ArrowColor #374151
skinparam NoteBackgroundColor #FFF7ED
skinparam NoteBorderColor #F97316

[*] --> Draft : 前端尚未送出
Draft --> Validating : POST create
Validating --> Rejected : 欄位 / 授權 / 點數不通過
Validating --> queued : 建立 ScanJob

queued --> crawling : worker started
crawling --> scanning : pages captured
scanning --> agent_testing : agent enabled
agent_testing --> finalizing : agent completed
scanning --> finalizing : agent disabled
finalizing --> completed : report materialized

queued --> cancelling : cancel requested
crawling --> cancelling : cancel requested
scanning --> cancelling : cancel requested
agent_testing --> cancelling : cancel requested
cancelling --> cancelled : cleanup + refund

queued --> failed : enqueue / startup error
crawling --> failed : crawler error
scanning --> failed : scanner error
agent_testing --> failed : provider fallback failed
finalizing --> failed : report persistence error

Rejected --> [*]
completed --> [*]
cancelled --> [*]
failed --> [*]

note right of finalizing
finalizing 階段完成：
Finding 彙整、成本結算、報告摘要、
拓撲資料與可匯出素材。
end note
@enduml
```

## 圖 8-1-1 資料庫 ER 圖

```plantuml
@startuml
skinparam defaultFontName Microsoft JhengHei
skinparam shadowing false
skinparam linetype ortho
skinparam roundcorner 8
skinparam BackgroundColor #FFFFFF
skinparam EntityBorderColor #334155
skinparam EntityBackgroundColor #F8FAFC
skinparam ArrowColor #374151

entity "auth_user" as user {
  * id : bigint <<PK>>
  --
  email : varchar
  username : varchar
  is_staff : boolean
  is_superuser : boolean
  date_joined : datetime
}

entity "scans_scanjob" as scanjob {
  * id : bigint <<PK>>
  --
  user_id : bigint <<FK>>
  target_url : text
  status : varchar
  scan_mode : varchar
  depth_limit : int
  page_limit : int
  estimated_cost : int
  actual_cost : int
  created_at : datetime
}

entity "scans_authorizationconsent" as consent {
  * id : bigint <<PK>>
  --
  scan_job_id : bigint <<FK>>
  active_scan_allowed : boolean
  scope_summary : text
  robots_policy : text
  accepted_at : datetime
}

entity "scans_page" as page {
  * id : bigint <<PK>>
  --
  scan_job_id : bigint <<FK>>
  url : text
  status_code : int
  depth : int
  load_time_ms : int
}

entity "scans_finding" as finding {
  * id : bigint <<PK>>
  --
  scan_job_id : bigint <<FK>>
  page_id : bigint <<FK>>
  category : varchar
  severity : varchar
  rule_id : varchar
  title : varchar
}

entity "scans_agentsession" as agentsession {
  * id : bigint <<PK>>
  --
  scan_job_id : bigint <<FK>>
  provider : varchar
  model_name : varchar
  status : varchar
  token_usage : json
}

entity "billing_coinwallet" as wallet {
  * id : bigint <<PK>>
  --
  user_id : bigint <<FK>>
  balance : int
  reserved_balance : int
}

entity "billing_cointransaction" as tx {
  * id : bigint <<PK>>
  --
  wallet_id : bigint <<FK>>
  scan_job_id : bigint <<FK>>
  type : varchar
  amount : int
  status : varchar
  created_at : datetime
}

entity "billing_pricingplan" as plan {
  * id : bigint <<PK>>
  --
  name : varchar
  coins : int
  price : decimal
  is_active : boolean
}

entity "billing_purchaseorder" as order {
  * id : bigint <<PK>>
  --
  user_id : bigint <<FK>>
  pricing_plan_id : bigint <<FK>>
  provider : varchar
  amount : decimal
  status : varchar
}

entity "reviews_platformreview" as review {
  * id : bigint <<PK>>
  --
  user_id : bigint <<FK>>
  rating : int
  content : text
  status : varchar
}

entity "reviews_reviewmessage" as message {
  * id : bigint <<PK>>
  --
  review_id : bigint <<FK>>
  user_id : bigint <<FK>>
  message : text
  is_staff_reply : boolean
}

entity "admin_api_adminauditlog" as audit {
  * id : bigint <<PK>>
  --
  actor_id : bigint <<FK>>
  action : varchar
  target_type : varchar
  target_id : varchar
  created_at : datetime
}

user ||--o{ scanjob : owns
scanjob ||--|| consent : requires
scanjob ||--o{ page : crawls
scanjob ||--o{ finding : produces
page ||--o{ finding : contains
scanjob ||--o{ agentsession : analyzes

user ||--|| wallet : has
wallet ||--o{ tx : records
scanjob ||--o{ tx : billed_by
plan ||--o{ order : selected_by
user ||--o{ order : places

user ||--o{ review : writes
review ||--o{ message : discusses
user ||--o{ message : sends
user ||--o{ audit : performs
@enduml
```
