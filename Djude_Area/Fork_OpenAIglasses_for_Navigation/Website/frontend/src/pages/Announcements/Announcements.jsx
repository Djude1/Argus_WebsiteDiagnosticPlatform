/**
 * 前台公告列表頁
 * - 顯示所有已發布且允許網站顯示的公告
 * - 支援標籤篩選
 * - 響應式設計
 */
import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'

// ── 類型設定 ────────────────────────────────────────────────────────────────
const TYPE_LABELS = {
  version_update: '版本更新',
  maintenance:    '系統維護',
  new_feature:    '新功能',
  general:        '一般通知',
}
const TYPE_COLORS = {
  version_update: { bg: 'bg-blue-500/20', text: 'text-blue-300', border: 'border-blue-500/30' },
  maintenance:    { bg: 'bg-yellow-500/20', text: 'text-yellow-300', border: 'border-yellow-500/30' },
  new_feature:    { bg: 'bg-green-500/20', text: 'text-green-300', border: 'border-green-500/30' },
  general:        { bg: 'bg-gray-500/20', text: 'text-gray-300', border: 'border-gray-500/30' },
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
      const params = selectedTag ? `?tag=${selectedTag}` : ''
      const res = await fetch(`/api/content/website-announcements/${params}`)
      if (res.ok) {
        const data = await res.json()
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
      }
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
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950">
      {/* ── Hero 區塊 ───────────────────────────────────────────── */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-600/10 to-purple-600/10" />
        <div className="absolute inset-0">
          <div className="absolute top-20 left-10 w-72 h-72 bg-blue-500/20 rounded-full blur-3xl" />
          <div className="absolute bottom-10 right-10 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-12">
          {/* 返回首頁 */}
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-gray-400 hover:text-white text-sm mb-8 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            返回首頁
          </Link>

          <div className="text-center">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500/20 rounded-full text-blue-300 text-sm font-medium mb-4">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
              </svg>
              最新消息
            </div>
            <h1 className="text-3xl sm:text-4xl font-bold text-white mb-4">
              公告中心
            </h1>
            <p className="text-gray-400 text-lg max-w-2xl mx-auto">
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
            <span className="text-sm text-gray-500 mr-2">篩選：</span>
            <button
              onClick={() => setSelectedTag(null)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                selectedTag === null
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
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
                    ? 'text-white ring-2 ring-offset-2 ring-offset-gray-900'
                    : 'text-gray-400 hover:text-white'
                }`}
                style={{
                  backgroundColor: selectedTag === tag.slug
                    ? (tag.color || '#6366f1')
                    : `${tag.color || '#6366f1'}20`,
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
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
          </div>
        ) : announcements.length === 0 ? (
          <div className="text-center py-20">
            <svg className="w-16 h-16 text-gray-700 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
            </svg>
            <p className="text-gray-500 text-lg">目前沒有公告</p>
            <p className="text-gray-600 text-sm mt-2">請稍後再查看最新消息</p>
          </div>
        ) : (
          <div className="space-y-4">
            {announcements.map(item => {
              const typeStyle = TYPE_COLORS[item.type] || TYPE_COLORS.general
              const isExpanded = expandedId === item.id

              return (
                <article
                  key={item.id}
                  className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-2xl overflow-hidden hover:border-gray-700 transition-colors"
                >
                  {/* 卡片標頭 */}
                  <div
                    className="p-5 cursor-pointer"
                    onClick={() => setExpandedId(isExpanded ? null : item.id)}
                  >
                    <div className="flex items-start gap-4">
                      {/* 類型徽章 */}
                      <div className={`flex-shrink-0 px-3 py-1.5 rounded-lg ${typeStyle.bg} ${typeStyle.text} border ${typeStyle.border}`}>
                        <span className="text-xs font-medium">
                          {TYPE_LABELS[item.type] || '公告'}
                        </span>
                      </div>

                      <div className="flex-1 min-w-0">
                        {/* 標題 */}
                        <h2 className="text-lg font-semibold text-white mb-2 leading-tight">
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
                        <div className="flex items-center gap-3 text-sm text-gray-500">
                          <span className="flex items-center gap-1">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            {fmtTime(item.created_at)}
                          </span>
                        </div>
                      </div>

                      {/* 展開指示 */}
                      <div className="flex-shrink-0">
                        <svg
                          className={`w-5 h-5 text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </div>
                  </div>

                  {/* 展開內容 */}
                  {isExpanded && (
                    <div className="px-5 pb-5 border-t border-gray-800">
                      <div className="pt-4 text-gray-300 leading-relaxed whitespace-pre-wrap">
                        {item.body}
                      </div>

                      {item.scheduled_at && (
                        <div className="mt-4 pt-4 border-t border-gray-800">
                          <p className="text-xs text-gray-500">
                            排程發布時間：{fmtDateTime(item.scheduled_at)}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}

        {/* 底部提示 */}
        {!loading && announcements.length > 0 && (
          <div className="mt-12 text-center">
            <p className="text-gray-600 text-sm">
              已顯示全部 {announcements.length} 則公告
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
