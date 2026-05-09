import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useContent } from '../../context/ContentContext'
import { useTheme } from '../../context/ThemeContext'

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false)
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const { site } = useContent()
  const { isDark, toggleTheme } = useTheme()

  const navLinks = [
    { to: '/', label: site.nav_home || '首頁' },
    { to: '/product', label: site.nav_product || '產品介紹' },
    { to: '/project', label: site.nav_project || '專案介紹' },
    { to: '/download', label: site.nav_download || 'APP 下載' },
    { to: '/announcements', label: '公告中心' },
    { to: '/purchase', label: site.nav_purchase || '立即購買' },
    { to: '/team', label: site.nav_team || '關於團隊' },
  ]

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // 換頁時關閉選單
  useEffect(() => {
    setIsMenuOpen(false)
  }, [pathname])

  return (
    <nav
      aria-label="主導航"
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled
          ? 'glass backdrop-blur-xl shadow-lg shadow-gray-300/20 dark:shadow-black/20'
          : 'bg-white/95 dark:bg-transparent backdrop-blur-md'
      } border-b border-gray-300 dark:border-white/10`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* 品牌 Logo */}
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-warm-500 to-warm-700 dark:from-brand-500 dark:to-brand-700 flex items-center justify-center text-white font-bold text-sm">
              {site.brand_short || 'AI'}
            </div>
            <span className="font-bold text-lg text-gray-900 dark:text-white group-hover:text-warm-600 dark:group-hover:text-brand-400 transition-colors">
              {site.brand_name || '智慧眼鏡'}
            </span>
          </Link>

          {/* 桌面版選單 */}
          <div className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => {
              // 精確匹配首頁，其餘用 startsWith 支援巢狀路由
              const isActive = link.to === '/'
                ? pathname === '/'
                : pathname === link.to || pathname.startsWith(link.to + '/')
              return (
              <Link
                key={link.to}
                to={link.to}
                className={`relative px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'text-warm-600 dark:text-brand-400 bg-warm-500/10 dark:bg-brand-500/10'
                    : 'text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5'
                }`}
              >
                {link.label}
                {/* 活躍連結底部指示線 */}
                {isActive && (
                  <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-warm-500 dark:bg-brand-500" />
                )}
              </Link>
              )
            })}
            {/* 主題切換按鈕 */}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg text-gray-600 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 hover:bg-gray-100 dark:hover:bg-white/5 transition-all"
              aria-label={isDark ? '切換到日間模式' : '切換到夜間模式'}
              title={isDark ? '日間模式' : '夜間模式'}
            >
              {isDark ? (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>
            <a
              href="/admin/"
              target="_blank"
              rel="noopener noreferrer"
              className="ml-4 btn-outline text-sm py-2 px-4"
            >
              {site.nav_admin || '後台管理'}
            </a>
          </div>

          {/* 手機版：主題切換 + 漢堡選單按鈕 */}
          <div className="flex items-center gap-1 md:hidden">
            {/* 主題切換按鈕（手機版）*/}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg text-gray-600 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 hover:bg-gray-100 dark:hover:bg-white/5 transition-all"
              aria-label={isDark ? '切換到日間模式' : '切換到夜間模式'}
              title={isDark ? '日間模式' : '夜間模式'}
            >
              {isDark ? (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>
            <button
              className="p-2 rounded-lg text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              aria-label={isMenuOpen ? '關閉選單' : '開啟選單'}
            >
            <div className="w-5 h-4 flex flex-col justify-between">
              <span className={`block h-0.5 bg-current transition-all duration-300 ${isMenuOpen ? 'rotate-45 translate-y-1.5' : ''}`} />
              <span className={`block h-0.5 bg-current transition-all duration-300 ${isMenuOpen ? 'opacity-0' : ''}`} />
              <span className={`block h-0.5 bg-current transition-all duration-300 ${isMenuOpen ? '-rotate-45 -translate-y-2' : ''}`} />
            </div>
          </button>
          </div>
        </div>
      </div>

      {/* 手機版下拉選單（動畫） */}
      <AnimatePresence mode="wait">
        {isMenuOpen && (
          <motion.div
            key="mobile-menu"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            style={{ overflow: 'hidden' }}
            className="md:hidden glass border-t border-gray-200 dark:border-white/10"
          >
            <div className="px-4 py-3 space-y-1">
              {navLinks.map((link) => {
                const isActive = link.to === '/'
                  ? pathname === '/'
                  : pathname === link.to || pathname.startsWith(link.to + '/')
                return (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`block px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'text-warm-600 dark:text-brand-400 bg-warm-500/10 dark:bg-brand-500/10 border-l-2 border-warm-500 dark:border-brand-500'
                      : 'text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5'
                  }`}
                >
                  {link.label}
                </Link>
                )
              })}
              <a
                href="/admin/"
                target="_blank"
                rel="noopener noreferrer"
                className="block px-4 py-3 rounded-lg text-sm font-medium text-warm-600 dark:text-brand-400 hover:bg-warm-500/10 dark:hover:bg-brand-500/10 transition-all"
              >
                {site.nav_admin || '後台管理'}
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  )
}
