/**
 * 前台公告列表頁
 * - 顯示所有已發布且允許網站顯示的公告
 * - 支援標籤篩選
 * - 響應式設計、玻璃擬態卡片、交錯動畫
 */
import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import apiClient from '../../api/client'
import ScrollReveal from '../../components/ScrollReveal'

// ── 類型設定 ────────────────────────────────────────────────────────────────
const TYPE_LABELS = {
  version_update: '版本更新',
  maintenance:    '系統維護',
  new_feature:    '新功能',
  general:        '一般通知',
}
const TYPE_COLORS = {
  version_update: { bg: 'bg-blue-500/20', text: 'text-blue-700 dark:text-blue-300', border: 'border-blue-500/30' },
  maintenance:    { bg: 'bg-yellow-500/20', text: 'text-yellow-700 dark:text-yellow-300', border: 'border-yellow-500/30' },
  new_feature:    { bg: 'bg-green-500/20', text: 'text-green-700 dark:text-green-300', border: 'border-green-500/30' },
  general:        { bg: 'bg-gray-500/20', text: 'text-gray-700 dark:text-gray-300', border: 'border-gray-500/30' },
}

// ── 類型圖示 ────────────────────────────────────────────────────────────────
function TypeIcon({ type }) {
  switch (type) {
    case 'version_update':
      return (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      )
    case 'maintenance':
      return (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      )
    case 'new_feature':
      return (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      )
    default:
      return (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
        </svg>
      )
  }
}

// ── 時間格式化 ──────────────────────────────────────────────────────────────
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')}`
}

function fmtDateTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

// ── 卡片動畫變體 ────────────────────────────────────────────────────────────
const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: 'easeOut' },
  }),
}

// ── 主元件 ──────────────────────────────────────────────────────────────────
export default function Announcements() {
  const [announcements, setAnnouncements] = useState([])
  const [tags, setTags] = useState([])
  const [selectedTag, setSelectedTag] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)

  // ── 載入公告 ──────────────────────────────────────────────────────────────
  const loadAnnouncements = useCallback(async () => {
    setLoading(true)
    try {
      const params = selectedTag ? { tag: selectedTag } : {}
      const res = await apiClient.get('/content/website-announcements/', { params })
      const data = res.data
      const list = data.results || data
      setAnnouncements(list)

      // 從公告中提取所有標籤
      const allTags = new Map()
      list.forEach(item => {
        if (item.tags_detail) {
          item.tags_detail.forEach(tag => {
            allTags.set(tag.id, tag)
          })
        }
      })
      setTags(Array.from(allTags.values()))
    } catch {
      // 靜默失敗
    }
    setLoading(false)
  }, [selectedTag])

  useEffect(() => {
    loadAnnouncements()
  }, [loadAnnouncements])

  // ── 渲染 ──────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen">
      {/* ── Hero 區塊 ───────────────────────────────────────────── */}
      <div className="relative overflow-hidden">
        {/* 網狀漸層底層 */}
        <div className="absolute inset-0 pointer-events-none mesh-gradient" />

        {/* 動態光球裝飾 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-[10%] w-[400px] h-[400px] bg-warm-400/5 dark:bg-brand-600/10 rounded-full blur-[100px] animate-float" />
          <div className="absolute bottom-[10%] right-[15%] w-72 h-72 bg-warm-500/4 dark:bg-brand-500/8 rounded-full blur-[80px] animate-float-delayed" />
        </div>

        {/* 幾何裝飾 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="geo-diamond absolute top-[30%] right-[15%] opacity-40" />
          <div className="geo-ring absolute bottom-[20%] left-[8%] opacity-30" />
        </div>

        {/* 中央放射漸層 */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-warm-500/5 via-transparent to-transparent dark:from-brand-950/20 dark:via-transparent dark:to-transparent" />

        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-12">
          {/* 返回首頁 */}
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-gray-700 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white text-sm mb-8 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            返回首頁
          </Link>

          <div className="text-center">
            {/* 徽章 — 使用 glass 效果，與其他頁面一致 */}
            <div className="inline-flex items-center gap-2 glass rounded-full px-4 py-2 text-sm text-warm-600 dark:text-brand-400 mb-6">
              <span className="w-2 h-2 bg-green-400 rounded-full" />
              最新消息
            </div>
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white mb-4">
              公告中心
            </h1>
            <p className="text-gray-700 dark:text-gray-400 text-lg max-w-2xl mx-auto">
              查看產品更新、系統維護通知與最新功能公告
            </p>
          </div>
        </div>
      </div>

      {/* ── 主要內容區 ───────────────────────────────────────────── */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        {/* 標籤篩選 */}
        {tags.length > 0 && (
          <div className="mb-8 flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-700 dark:text-gray-400 mr-2">篩選：</span>
            <button
              onClick={() => setSelectedTag(null)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                selectedTag === null
                  ? 'bg-gradient-to-r from-warm-600 to-warm-500 dark:from-brand-600 dark:to-brand-500 text-white shadow-md'
                  : 'glass text-gray-700 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              全部
            </button>
            {tags.map(tag => (
              <button
                key={tag.id}
                onClick={() => setSelectedTag(tag.slug)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                  selectedTag === tag.slug
                    ? 'text-white shadow-md ring-2 ring-offset-2 ring-offset-white dark:ring-offset-gray-900'
                    : 'glass text-gray-700 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
                style={{
                  backgroundColor: selectedTag === tag.slug
                    ? (tag.color || '#6366f1')
                    : undefined,
                }}
              >
                {tag.name}
              </button>
            ))}
          </div>
        )}

        {/* 載入中 */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-warm-500 dark:border-brand-500" />
          </div>
        ) : announcements.length === 0 ? (
          <div className="text-center py-20">
            <svg className="w-16 h-16 text-gray-400 dark:text-gray-700 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
            </svg>
            <p className="text-gray-700 dark:text-gray-400 text-lg">目前沒有公告</p>
            <p className="text-gray-700 dark:text-gray-400 text-sm mt-2">請稍後再查看最新消息</p>
          </div>
        ) : (
          <div className="space-y-5">
            {announcements.map((item, index) => {
              const typeStyle = TYPE_COLORS[item.type] || TYPE_COLORS.general
              const isExpanded = expandedId === item.id

              return (
                <ScrollReveal key={item.id} delay={index * 0.05} direction="up">
                  <motion.article
                    custom={index}
                    variants={cardVariants}
                    initial="hidden"
                    animate="visible"
                    whileHover={{ y: -2 }}
                    transition={{ duration: 0.2 }}
                    className={`accent-left-line glass gradient-top-border rounded-2xl overflow-hidden transition-all duration-300 ${
                      isExpanded ? 'glow-border' : 'hover:glow-border'
                    }`}
                    data-type={item.type}
                  >
                    {/* 卡片標頭 */}
                    <div
                      className="p-5 sm:p-6 cursor-pointer"
                      onClick={() => setExpandedId(isExpanded ? null : item.id)}
                    >
                      <div className="flex items-start gap-4">
                        {/* 類型徽章 + 圖示 */}
                        <div className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg ${typeStyle.bg} ${typeStyle.text} border ${typeStyle.border}`}>
                          <TypeIcon type={item.type} />
                          <span className="text-xs font-medium">
                            {TYPE_LABELS[item.type] || '公告'}
                          </span>
                        </div>

                        <div className="flex-1 min-w-0">
                          {/* 標題 */}
                          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2 leading-tight">
                            {item.title}
                          </h2>

                          {/* 標籤 */}
                          {item.tags_detail && item.tags_detail.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mb-2">
                              {item.tags_detail.map(tag => (
                                <span
                                  key={tag.id}
                                  className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                                  style={{
                                    backgroundColor: `${tag.color || '#6366f1'}20`,
                                    color: tag.color || '#6366f1',
                                  }}
                                >
                                  #{tag.name}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* 發布時間 */}
                          <div className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-400">
                            <span className="flex items-center gap-1">
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                  d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                              </svg>
                              {fmtTime(item.created_at)}
                            </span>
                          </div>
                        </div>

                        {/* 展開指示 — 平滑旋轉動畫 */}
                        <div className="flex-shrink-0">
                          <motion.svg
                            animate={{ rotate: isExpanded ? 180 : 0 }}
                            transition={{ duration: 0.2 }}
                            className="w-5 h-5 text-gray-700 dark:text-gray-400"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </motion.svg>
                        </div>
                      </div>
                    </div>

                    {/* 展開內容 */}
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          key={item.id}
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.25, ease: 'easeInOut' }}
                          style={{ overflow: 'hidden' }}
                        >
                          <div className="px-5 sm:px-6 pb-5 sm:pb-6 border-t border-gray-200 dark:border-gray-800">
                            <div className="pt-4 text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                              {item.body}
                            </div>

                            {item.scheduled_at && (
                              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-800">
                                <p className="text-xs text-gray-700 dark:text-gray-400">
                                  排程發布時間：{fmtDateTime(item.scheduled_at)}
                                </p>
                              </div>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.article>
                </ScrollReveal>
              )
            })}
          </div>
        )}

        {/* 底部提示 */}
        {!loading && announcements.length > 0 && (
          <div className="mt-12 text-center">
            <div className="section-divider max-w-xs mx-auto mb-4" />
            <p className="text-gray-700 dark:text-gray-400 text-sm">
              已顯示全部 {announcements.length} 則公告
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
