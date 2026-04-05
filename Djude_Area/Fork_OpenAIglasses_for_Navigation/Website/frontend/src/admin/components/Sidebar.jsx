/**
 * 後台側邊欄導覽（重構版）
 * - 分組導覽（網站管理、監控與日誌）
 * - 各分組可展開/收合
 * - 側邊欄可完全收縮
 * - 狀態持久化至 localStorage
 */
import { useState, useEffect } from 'react'

// 分組結構設定
const APP_GROUPS = {
  website: {
    label: '網站管理',
    defaultExpanded: true,
    items: [
      {
        id: 'dashboard',
        label: '流量追蹤',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      },
      {
        id: 'page-content',
        label: '頁面內容管理',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        id: 'products',
        label: '商品管理',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
          </svg>
        ),
      },
      {
        id: 'orders',
        label: '訂單管理',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        ),
      },
      {
        id: 'team',
        label: '成員管理',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        ),
      },
      {
        id: 'accounts',
        label: '帳號管理',
        superadminOnly: true,
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        ),
      },
      {
        id: 'announcements',
        label: '公告管理',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
          </svg>
        ),
      },
      {
        id: 'server-config',
        label: 'APP 伺服器設定',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
          </svg>
        ),
      },
    ],
  },
  monitoring: {
    label: '監控與日誌',
    defaultExpanded: false,
    items: [
      {
        id: 'logs',
        label: '操作日誌',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
        ),
      },
      {
        id: 'devices',
        label: '裝置監控',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        id: 'feedback',
        label: '撞擊回饋',
        icon: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        ),
      },
    ],
  },
}

// 使用者後台區塊（維持原有結構）
const USER_CATEGORIES = [
  {
    id: 'app-device',
    label: 'APP 裝置管理',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    id: 'voice',
    label: '語音偵測中控台',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 3a4 4 0 014 4v4a4 4 0 01-8 0V7a4 4 0 014-4z" />
      </svg>
    ),
  },
  {
    id: 'announcements',
    label: 'APP 公告管理',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
      </svg>
    ),
  },
]

export default function Sidebar({ active, onSelect, onLogout, userRole, userPermissions, mode }) {
  const isSuperAdmin = userRole === 'superadmin'

  // 側邊欄收縮狀態（持久化）
  const [isCollapsed, setIsCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('sidebar-collapsed') === 'true'
    }
    return false
  })

  // 分組展開狀態（持久化）
  const [expandedGroups, setExpandedGroups] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('sidebar-expanded-groups')
      if (saved) {
        try { return JSON.parse(saved) } catch { /* 忽略解析錯誤 */ }
      }
    }
    const defaults = {}
    Object.entries(APP_GROUPS).forEach(([key, group]) => {
      defaults[key] = group.defaultExpanded
    })
    return defaults
  })

  useEffect(() => {
    localStorage.setItem('sidebar-collapsed', String(isCollapsed))
  }, [isCollapsed])

  useEffect(() => {
    localStorage.setItem('sidebar-expanded-groups', JSON.stringify(expandedGroups))
  }, [expandedGroups])

  const toggleGroup = (groupKey) => {
    setExpandedGroups(prev => ({ ...prev, [groupKey]: !prev[groupKey] }))
  }

  const filterItems = (items) => {
    return items.filter((item) => {
      if (item.superadminOnly) return isSuperAdmin
      if (!isSuperAdmin && userRole === 'admin') {
        return Array.isArray(userPermissions) && userPermissions.includes(item.id)
      }
      return true
    })
  }

  // 使用者模式：維持原有扁平列表
  if (mode === 'user') {
    const visibleCategories = filterItems(USER_CATEGORIES)

    return (
      <aside className={`${isCollapsed ? 'w-16' : 'w-64'} bg-gradient-to-b from-slate-900 to-slate-800 flex flex-col h-full flex-shrink-0 shadow-2xl transition-all duration-300 relative`}>
        <button
          onClick={() => setIsCollapsed(prev => !prev)}
          className="absolute top-3 right-0 translate-x-1/2 w-6 h-6 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center text-slate-400 hover:text-white transition-colors z-10"
          title={isCollapsed ? '展開側邊欄' : '收縮側邊欄'}
        >
          <svg className={`w-4 h-4 transition-transform ${isCollapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <div className={`flex items-center gap-3 px-3 py-5 border-b border-slate-700/50 ${isCollapsed ? 'justify-center' : ''}`}>
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-green-400 to-green-600 flex items-center justify-center text-white font-extrabold text-sm flex-shrink-0 shadow-lg">
            AI
          </div>
          {!isCollapsed && (
            <div className="min-w-0">
              <div className="text-white font-bold text-sm leading-tight truncate">智慧眼鏡後台</div>
              <div className="text-xs mt-0.5 font-medium text-green-400">▶ 使用者後台</div>
            </div>
          )}
        </div>

        <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
          {visibleCategories.map((cat) => {
            const isActive = active === cat.id
            return (
              <button
                key={cat.id}
                onClick={() => onSelect(cat.id)}
                title={isCollapsed ? cat.label : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 text-left group ${
                  isCollapsed ? 'justify-center' : ''
                } ${
                  isActive
                    ? 'bg-green-600/90 text-white shadow-lg shadow-green-900/30'
                    : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-100'
                }`}
              >
                <span className={`flex-shrink-0 transition-colors ${isActive ? 'text-green-100' : 'text-slate-500 group-hover:text-slate-300'}`}>
                  {cat.icon}
                </span>
                {!isCollapsed && <span className="truncate">{cat.label}</span>}
              </button>
            )
          })}
        </nav>

        {!isCollapsed && (
          <div className="px-3 py-4 space-y-1 border-t border-slate-700/50">
            <a
              href="/"
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-400 hover:bg-slate-700/50 hover:text-slate-100 transition-all"
            >
              <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              前台網站
            </a>
            <button
              onClick={onLogout}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-400 hover:bg-red-900/30 hover:text-red-400 transition-all"
            >
              <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                  d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              登出
            </button>
          </div>
        )}
      </aside>
    )
  }

  // 網站管理模式：分組導覽
  return (
    <aside className={`${isCollapsed ? 'w-16' : 'w-64'} bg-gradient-to-b from-slate-900 to-slate-800 flex flex-col h-full flex-shrink-0 shadow-2xl transition-all duration-300 relative`}>
      <button
        onClick={() => setIsCollapsed(prev => !prev)}
        className="absolute top-3 right-0 translate-x-1/2 w-6 h-6 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center text-slate-400 hover:text-white transition-colors z-10"
        title={isCollapsed ? '展開側邊欄' : '收縮側邊欄'}
      >
        <svg className={`w-4 h-4 transition-transform ${isCollapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      <div className={`flex items-center gap-3 px-3 py-5 border-b border-slate-700/50 ${isCollapsed ? 'justify-center' : ''}`}>
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-white font-extrabold text-sm flex-shrink-0 shadow-lg">
          AI
        </div>
        {!isCollapsed && (
          <div className="min-w-0">
            <div className="text-white font-bold text-sm leading-tight truncate">智慧眼鏡後台</div>
            <div className="text-xs mt-0.5 font-medium text-blue-400">▶ 網站管理</div>
          </div>
        )}
      </div>

      {!isCollapsed && (
        <div className="mx-3 mt-3 mb-1 px-3 py-2 rounded-lg bg-slate-700/40 border border-slate-600/30 flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-400 to-purple-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {userRole === 'superadmin' ? '★' : '◆'}
          </div>
          <div className="min-w-0">
            <div className={`text-xs font-semibold truncate ${userRole === 'superadmin' ? 'text-amber-300' : 'text-blue-300'}`}>
              {userRole === 'superadmin' ? '超級管理員' : '一般管理員'}
            </div>
          </div>
        </div>
      )}

      <nav className="flex-1 px-2 py-3 overflow-y-auto">
        {Object.entries(APP_GROUPS).map(([groupKey, group]) => {
          const filteredItems = filterItems(group.items)
          if (filteredItems.length === 0) return null

          const isExpanded = expandedGroups[groupKey]
          const hasActiveItem = filteredItems.some((item) => item.id === active)

          return (
            <div key={groupKey} className="mb-2">
              <button
                onClick={() => toggleGroup(groupKey)}
                title={isCollapsed ? group.label : undefined}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors ${
                  isCollapsed ? 'justify-center' : ''
                } ${
                  hasActiveItem
                    ? 'text-blue-300 bg-blue-900/20'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/30'
                }`}
              >
                <svg
                  className={`w-3 h-3 flex-shrink-0 transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''} ${isCollapsed ? 'hidden' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                {!isCollapsed && <span className="truncate">{group.label}</span>}
              </button>

              {isExpanded && !isCollapsed && (
                <div className="mt-1 space-y-0.5">
                  {filteredItems.map((item) => {
                    const isActive = active === item.id
                    return (
                      <button
                        key={item.id}
                        onClick={() => onSelect(item.id)}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 text-left group ${
                          isActive
                            ? 'bg-blue-600/90 text-white shadow-lg shadow-blue-900/30'
                            : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-100'
                        }`}
                      >
                        <span className={`flex-shrink-0 transition-colors ${isActive ? 'text-blue-100' : 'text-slate-500 group-hover:text-slate-300'}`}>
                          {item.icon}
                        </span>
                        <span className="truncate">{item.label}</span>
                        {item.superadminOnly && (
                          <span className="ml-auto text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded-full flex-shrink-0">管</span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}

              {isCollapsed && (
                <div className="mt-1 space-y-0.5">
                  {filteredItems.map((item) => {
                    const isActive = active === item.id
                    return (
                      <button
                        key={item.id}
                        onClick={() => onSelect(item.id)}
                        title={item.label}
                        className={`w-full flex items-center justify-center px-2 py-2.5 rounded-xl transition-all duration-150 group ${
                          isActive
                            ? 'bg-blue-600/90 text-white shadow-lg shadow-blue-900/30'
                            : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-100'
                        }`}
                      >
                        <span className={`flex-shrink-0 transition-colors ${isActive ? 'text-blue-100' : 'text-slate-500 group-hover:text-slate-300'}`}>
                          {item.icon}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      {!isCollapsed && (
        <div className="px-3 py-4 space-y-1 border-t border-slate-700/50">
          <a
            href="/"
            target="_blank"
            rel="noopener noreferrer"
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-400 hover:bg-slate-700/50 hover:text-slate-100 transition-all"
          >
            <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            前台網站
          </a>
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-400 hover:bg-red-900/30 hover:text-red-400 transition-all"
          >
            <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            登出
          </button>
        </div>
      )}
    </aside>
  )
}
