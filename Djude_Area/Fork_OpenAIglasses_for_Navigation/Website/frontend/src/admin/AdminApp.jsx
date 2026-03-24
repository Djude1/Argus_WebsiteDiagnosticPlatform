import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import AdminLogin from './AdminLogin'
import Sidebar from './components/Sidebar'
import Dashboard from './sections/Dashboard'
import PageContent from './sections/PageContent'
import Products from './sections/Products'
import Orders from './sections/Orders'
import TeamMembers from './sections/TeamMembers'
import Accounts from './sections/Accounts'
import ActivityLogs from './sections/ActivityLogs'
import AppDevice from './sections/AppDevice'
import VoiceDetection from './sections/VoiceDetection'
import Announcements from './sections/Announcements'
import { getMe } from './api'

// ── 保護路由：未登入導向 login ────────────────────────────────────
function RequireAuth({ children }) {
  const token = localStorage.getItem('admin_access')
  const location = useLocation()
  if (!token) return <Navigate to="/admin/login" state={{ from: location }} replace />
  return children
}

// ── 後台 / 使用者後台 切換按鈕 ────────────────────────────────────
function ModeToggle({ mode, onChange }) {
  const isUser = mode === 'user'
  return (
    <button
      onClick={() => onChange(isUser ? 'website' : 'user')}
      className={`relative inline-flex items-center h-8 rounded-full px-1 w-36 transition-all duration-300 focus:outline-none shadow-inner ${
        isUser
          ? 'bg-green-500'
          : 'bg-slate-600'
      }`}
      title={isUser ? '切換至網站後台' : '切換至使用者後台'}
    >
      {/* 滑動圓球 */}
      <span className={`absolute w-6 h-6 bg-white rounded-full shadow-md transition-all duration-300 ${
        isUser ? 'left-[calc(100%-28px)]' : 'left-1'
      }`} />
      {/* 文字標籤 */}
      <span className={`w-full text-center text-xs font-semibold text-white transition-all duration-200 ${
        isUser ? 'pr-5' : 'pl-5'
      }`}>
        {isUser ? '使用者後台' : '網站後台'}
      </span>
    </button>
  )
}

// ── 主後台介面（三欄佈局）────────────────────────────────────────
function AdminLayout() {
  const [activeCategory, setActiveCategory] = useState('dashboard')
  const [userRole, setUserRole]             = useState('')
  const [userPermissions, setUserPermissions] = useState([])
  const [username, setUsername]             = useState('')
  // mode: 'website' = 網站後台 | 'user' = 使用者後台
  const [mode, setMode]                     = useState('website')
  const navigate = useNavigate()

  // 取得目前登入者資料（角色 + 功能權限）
  useEffect(() => {
    getMe().then(r => {
      setUserRole(r.data.role || '')
      setUserPermissions(r.data.permissions || [])
      setUsername(r.data.username || '')
    }).catch(() => {})
  }, [])

  const SECTION_MAP = {
    'dashboard':    { label: '流量追蹤',     component: <Dashboard /> },
    'page-content': { label: '頁面內容管理', component: <PageContent /> },
    'products':     { label: '商品管理',     component: <Products /> },
    'orders':       { label: '訂單管理',     component: <Orders /> },
    'team':         { label: '成員管理',     component: <TeamMembers /> },
    'accounts':     { label: '帳號管理',     component: <Accounts currentUserRole={userRole} /> },
    'logs':         { label: '操作日誌',     component: <ActivityLogs /> },
    'app-device':     { label: 'APP 裝置管理',   component: <AppDevice /> },
    'voice':          { label: '語音偵測中控台', component: <VoiceDetection /> },
    'announcements':  { label: 'APP 公告管理',  component: <Announcements /> },
  }

  const handleLogout = () => {
    localStorage.removeItem('admin_access')
    localStorage.removeItem('admin_refresh')
    localStorage.removeItem('device_access')
    navigate('/admin/login')
  }

  const handleSelect = (id) => {
    // 帳號管理只有超級管理員可進入
    if (id === 'accounts' && userRole !== 'superadmin') return
    // 一般管理員需檢查 permissions（superadmin 跳過）
    if (userRole === 'admin' && !['accounts'].includes(id)) {
      if (!userPermissions.includes(id)) return
    }
    setActiveCategory(id)
  }

  // 切換模式時自動跳到對應的第一個可用 section
  const handleModeChange = (newMode) => {
    setMode(newMode)
    if (newMode === 'user') {
      // 保留目前的 user section，若不是 user section 才切換到預設
      const userSections = ['app-device', 'voice', 'announcements']
      if (!userSections.includes(activeCategory)) {
        setActiveCategory('app-device')
      }
    } else {
      const websiteSections = ['dashboard', 'page-content', 'products', 'orders', 'team', 'accounts', 'logs']
      if (!websiteSections.includes(activeCategory)) {
        setActiveCategory('dashboard')
      }
    }
  }

  const isSuperAdmin = userRole === 'superadmin'

  return (
    <div className="flex h-screen bg-slate-100 overflow-hidden font-sans">
      {/* 左欄：側欄導覽 */}
      <Sidebar
        active={activeCategory}
        onSelect={handleSelect}
        onLogout={handleLogout}
        userRole={userRole}
        userPermissions={userPermissions}
        mode={mode}
      />

      {/* 主內容區 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 頂部列 */}
        <header className="bg-white border-b border-gray-100 px-6 py-0 flex items-center flex-shrink-0 h-14">
          {/* 麵包屑 */}
          <div className="flex items-center gap-2 min-w-0">
            <svg className="w-4 h-4 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            <span className="text-xs text-gray-400">管理後台</span>
            <svg className="w-3 h-3 text-gray-300 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="text-sm font-semibold text-gray-700 truncate">
              {SECTION_MAP[activeCategory]?.label}
            </span>
          </div>

          {/* 右側工具列 */}
          <div className="ml-auto flex items-center gap-3">
            {/* 後台切換 Toggle */}
            <ModeToggle mode={mode} onChange={handleModeChange} />

            {/* 分隔線 */}
            <div className="w-px h-6 bg-gray-200" />

            {/* 使用者資訊 */}
            <div className="flex items-center gap-2.5">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold uppercase shadow-md ${
                isSuperAdmin ? 'bg-gradient-to-br from-amber-400 to-orange-500' : 'bg-gradient-to-br from-blue-500 to-blue-700'
              }`}>
                {username ? username.charAt(0) : '?'}
              </div>
              <div className="hidden sm:block">
                <div className="text-xs font-semibold text-gray-800 leading-tight">{username || '管理員'}</div>
                <div className={`text-xs leading-tight font-medium ${isSuperAdmin ? 'text-amber-500' : 'text-blue-500'}`}>
                  {isSuperAdmin ? '⭐ 超級管理員' : '◆ 一般管理員'}
                </div>
              </div>
            </div>
          </div>
        </header>

        {/* 內容主體 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {SECTION_MAP[activeCategory]?.component}
        </div>
      </div>
    </div>
  )
}

// ── 路由入口 ─────────────────────────────────────────────────────
export default function AdminApp() {
  return (
    <Routes>
      <Route path="login" element={<AdminLogin />} />
      <Route path="*" element={
        <RequireAuth>
          <AdminLayout />
        </RequireAuth>
      } />
    </Routes>
  )
}
