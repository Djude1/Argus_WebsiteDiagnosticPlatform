import { Link } from 'react-router-dom'
import { useContent } from '../../context/ContentContext'

export default function Footer() {
  const { site } = useContent()

  const quickLinks = [
    { to: '/', label: site.nav_home || '首頁' },
    { to: '/product', label: site.nav_product || '產品介紹' },
    { to: '/purchase', label: site.nav_purchase || '立即購買' },
    { to: '/team', label: site.nav_team || '關於團隊' },
  ]

  return (
    <footer aria-label="頁尾" className="border-t border-gray-200 dark:border-white/10 mt-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* 品牌資訊 */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-warm-500 to-warm-700 dark:from-brand-500 dark:to-brand-700 flex items-center justify-center text-white font-bold text-sm">
                {site.brand_short || 'AI'}
              </div>
              <span className="font-bold text-lg">{site.brand_name || '智慧眼鏡'}</span>
            </div>
            <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed">
              {site.brand_description || '結合 OpenAI GPT 語音助理與 AR 導航技術的次世代智慧穿戴裝置。基於開源專案 OpenAIglasses_for_Navigation 進行開發。'}
            </p>
          </div>

          {/* 快速連結 */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
              {site.footer_quick_links_title || '快速連結'}
            </h3>
            <ul className="space-y-2">
              {quickLinks.map((link) => (
                <li key={link.to}>
                  <Link
                    to={link.to}
                    className="text-gray-700 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 text-sm transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* 原始碼連結 */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
              {site.footer_opensource_title || '開源資源'}
            </h3>
            <ul className="space-y-2">
              <li>
                <a
                  href={site.footer_opensource_url || 'https://github.com/AI-FanGe/OpenAIglasses_for_Navigation'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-700 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 text-sm transition-colors"
                >
                  {site.footer_opensource_text || '原始開源專案'}
                </a>
              </li>
              <li>
                <a
                  href="/admin/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-700 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 text-sm transition-colors"
                >
                  {site.nav_admin || '後台管理'}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="border-t border-gray-200 dark:border-white/10 mt-8 pt-8 text-center text-gray-700 dark:text-gray-400 text-sm">
          <p>&copy; {site.footer_copyright || '2025 AI 導航智慧眼鏡專題。基於 OpenAIglasses_for_Navigation 開源專案。'}</p>
        </div>
      </div>
    </footer>
  )
}
