import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white font-bold">
              AI
            </div>
            <span className="text-white text-xl font-bold">管理後台</span>
          </div>
          <p className="text-slate-400 text-sm">請登入以繼續</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-slate-800 rounded-2xl p-8 shadow-2xl">
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-slate-300 mb-1.5">帳號</label>
            <input
              type="text"
              value={form.username}
              onChange={e => setForm(p => ({ ...p, username: e.target.value }))}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
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
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="輸入密碼"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg transition-colors"
          >
            {loading ? '登入中...' : '登入'}
          </button>
        </form>
      </div>
    </div>
  )
}
