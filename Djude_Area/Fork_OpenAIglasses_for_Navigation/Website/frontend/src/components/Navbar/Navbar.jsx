import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useContent } from '../../context/ContentContext'

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false)
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const { site } = useContent()

  const navLinks = [
    { to: '/', label: site.nav_home || '首頁' },
    { to: '/product', label: site.nav_product || '產品介紹' },
    { to: '/project', label: site.nav_project || '專案介紹' },
    { to: '/download', label: site.nav_download || 'APP 下載' },
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
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled ? 'glass shadow-lg shadow-black/20' : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* 品牌 Logo */}
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-bold text-sm">
              {site.brand_short || 'AI'}
            </div>
            <span className="font-bold text-lg text-white group-hover:text-brand-400 transition-colors">
              {site.brand_name || '智慧眼鏡'}
            </span>
          </Link>

          {/* 桌面版選單 */}
          <div className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  pathname === link.to
                    ? 'text-brand-400 bg-brand-500/10'
                    : 'text-gray-300 hover:text-white hover:bg-white/5'
                }`}
              >
                {link.label}
              </Link>
            ))}
            <a
              href="/admin/"
              target="_blank"
              rel="noopener noreferrer"
              className="ml-4 btn-outline text-sm py-2 px-4"
            >
              {site.nav_admin || '後台管理'}
            </a>
          </div>

          {/* 手機版漢堡選單按鈕 */}
          <button
            className="md:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label="開啟選單"
          >
            <div className="w-5 h-4 flex flex-col justify-between">
              <span className={`block h-0.5 bg-current transition-all duration-300 ${isMenuOpen ? 'rotate-45 translate-y-1.5' : ''}`} />
              <span className={`block h-0.5 bg-current transition-all duration-300 ${isMenuOpen ? 'opacity-0' : ''}`} />
              <span className={`block h-0.5 bg-current transition-all duration-300 ${isMenuOpen ? '-rotate-45 -translate-y-2' : ''}`} />
            </div>
          </button>
        </div>
      </div>

      {/* 手機版下拉選單 */}
      {isMenuOpen && (
        <div className="md:hidden glass border-t border-white/10">
          <div className="px-4 py-3 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`block px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                  pathname === link.to
                    ? 'text-brand-400 bg-brand-500/10'
                    : 'text-gray-300 hover:text-white hover:bg-white/5'
                }`}
              >
                {link.label}
              </Link>
            ))}
            <a
              href="/admin/"
              target="_blank"
              rel="noopener noreferrer"
              className="block px-4 py-3 rounded-lg text-sm font-medium text-brand-400 hover:bg-brand-500/10 transition-all"
            >
              {site.nav_admin || '後台管理'}
            </a>
          </div>
        </div>
      )}
    </nav>
  )
}
