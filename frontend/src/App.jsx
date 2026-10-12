import { lazy, startTransition, Suspense, useEffect, useState } from "react";

import PageLoader from "./shared/PageLoader.jsx";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";

import { useArgusStore } from "./store";
import { useDocumentTitle } from "./shared/documentTitle";

// 掃描詳情的舊子網址轉到新分頁（保留已分享出去的連結）
function ScanSubpathRedirect({ to }) {
  const { scanId } = useParams();
  return <Navigate to={`/scans/${scanId}${to ? `/${to}` : ""}`} replace />;
}

// 2026-10-06 前的分享網址
function ShareRedirect() {
  const { token } = useParams();
  return <Navigate to={`/optimized/${token}`} replace />;
}

function lazyNamed(loader, exportName) {
  let loaded = null;
  const load = () => loader().then((module) => {
    loaded = module[exportName];
    return { default: loaded };
  });
  const Lazy = lazy(load);
  // 已載入（建置時預先渲染、或 hydrate 前先 preload）就直接渲染，不經過 Suspense：
  // hydrate 時若還有沒載入的 lazy 區塊，登入狀態一更新就會出 React #421 並整塊重畫。
  // 每個實例掛載時決定一次，之後不換元件型別（換了會整頁重掛、狀態消失）。
  function LazyNamed(props) {
    const [Loaded] = useState(() => loaded);
    return Loaded ? <Loaded {...props} /> : <Lazy {...props} />;
  }
  LazyNamed.preload = load;
  return LazyNamed;
}

const loadAuthPages = () => import("./features/auth/AuthPages.jsx");
const loadScanExperience = () => import("./features/scans/ScanExperience.jsx");
const loadOptimizationResult = () => import("./features/optimize/OptimizationResultPage.jsx");
const loadDomainPages = () => import("./features/domains/DomainVerifyPage.jsx");
const loadAuthenticatedPages = () => import("./features/account/AuthenticatedPages.jsx");
const loadReviewsPage = () => import("./features/reviews/ReviewsPage.jsx");
const loadPublicPages = () => import("./features/public/PublicPages.jsx");
const loadPartnersPage = () => import("./features/public/PartnersPage.jsx");
const loadLegalPages = () => import("./features/public/LegalPages.jsx");
const loadScannerInfoPage = () => import("./features/public/ScannerInfoPage.jsx");
const loadMcpAccessPage = () => import("./features/account/McpAccessPage.jsx");
const loadProjectWorkspace = () => import("./features/projects/ProjectWorkspace.jsx");
const loadProjectPages = () => import("./features/projects/ProjectPages.jsx");
const loadProjectSeoPage = () => import("./features/projects/ProjectSeoPage.jsx");
const loadAdminPages = () => import("./features/admin/AdminPages.jsx");
const loadAdminOrders = () => import("./features/admin/AdminOrdersPage.jsx");
const loadAdminOverview = () => import("./features/admin/AdminOverviewPage.jsx");
const loadAdminHealth = () => import("./features/admin/AdminHealthPage.jsx");
const loadAdminScans = () => import("./features/admin/AdminScansPages");
const loadAdminUsers = () => import("./features/admin/AdminUsersPages");
const loadAdminTransactions = () => import("./features/admin/AdminTransactionsPage");
const loadAdminReviews = () => import("./features/admin/AdminReviewsPage");
const loadAdminDomains = () => import("./features/admin/AdminDomainsPage");
const loadAdminAuditLog = () => import("./features/admin/AdminAuditLogPage");
const loadAdminAnnouncements = () => import("./features/admin/AdminAnnouncementsPage");
const loadAdminPlans = () => import("./features/admin/AdminPlansPage");

const RequireAuth = lazyNamed(loadAuthPages, "RequireAuth");
const LoginPage = lazyNamed(loadAuthPages, "LoginPage");
const AccountSetupPage = lazyNamed(loadAuthPages, "AccountSetupPage");
const PasswordResetRequestPage = lazyNamed(loadAuthPages, "PasswordResetRequestPage");
const PasswordResetConfirmPage = lazyNamed(loadAuthPages, "PasswordResetConfirmPage");
const ScanLayout = lazyNamed(loadScanExperience, "ScanLayout");
const ScanDetailPage = lazyNamed(loadScanExperience, "ScanDetailPage");
const ScanStrengthsPage = lazyNamed(loadScanExperience, "ScanStrengthsPage");
const ScanArchitecturePage = lazyNamed(loadScanExperience, "ScanArchitecturePage");
const TopologyPage = lazyNamed(loadScanExperience, "TopologyPage");
const ScanPerformancePage = lazyNamed(loadScanExperience, "ScanPerformancePage");
const ScanScorePage = lazyNamed(loadScanExperience, "ScanScorePage");
const OptimizationResultPage = lazyNamed(loadOptimizationResult, "OptimizationResultPage");
const DomainVerifyPage = lazyNamed(loadDomainPages, "DomainVerifyPage");
const TopNav = lazyNamed(loadAuthenticatedPages, "TopNav");
const BillingPage = lazyNamed(loadAuthenticatedPages, "BillingPage");
const ReviewsPage = lazyNamed(loadReviewsPage, "ReviewsPage");
const SettingsPage = lazyNamed(loadAuthenticatedPages, "SettingsPage");
const McpAccessPage = lazyNamed(loadMcpAccessPage, "McpAccessPage");
const ProjectWorkspace = lazyNamed(loadProjectWorkspace, "ProjectWorkspace");
const ProjectScanShell = lazyNamed(loadProjectWorkspace, "ProjectScanShell");
const ProjectHomeRedirect = lazyNamed(loadProjectWorkspace, "ProjectHomeRedirect");
const ProjectsListPage = lazyNamed(loadProjectWorkspace, "ProjectsListPage");
const ProjectCreatePage = lazyNamed(loadProjectWorkspace, "ProjectCreatePage");
const ProjectOverviewPage = lazyNamed(loadProjectPages, "ProjectOverviewPage");
const ProjectScansPage = lazyNamed(loadProjectPages, "ProjectScansPage");
const ProjectIssuesPage = lazyNamed(loadProjectPages, "ProjectIssuesPage");
const ProjectPagesPage = lazyNamed(loadProjectPages, "ProjectPagesPage");
const ProjectAeoPage = lazyNamed(loadProjectPages, "ProjectAeoPage");
const ProjectSeoPage = lazyNamed(loadProjectSeoPage, "ProjectSeoPage");
const ProjectSecurityPage = lazyNamed(
  () => import("./features/projects/ProjectSecurityPage.jsx"),
  "ProjectSecurityPage",
);
const ProjectSettingsPage = lazyNamed(loadProjectPages, "ProjectSettingsPage");
const PublicLayout = lazyNamed(loadPublicPages, "PublicLayout");
const SharedOptimizationPage = lazy(() => import("./features/optimize/SharedOptimizationPage.jsx"));
const ProjectPage = lazyNamed(loadPublicPages, "ProjectPage");
const PurchasePage = lazyNamed(loadPublicPages, "PurchasePage");
const FreeToolsPage = lazyNamed(loadPublicPages, "FreeToolsPage");
const DownloadPage = lazyNamed(loadPublicPages, "DownloadPage");
const VerifyReportPage = lazyNamed(loadPublicPages, "VerifyReportPage");
const PartnersPage = lazyNamed(loadPartnersPage, "PartnersPage");
const PrivacyPolicyPage = lazyNamed(loadLegalPages, "PrivacyPolicyPage");
const TermsOfServicePage = lazyNamed(loadLegalPages, "TermsOfServicePage");
const ScannerInfoPage = lazyNamed(loadScannerInfoPage, "ScannerInfoPage");
const RequireAdmin = lazyNamed(loadAdminPages, "RequireAdmin");
const AdminLayout = lazyNamed(loadAdminPages, "AdminLayout");
const AdminOverviewPage = lazyNamed(loadAdminOverview, "AdminOverviewPage");
const AdminUsersPage = lazyNamed(loadAdminUsers, "AdminUsersPage");
const AdminUserDetailPage = lazyNamed(loadAdminUsers, "AdminUserDetailPage");
const AdminTransactionsPage = lazyNamed(loadAdminTransactions, "AdminTransactionsPage");
const AdminOrdersPage = lazyNamed(loadAdminOrders, "AdminOrdersPage");
const AdminHealthPage = lazyNamed(loadAdminHealth, "AdminHealthPage");
const AdminReviewsPage = lazyNamed(loadAdminReviews, "AdminReviewsPage");
const AdminScansPage = lazyNamed(loadAdminScans, "AdminScansPage");
const AdminScanDetailPage = lazyNamed(loadAdminScans, "AdminScanDetailPage");
const AdminDomainsPage = lazyNamed(loadAdminDomains, "AdminDomainsPage");
const AdminContentPage = lazyNamed(loadAdminPages, "AdminContentPage");
const AdminPartnerInquiriesPage = lazyNamed(loadAdminPages, "AdminPartnerInquiriesPage");
const AdminPlansPage = lazyNamed(loadAdminPlans, "AdminPlansPage");
const AdminSettingsPage = lazyNamed(loadAdminPages, "AdminSettingsPage");
const AdminAuditLogPage = lazyNamed(loadAdminAuditLog, "AdminAuditLogPage");
const AdminAnnouncementsPage = lazyNamed(loadAdminAnnouncements, "AdminAnnouncementsPage");
// 建置時預先渲染的公開頁（scripts/prerender.mjs 依此表產出 HTML；main.jsx hydrate 前先載入對應元件）
// 列出這頁會渲染到的所有 lazy 元件（不在 isPublic 的頁面還有 TopNav）；新增公開頁時加進來，
// 也要加進 shared/documentTitle.ts 的標題與摘要表
export const PRERENDERED_ROUTES = {
  "/": [PublicLayout, ProjectPage],
  "/project": [PublicLayout, ProjectPage],
  "/free-tools": [PublicLayout, FreeToolsPage],
  "/purchase": [PublicLayout, PurchasePage],
  "/download": [PublicLayout, DownloadPage],
  "/verify": [PublicLayout, VerifyReportPage],
  "/partners": [PublicLayout, PartnersPage],
  "/privacy": [TopNav, PublicLayout, PrivacyPolicyPage],
  "/terms": [TopNav, PublicLayout, TermsOfServicePage],
  "/scanner": [PublicLayout, ScannerInfoPage],
  "/reviews": [PublicLayout, ReviewsPage],
  "/login": [TopNav, LoginPage],
};

export function preloadRoute(pathname) {
  const components = PRERENDERED_ROUTES[pathname.replace(/(.)\/$/, "$1")] || [];
  return Promise.all(components.map((component) => component.preload()));
}

// 產品介紹（/ 與 /project 共用）：/ 先顯示產品介紹（與預先渲染的 HTML 一致），登入狀態確認後
// 再轉到會員區或 /project。兩個路由用同一個元件，轉到 /project 時頁面不會重新掛載（否則整頁跳動，CLS 偏高）
function ProjectEntry() {
  const accessToken = useArgusStore((state) => state.accessToken);
  const authReady = useArgusStore((state) => state.authReady);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (pathname === "/" && authReady) navigate(accessToken ? "/dashboard" : "/project", { replace: true });
  }, [pathname, authReady, accessToken, navigate]);
  return <ProjectPage />;
}

const IntroSequence = lazy(() => import("./components/brand/IntroSequence.jsx"));
const NotFoundPage = lazy(() => import("./features/public/NotFoundPage.jsx"));

// 網站專案工作區（含掃描詳情）、網域驗證、購點維持改版前（462848b）外觀：舊版樣式只在這個包裝內生效，
// 見 styles/legacy-member/index.css。包裝本身是 display: contents，不影響版面。
function MemberLegacy({ children }) {
  return <div className="member-legacy">{children}</div>;
}

function AppShell({ googleOAuthEnabled }) {
  const accessToken = useArgusStore((state) => state.accessToken);
  const authReady = useArgusStore((state) => state.authReady);
  const restoreSession = useArgusStore((state) => state.restoreSession);
  const location = useLocation();
  const isAdmin = location.pathname.startsWith("/admin");
  // 評論頁：登入後留在會員區（會員導覽列）；未登入才走公開頁版型
  const isPublic = (location.pathname === "/" && !accessToken) || [
    "/project", "/free-tools", "/purchase", "/download", "/verify", "/partners", "/scanner", "/share", "/optimized",
    ...(accessToken ? [] : ["/reviews"]),
  ].some((p) =>
    // 以路徑段比對：/projects（會員的網站專案）不能被當成公開頁 /project
    location.pathname === p || location.pathname.startsWith(`${p}/`),
  );
  const showTopNav = !isAdmin && !isPublic;
  // 首次進站才播過場動畫（旗標在 store/localStorage）；品牌 ⟡ icon 可呼叫 replayIntro 重播
  const introSeen = useArgusStore((s) => s.introSeen);
  const markIntroSeen = useArgusStore((s) => s.markIntroSeen);
  // mounted：預先渲染的頁面 hydrate 完成後才為 true。
  // - 開場動畫靠 JavaScript 播放與結束，只在掛載後才加上：預先渲染的 HTML 不含這層遮罩
  //   （否則不執行 JavaScript 的訪客會卡在動畫畫面，hydrate 時也會與預先渲染的內容不一致）
  // - 用 startTransition 設定：React 會先把頁面內容 hydrate 完才套用；登入狀態（store）的更新
  //   也等到這之後才開始，否則 hydrate 途中收到更新會出 React #421、整頁改成重新渲染
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    startTransition(() => setMounted(true));
  }, []);
  useEffect(() => {
    if (mounted) restoreSession();
  }, [mounted, restoreSession]);
  useDocumentTitle(location.pathname);
  // 公開頁不必等登入狀態確認完才顯示（2026-10-12）：原本每個頁面都先只有「正在驗證登入狀態…」，
  // 爬蟲與 AI 讀到的是沒有 <main>、H1 與連結的空頁（Argus 自掃 4.16、4.19），訪客也要多等一次 API。
  const rendersWithoutAuth = isPublic || ["/login", "/privacy", "/terms", "/reviews", "/password-reset"].some(
    (p) => location.pathname === p || location.pathname.startsWith(`${p}/`),
  );
  if (!authReady && !rendersWithoutAuth) {
    return <div className="argus-app"><p className="loading-state">正在驗證登入狀態…</p></div>;
  }
  function handleIntroDone() {
    markIntroSeen();
  }
  return (
    <div className={`argus-app ${isAdmin ? "is-admin-mode" : ""} ${isPublic ? "is-public-mode" : ""}`}>
      <Suspense fallback={<PageLoader label="正在載入頁面…" className="is-route" />}>
        {mounted && !introSeen && location.pathname === "/project" && (
          <IntroSequence onComplete={handleIntroDone} />
        )}
        {showTopNav && <TopNav />}
        <main className={`argus-main ${accessToken && showTopNav ? "with-nav" : ""} ${isAdmin ? "is-admin" : ""} ${isPublic ? "is-public" : ""}`}>
          <Routes>
          <Route path="/login" element={<LoginPage googleOAuthEnabled={googleOAuthEnabled} />} />
          <Route path="/password-reset" element={<PasswordResetRequestPage />} />
          <Route path="/password-reset/confirm" element={<PasswordResetConfirmPage />} />
          <Route path="/reviews-next" element={<Navigate to="/reviews" replace />} />
          {/* 頁面優化的分享頁：精簡頁首、唯讀，不套公開頁或會員區的導覽 */}
          <Route path="/optimized/:token" element={<SharedOptimizationPage />} />
          <Route path="/share/rebuilds/:token" element={<ShareRedirect />} />
          <Route element={<PublicLayout />}>
            <Route index element={<ProjectEntry />} />
            <Route path="/project" element={<ProjectEntry />} />
            <Route path="/free-tools" element={<FreeToolsPage />} />
            <Route path="/purchase" element={<PurchasePage />} />
            <Route path="/download" element={<DownloadPage />} />
            <Route path="/verify" element={<VerifyReportPage />} />
            <Route path="/verify/:reportNumber" element={<VerifyReportPage />} />
            <Route path="/partners" element={<PartnersPage />} />
            <Route path="/privacy" element={<PrivacyPolicyPage />} />
            <Route path="/terms" element={<TermsOfServicePage />} />
            <Route path="/scanner" element={<ScannerInfoPage />} />
            {!accessToken && <Route path="/reviews" element={<ReviewsPage />} />}
          </Route>
          {accessToken && <Route path="/reviews" element={<ReviewsPage />} />}
          {/* 會員區以網站專案為單位（docs/adr/0003-site-project-workspace.md）；
              /dashboard、/scans、/history 是舊入口，轉到目前專案的對應分頁 */}
          <Route path="/dashboard" element={<RequireAuth><ProjectHomeRedirect /></RequireAuth>} />
          <Route path="/scans" element={<RequireAuth><ProjectHomeRedirect section="scans" /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><ProjectHomeRedirect section="scans" /></RequireAuth>} />
          <Route
            path="/projects"
            element={
              <RequireAuth>
                <MemberLegacy>
                  <ProjectsListPage />
                </MemberLegacy>
              </RequireAuth>
            }
          />
          <Route
            path="/projects/new"
            element={
              <RequireAuth>
                <MemberLegacy>
                  <ProjectCreatePage />
                </MemberLegacy>
              </RequireAuth>
            }
          />
          <Route
            path="/projects/:projectId"
            element={
              <RequireAuth>
                <MemberLegacy>
                  <ProjectWorkspace />
                </MemberLegacy>
              </RequireAuth>
            }
          >
            <Route index element={<ProjectOverviewPage />} />
            <Route path="scans" element={<ProjectScansPage />} />
            <Route path="seo" element={<ProjectSeoPage />} />
            <Route path="issues" element={<ProjectIssuesPage />} />
            <Route path="pages" element={<ProjectPagesPage />} />
            <Route path="aeo" element={<ProjectAeoPage />} />
            <Route path="security" element={<ProjectSecurityPage />} />
            {/* 歷史報告 2026-10-08 併入「掃描與報告」 */}
            <Route path="history" element={<Navigate to="../scans" replace />} />
            <Route path="settings" element={<ProjectSettingsPage />} />
          </Route>
          <Route
            element={
              <RequireAuth>
                <MemberLegacy>
                  <ProjectScanShell />
                </MemberLegacy>
              </RequireAuth>
            }
          >
            <Route element={<ScanLayout />}>
              <Route path="/scans/:scanId" element={<ScanDetailPage />} />
              <Route path="/scans/:scanId/strengths" element={<ScanStrengthsPage />} />
              <Route path="/scans/:scanId/architecture" element={<ScanArchitecturePage />} />
              <Route path="/scans/:scanId/topology" element={<TopologyPage />} />
              <Route path="/scans/:scanId/performance" element={<ScanPerformancePage />} />
              <Route path="/scans/:scanId/score" element={<ScanScorePage />} />
              {/* 舊網址：修正產出已移除（2026-10-06）；topology 2026-10-10 起是獨立的網站拓撲分頁 */}
              <Route path="/scans/:scanId/fixes" element={<ScanSubpathRedirect to="" />} />
            </Route>
          </Route>
          {/* 頁面優化成果頁：屬於「頁面」分頁，不顯示掃描報告的子分頁 */}
          <Route
            element={
              <RequireAuth>
                <MemberLegacy>
                  <ProjectScanShell section="pages" />
                </MemberLegacy>
              </RequireAuth>
            }
          >
            <Route path="/scans/:scanId/rebuild/:rebuildId" element={<OptimizationResultPage />} />
          </Route>
          <Route
            path="/domains"
            element={
              <RequireAuth>
                <MemberLegacy>
                  <DomainVerifyPage />
                </MemberLegacy>
              </RequireAuth>
            }
          />
          <Route
            path="/billing"
            element={
              <RequireAuth>
                <MemberLegacy>
                  <BillingPage />
                </MemberLegacy>
              </RequireAuth>
            }
          />
          <Route
            path="/account/setup"
            element={
              <RequireAuth>
                <AccountSetupPage />
              </RequireAuth>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAuth>
                <SettingsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/mcp"
            element={
              <RequireAuth>
                <McpAccessPage />
              </RequireAuth>
            }
          />
          <Route
            element={
              <RequireAdmin>
                <AdminLayout />
              </RequireAdmin>
            }
          >
            <Route path="/admin" element={<Navigate to="/admin/overview" replace />} />
            <Route path="/admin/overview" element={<AdminOverviewPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/users/:userId" element={<AdminUserDetailPage />} />
            <Route path="/admin/transactions" element={<AdminTransactionsPage />} />
            <Route path="/admin/orders" element={<AdminOrdersPage />} />
            <Route path="/admin/health" element={<AdminHealthPage />} />
            <Route path="/admin/reviews" element={<AdminReviewsPage />} />
            <Route path="/admin/scans" element={<AdminScansPage />} />
            <Route path="/admin/scans/:scanId" element={<AdminScanDetailPage />} />
            <Route path="/admin/domains" element={<AdminDomainsPage />} />
            <Route path="/admin/content" element={<AdminContentPage />} />
            <Route path="/admin/partner-inquiries" element={<AdminPartnerInquiriesPage />} />
            <Route path="/admin/plans" element={<AdminPlansPage />} />
            <Route path="/admin/settings" element={<AdminSettingsPage />} />
            <Route path="/admin/audit-log" element={<AdminAuditLogPage />} />
            <Route path="/admin/announcements" element={<AdminAnnouncementsPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </main>
      </Suspense>
    </div>
  );
}

export default function App({ googleOAuthEnabled = false }) {
  return <AppShell googleOAuthEnabled={googleOAuthEnabled} />;
}
