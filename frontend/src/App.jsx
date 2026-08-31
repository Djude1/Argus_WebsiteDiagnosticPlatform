import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useArgusStore } from "./store";

function lazyNamed(loader, exportName) {
  return lazy(() => loader().then((module) => ({ default: module[exportName] })));
}

const loadAuthPages = () => import("./features/auth/AuthPages.jsx");
const loadScanExperience = () => import("./features/scans/ScanExperience.jsx");
const loadAuthenticatedPages = () => import("./features/account/AuthenticatedPages.jsx");
const loadReviewsPage = () => import("./features/reviews/ReviewsPage.jsx");
const loadPublicPages = () => import("./features/public/PublicPages.jsx");
const loadAdminPages = () => import("./features/admin/AdminPages.jsx");

const RequireAuth = lazyNamed(loadAuthPages, "RequireAuth");
const LoginPage = lazyNamed(loadAuthPages, "LoginPage");
const PasswordResetRequestPage = lazyNamed(loadAuthPages, "PasswordResetRequestPage");
const PasswordResetConfirmPage = lazyNamed(loadAuthPages, "PasswordResetConfirmPage");
const ScanLayout = lazyNamed(loadScanExperience, "ScanLayout");
const ScansPlaceholder = lazyNamed(loadScanExperience, "ScansPlaceholder");
const ScanDetailPage = lazyNamed(loadScanExperience, "ScanDetailPage");
const TopologyPage = lazyNamed(loadScanExperience, "TopologyPage");
const TopNav = lazyNamed(loadAuthenticatedPages, "TopNav");
const DashboardPage = lazyNamed(loadAuthenticatedPages, "DashboardPage");
const HistoryPage = lazyNamed(loadAuthenticatedPages, "HistoryPage");
const BillingPage = lazyNamed(loadAuthenticatedPages, "BillingPage");
const ReviewsPage = lazyNamed(loadReviewsPage, "ReviewsPage");
const SettingsPage = lazyNamed(loadAuthenticatedPages, "SettingsPage");
const PublicLayout = lazyNamed(loadPublicPages, "PublicLayout");
const ProjectPage = lazyNamed(loadPublicPages, "ProjectPage");
const TeamPage = lazyNamed(loadPublicPages, "TeamPage");
const PurchasePage = lazyNamed(loadPublicPages, "PurchasePage");
const FreeToolsPage = lazyNamed(loadPublicPages, "FreeToolsPage");
const DownloadPage = lazyNamed(loadPublicPages, "DownloadPage");
const VerifyReportPage = lazyNamed(loadPublicPages, "VerifyReportPage");
const RequireAdmin = lazyNamed(loadAdminPages, "RequireAdmin");
const AdminLayout = lazyNamed(loadAdminPages, "AdminLayout");
const AdminOverviewPage = lazyNamed(loadAdminPages, "AdminOverviewPage");
const AdminUsersPage = lazyNamed(loadAdminPages, "AdminUsersPage");
const AdminUserDetailPage = lazyNamed(loadAdminPages, "AdminUserDetailPage");
const AdminTransactionsPage = lazyNamed(loadAdminPages, "AdminTransactionsPage");
const AdminReviewsPage = lazyNamed(loadAdminPages, "AdminReviewsPage");
const AdminScansPage = lazyNamed(loadAdminPages, "AdminScansPage");
const AdminScanDetailPage = lazyNamed(loadAdminPages, "AdminScanDetailPage");
const AdminContentPage = lazyNamed(loadAdminPages, "AdminContentPage");
const AdminPlansPage = lazyNamed(loadAdminPages, "AdminPlansPage");
const AdminSettingsPage = lazyNamed(loadAdminPages, "AdminSettingsPage");
const AdminAuditLogPage = lazyNamed(loadAdminPages, "AdminAuditLogPage");
const AdminAnnouncementsPage = lazyNamed(loadAdminPages, "AdminAnnouncementsPage");
const IntroSequence = lazy(() => import("./components/brand/IntroSequence.jsx"));
const NotFoundPage = lazy(() => import("./features/public/NotFoundPage.jsx"));

function AppShell({ googleOAuthEnabled }) {
  const accessToken = useArgusStore((state) => state.accessToken);
  const authReady = useArgusStore((state) => state.authReady);
  const restoreSession = useArgusStore((state) => state.restoreSession);
  const location = useLocation();
  const isAdmin = location.pathname.startsWith("/admin");
  const isPublic = [
    "/project", "/free-tools", "/team", "/purchase", "/download", "/reviews", "/verify",
  ].some((p) =>
    location.pathname.startsWith(p),
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
            <Route path="/team" element={<TeamPage />} />
            <Route path="/purchase" element={<PurchasePage />} />
            <Route path="/download" element={<DownloadPage />} />
            <Route path="/verify" element={<VerifyReportPage />} />
            <Route path="/verify/:reportNumber" element={<VerifyReportPage />} />
            <Route path="/reviews" element={<ReviewsPage />} />
          </Route>
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            element={
              <RequireAuth>
                <ScanLayout />
              </RequireAuth>
            }
          >
            <Route path="/scans" element={<ScansPlaceholder />} />
            <Route path="/scans/:scanId" element={<ScanDetailPage />} />
            <Route path="/scans/:scanId/topology" element={<TopologyPage />} />
          </Route>
          <Route
            path="/history"
            element={
              <RequireAuth>
                <HistoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/billing"
            element={
              <RequireAuth>
                <BillingPage />
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
            <Route path="/admin/reviews" element={<AdminReviewsPage />} />
            <Route path="/admin/scans" element={<AdminScansPage />} />
            <Route path="/admin/scans/:scanId" element={<AdminScanDetailPage />} />
            <Route path="/admin/content" element={<AdminContentPage />} />
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
