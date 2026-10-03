import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useArgusStore } from "./store";

function lazyNamed(loader, exportName) {
  return lazy(() => loader().then((module) => ({ default: module[exportName] })));
}

const loadAuthPages = () => import("./features/auth/AuthPages.jsx");
const loadScanExperience = () => import("./features/scans/ScanExperience.jsx");
const loadRebuildWorkspace = () => import("./features/scans/RebuildWorkspace.jsx");
const loadDomainPages = () => import("./features/domains/DomainVerifyPage.jsx");
const loadAuthenticatedPages = () => import("./features/account/AuthenticatedPages.jsx");
const loadReviewsPage = () => import("./features/reviews/ReviewsPage.jsx");
const loadPublicPages = () => import("./features/public/PublicPages.jsx");
const loadPartnersPage = () => import("./features/public/PartnersPage.jsx");
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
const PasswordResetRequestPage = lazyNamed(loadAuthPages, "PasswordResetRequestPage");
const PasswordResetConfirmPage = lazyNamed(loadAuthPages, "PasswordResetConfirmPage");
const ScanLayout = lazyNamed(loadScanExperience, "ScanLayout");
const ScanDetailPage = lazyNamed(loadScanExperience, "ScanDetailPage");
const TopologyPage = lazyNamed(loadScanExperience, "TopologyPage");
const ScanFixOutputPage = lazyNamed(loadScanExperience, "ScanFixOutputPage");
const RebuildWorkspace = lazyNamed(loadRebuildWorkspace, "RebuildWorkspace");
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
const ProjectHistoryPage = lazyNamed(loadProjectPages, "ProjectHistoryPage");
const ProjectSettingsPage = lazyNamed(loadProjectPages, "ProjectSettingsPage");
const PublicLayout = lazyNamed(loadPublicPages, "PublicLayout");
const ProjectPage = lazyNamed(loadPublicPages, "ProjectPage");
const PurchasePage = lazyNamed(loadPublicPages, "PurchasePage");
const FreeToolsPage = lazyNamed(loadPublicPages, "FreeToolsPage");
const DownloadPage = lazyNamed(loadPublicPages, "DownloadPage");
const VerifyReportPage = lazyNamed(loadPublicPages, "VerifyReportPage");
const PartnersPage = lazyNamed(loadPartnersPage, "PartnersPage");
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
  const isPublic = [
    "/project", "/free-tools", "/purchase", "/download", "/verify", "/partners",
    ...(accessToken ? [] : ["/reviews"]),
  ].some((p) =>
    // 以路徑段比對：/projects（會員的網站專案）不能被當成公開頁 /project
    location.pathname === p || location.pathname.startsWith(`${p}/`),
  );
  const showTopNav = !isAdmin && !isPublic;
  // 首次進站才播過場動畫（旗標在 store/localStorage）；品牌 ⟡ icon 可呼叫 replayIntro 重播
  const introSeen = useArgusStore((s) => s.introSeen);
  const markIntroSeen = useArgusStore((s) => s.markIntroSeen);
  useEffect(() => {
    restoreSession();
  }, [restoreSession]);
  if (!authReady) {
    return <div className="argus-app"><p className="loading-state">正在驗證登入狀態…</p></div>;
  }
  function handleIntroDone() {
    markIntroSeen();
  }
  return (
    <div className={`argus-app ${isAdmin ? "is-admin-mode" : ""} ${isPublic ? "is-public-mode" : ""}`}>
      <Suspense fallback={<p className="loading-state">正在載入頁面…</p>}>
        {!introSeen && location.pathname === "/project" && (
          <IntroSequence onComplete={handleIntroDone} />
        )}
        {showTopNav && <TopNav />}
        <main className={`argus-main ${accessToken && showTopNav ? "with-nav" : ""} ${isAdmin ? "is-admin" : ""} ${isPublic ? "is-public" : ""}`}>
          <Routes>
          <Route path="/" element={<Navigate to={accessToken ? "/dashboard" : "/project"} replace />} />
          <Route path="/login" element={<LoginPage googleOAuthEnabled={googleOAuthEnabled} />} />
          <Route path="/password-reset" element={<PasswordResetRequestPage />} />
          <Route path="/password-reset/confirm" element={<PasswordResetConfirmPage />} />
          <Route path="/reviews-next" element={<Navigate to="/reviews" replace />} />
          <Route element={<PublicLayout />}>
            <Route path="/project" element={<ProjectPage />} />
            <Route path="/free-tools" element={<FreeToolsPage />} />
            <Route path="/purchase" element={<PurchasePage />} />
            <Route path="/download" element={<DownloadPage />} />
            <Route path="/verify" element={<VerifyReportPage />} />
            <Route path="/verify/:reportNumber" element={<VerifyReportPage />} />
            <Route path="/partners" element={<PartnersPage />} />
            {!accessToken && <Route path="/reviews" element={<ReviewsPage />} />}
          </Route>
          {accessToken && <Route path="/reviews" element={<ReviewsPage />} />}
          {/* 會員區以網站專案為單位（docs/adr/0003-site-project-workspace.md）；
              /dashboard、/scans、/history 是舊入口，轉到目前專案的對應分頁 */}
          <Route path="/dashboard" element={<RequireAuth><ProjectHomeRedirect /></RequireAuth>} />
          <Route path="/scans" element={<RequireAuth><ProjectHomeRedirect section="scans" /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><ProjectHomeRedirect section="history" /></RequireAuth>} />
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
            <Route path="history" element={<ProjectHistoryPage />} />
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
              <Route path="/scans/:scanId/topology" element={<TopologyPage />} />
              <Route path="/scans/:scanId/fixes" element={<ScanFixOutputPage />} />
              <Route
                path="/scans/:scanId/rebuild/:rebuildId"
                element={<RebuildWorkspace />}
              />
            </Route>
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
