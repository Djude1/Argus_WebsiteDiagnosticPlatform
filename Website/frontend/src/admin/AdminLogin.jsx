import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { login, getMe } from './api'

export default function AdminLogin() {
  const [form, setForm]       = useState({ username: '', password: '' })
  const [error, setError]     = useState('')
  const [loading, setLoading] = useState(false)
  const navigate              = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await login(form.username, form.password)
      localStorage.setItem('admin_access',  res.data.access)
      localStorage.setItem('admin_refresh', res.data.refresh)

      // 確認角色是否有後台權限
      const me = await getMe()
      const role = me.data.role
      if (!me.data.is_superuser && !['superadmin', 'admin'].includes(role)) {
        localStorage.removeItem('admin_access')
        localStorage.removeItem('admin_refresh')
        setError('此帳號無後台管理權限')
        return
      }
      navigate('/admin')
    } catch (err) {
      if (err.response?.status === 401) {
        setError('帳號或密碼錯誤，請重新輸入')
      } else if (err.response?.status === 403) {
        setError('此帳號無後台管理權限')
      } else if (err.code === 'ECONNABORTED' || err.message?.includes('Network')) {
        setError('無法連線至伺服器，請確認後端服務是否正常運行')
      } else {
        setError('登入失敗，請稍後再試')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4 relative overflow-hidden">
      {/* 背景裝飾 — 動態漸層光暈 */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/8 rounded-full blur-3xl animate-[admin-bg-drift_12s_ease-in-out_infinite]" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-purple-500/8 rounded-full blur-3xl animate-[admin-bg-drift_15s_ease-in-out_infinite_reverse]" />
        <div className="absolute top-1/2 right-1/3 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl animate-[admin-bg-drift_18s_ease-in-out_infinite_2s]" />
      </div>

      {/* 動畫 keyframes 定義 */}
      <style>{`
@keyframes admin-bg-drift {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(30px, -20px) scale(1.05); }
  50% { transform: translate(-20px, 30px) scale(0.95); }
  75% { transform: translate(15px, 15px) scale(1.02); }
}
@keyframes admin-card-glow {
  0%, 100% { border-color: rgba(100, 116, 139, 0.3); box-shadow: 0 25px 50px -12px rgba(0,0,0,0.4); }
  50% { border-color: rgba(59, 130, 246, 0.2); box-shadow: 0 25px 50px -12px rgba(0,0,0,0.4), 0 0 20px rgba(59,130,246,0.06); }
}
@keyframes admin-btn-shimmer {
  0% { background-position: -200% center; }
  100% { background-position: 200% center; }
}
  .admin-card-glow {
    border-color: rgba(59, 130, 246, 0.2);
    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.4), 0 0 20px rgba(59,130,246,0.06);
  }
.admin-btn-loading {
  background-size: 200% auto;
  background-image: linear-gradient(90deg, #2563eb 0%, #60a5fa 25%, #2563eb 50%, #60a5fa 75%, #2563eb 100%);
  animation: admin-btn-shimmer 2s linear infinite;
}
      `}</style>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.4, 0.25, 1] }}
        className="w-full max-w-sm relative z-10"
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <motion.div
            initial={{ scale: 0.8 }}
            animate={{ scale: 1 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="inline-flex items-center gap-2 mb-2"
          >
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white font-bold shadow-lg shadow-blue-500/30">
              AI
            </div>
            <span className="text-white text-xl font-bold">管理後台</span>
          </motion.div>
          <p className="text-slate-400 text-sm">請登入以繼續</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-slate-800/80 backdrop-blur-sm rounded-2xl p-8 shadow-2xl border border-slate-700/50 admin-card-glow">
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm"
            >
              {error}
            </motion.div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-slate-300 mb-1.5">帳號</label>
            <input
              type="text"
              value={form.username}
              onChange={e => setForm(p => ({ ...p, username: e.target.value }))}
              className="w-full bg-slate-700/50 border border-slate-600 rounded-lg px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all"
              placeholder="輸入帳號"
              required
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-slate-300 mb-1.5">密碼</label>
            <input
              type="password"
              value={form.password}
              onChange={e => setForm(p => ({ ...p, password: e.target.value }))}
              className="w-full bg-slate-700/50 border border-slate-600 rounded-lg px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all"
              placeholder="輸入密碼"
              required
            />
          </div>

          <motion.button
            type="submit"
            disabled={loading}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            className={`w-full font-semibold py-2.5 rounded-lg transition-all shadow-lg shadow-blue-500/20 ${
              loading
                ? 'admin-btn-loading text-white/80 cursor-wait'
                : 'bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 disabled:opacity-50 text-white'
            }`}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                登入中...
              </span>
            ) : '登入'}
          </motion.button>
        </form>

        <p className="text-center text-slate-600 text-xs mt-6">
          AI 導航智慧眼鏡管理系統
        </p>
      </motion.div>
    </div>
  )
}
