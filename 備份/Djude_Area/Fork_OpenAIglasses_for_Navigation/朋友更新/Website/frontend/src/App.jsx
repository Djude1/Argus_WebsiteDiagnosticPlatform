import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { ContentProvider } from './context/ContentContext'
import { CartProvider } from './context/CartContext'
import Navbar from './components/Navbar/Navbar'
import Footer from './components/Footer/Footer'
import FloatingCart from './components/FloatingCart/FloatingCart'
import Home from './pages/Home/Home'
import Product from './pages/Product/Product'
import Purchase from './pages/Purchase/Purchase'
import PurchaseResult from './pages/Purchase/PurchaseResult'
import Team from './pages/Team/Team'
import Download from './pages/Download/Download'
import Project from './pages/Project/Project'
import Announcements from './pages/Announcements/Announcements'
import NotFound from './pages/NotFound'
import ScrollToTop from './components/ScrollToTop'
import ErrorBoundary from './components/ErrorBoundary'
import AdminApp from './admin/AdminApp'

// 每次路由切換時上報頁面瀏覽（SPA 無法靠伺服器感知路由）
function PageTracker() {
  const location = useLocation()
  useEffect(() => {
    fetch('/api/analytics/track/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: location.pathname }),
    }).catch(() => {})
  }, [location.pathname])
  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 後台路由：不套用 Navbar/Footer/ContentProvider */}
        <Route path="/admin/*" element={<AdminApp />} />

        {/* 前台路由：套用完整佈局 */}
        <Route path="/*" element={
          <ContentProvider>
            <CartProvider>
              <PageTracker />
              <ScrollToTop />
              <div className="min-h-screen flex flex-col text-gray-800 dark:bg-gray-950 dark:text-white">
                <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-warm-500 focus:text-white focus:rounded-lg">
                  跳到主要內容
                </a>
                <Navbar />
                <main id="main-content" className="flex-1">
                  <ErrorBoundary>
                  <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/product" element={<Product />} />
                    <Route path="/product/:id" element={<Product />} />
                    <Route path="/purchase" element={<Purchase />} />
                    <Route path="/purchase/result" element={<PurchaseResult />} />
                    <Route path="/team" element={<Team />} />
                    <Route path="/download" element={<Download />} />
                    <Route path="/project" element={<Project />} />
                    <Route path="/announcements" element={<Announcements />} />
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                  </ErrorBoundary>
                </main>
                <Footer />
                {/* 浮動購物車：所有前台頁面都顯示 */}
                <FloatingCart />
              </div>
            </CartProvider>
          </ContentProvider>
        } />
      </Routes>
    </BrowserRouter>
  )
}
