import { useState, useEffect, useCallback } from 'react'
import { getUsers, createUser, updateUser, deleteUser } from '../api'
import Modal from '../components/Modal'

// ── ON / OFF 紅綠開關元件 ─────────────────────────────────────────
function ToggleSwitch({ value, onChange, disabled = false }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!value)}
      disabled={disabled}
      className={`relative inline-flex items-center h-8 rounded-full transition-all duration-300 focus:outline-none select-none ${
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
      } ${value ? 'bg-green-500' : 'bg-red-500'}`}
      style={{ width: '72px', boxShadow: 'inset 0 2px 6px rgba(0,0,0,0.25)' }}
    >
      {/* 滑動圓球 */}
      <span
        className="absolute w-6 h-6 bg-white rounded-full shadow-md transition-all duration-300"
        style={{ left: value ? 'calc(100% - 28px)' : '4px' }}
      />
      {/* 文字 */}
      <span
        className="w-full text-center text-xs font-bold text-white transition-all duration-200"
        style={{ paddingLeft: value ? 0 : '18px', paddingRight: value ? '18px' : 0 }}
      >
        {value ? 'ON' : 'OFF'}
      </span>
    </button>
  )
}

// ── 欄位元件 ─────────────────────────────────────────────────────
function Field({ label, value, onChange, type = 'text' }) {
  return (
    <div className="mb-3">
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{label}</label>
      <input
        type={type}
        value={value ?? ''}
        onChange={e => onChange(e.target.value)}
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400"
      />
    </div>
  )
}

// ── 常數 ─────────────────────────────────────────────────────────
const ROLE_LABELS = { superadmin: '超級管理員', admin: '一般管理員' }
const ROLE_COLORS = {
  superadmin: 'bg-red-100 text-red-700',
  admin:      'bg-blue-100 text-blue-700',
}

// 可授權給一般管理員的功能區塊（帳號管理永遠只有超級管理員）
const PERMISSION_OPTIONS = [
  { id: 'dashboard',    label: '流量追蹤' },
  { id: 'page-content', label: '頁面內容管理' },
  { id: 'products',     label: '商品管理' },
  { id: 'orders',       label: '訂單管理' },
  { id: 'team',         label: '成員管理' },
  { id: 'logs',         label: '操作日誌' },
  { id: 'app-device',   label: 'APP 裝置管理' },
]

const emptyUser = {
  username: '', email: '', first_name: '', last_name: '',
  role: 'admin', permissions: [], password: '', is_active: true,
}

/** 排序圖示元件 */
function SortIcon({ field, sortField, sortDir }) {
  if (sortField !== field) return <span className="text-gray-300 ml-0.5">↕</span>
  return sortDir === 'asc' ? <span className="text-blue-500 ml-0.5">↑</span> : <span className="text-blue-500 ml-0.5">↓</span>
}

// ── 主元件 ───────────────────────────────────────────────────────
export default function Accounts({ currentUserRole }) {
  const [users, setUsers]         = useState([])
  const [selected, setSelected]   = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [editForm, setEditForm]   = useState({})
  const [saving, setSaving]       = useState(false)
  const [saved, setSaved]         = useState(false)
  const [modal, setModal]         = useState(false)
  const [newForm, setNewForm]     = useState(emptyUser)
  const [newSaving, setNewSaving] = useState(false)
  const [sortField, setSortField] = useState('username')  // 排序欄位
  const [sortDir, setSortDir]     = useState('asc')       // asc 或 desc

  const isSuperAdmin = currentUserRole === 'superadmin'

  const load = useCallback(() =>
    getUsers().then(r => setUsers(r.data.results || r.data)), [])

  useEffect(() => { load() }, [load])

  const selectUser = (u) => {
    setSelected(u)
    setEditForm({ ...u, password: '', permissions: u.permissions || [] })
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    const payload = { ...editForm }
    if (!payload.password) delete payload.password
    try {
      const res = await updateUser(selected.id, payload)
      setSelected(res.data)
      setSaved(true)
      load()
    } catch (e) { alert('儲存失敗：' + JSON.stringify(e.response?.data)) }
    finally { setSaving(false) }
  }

  const handleDelete = async () => {
    if (!confirm(`確定刪除帳號「${selected.username}」？`)) return
    await deleteUser(selected.id)
    setSelected(null)
    load()
  }

  const handleCreate = async () => {
    setNewSaving(true)
    try {
      await createUser(newForm)
      setModal(false)
      setNewForm(emptyUser)
      load()
    } catch (e) { alert('建立失敗：' + JSON.stringify(e.response?.data)) }
    finally { setNewSaving(false) }
  }

  // 修改編輯表單欄位
  const set = (f, v) => { setEditForm(p => ({ ...p, [f]: v })); setSaved(false) }

  // 搜尋篩選：依帳號名稱或 Email
  const filteredUsers = users.filter(u => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return (
      (u.username && u.username.toLowerCase().includes(term)) ||
      (u.email && u.email.toLowerCase().includes(term))
    )
  })

  // 排序切換函式
  function toggleSort(field) {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  // 排序後的帳號列表
  const sortedUsers = [...filteredUsers].sort((a, b) => {
    const aVal = a[sortField] ?? ''
    const bVal = b[sortField] ?? ''
    const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal), 'zh-TW')
    return sortDir === 'asc' ? cmp : -cmp
  })

  // 切換功能權限開關
  const togglePermission = (id, isEdit) => {
    if (isEdit) {
      setEditForm(prev => {
        const perms = prev.permissions || []
        const next = perms.includes(id) ? perms.filter(p => p !== id) : [...perms, id]
        return { ...prev, permissions: next }
      })
      setSaved(false)
    } else {
      setNewForm(prev => {
        const perms = prev.permissions || []
        const next = perms.includes(id) ? perms.filter(p => p !== id) : [...perms, id]
        return { ...prev, permissions: next }
      })
    }
  }

  return (
    <div className="flex h-full">
      {/* 左欄：帳號列表 */}
      <div className="w-64 bg-white border-r border-gray-100 flex-shrink-0 flex flex-col">
        {/* 搜尋 */}
        <div className="px-4 py-2 border-b border-gray-100">
          <input
            type="text"
            placeholder="搜尋帳號或 Email..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400"
          />
        </div>
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">帳號管理</h3>
          {isSuperAdmin && (
            <button
              onClick={() => setModal(true)}
              className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-500"
            >
              + 新增
            </button>
          )}
        </div>
        {/* 排序控制 */}
        <div className="px-4 py-1.5 border-b border-gray-100 flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-400">排序：</span>
          {[
            { field: 'username', label: '帳號' },
            { field: 'email', label: 'Email' },
            { field: 'role', label: '角色' },
            { field: 'date_joined', label: '建立日期' },
          ].map(({ field, label }) => (
            <button key={field} onClick={() => toggleSort(field)}
              className="text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors flex items-center">
              {label}<SortIcon field={field} sortField={sortField} sortDir={sortDir} />
            </button>
          ))}
        </div>
        <div className="overflow-y-auto flex-1">
          {filteredUsers.length === 0 && users.length === 0 && (
            <div className="text-center text-gray-400 text-sm py-8">
              <div className="text-2xl mb-2">📭</div>
              <p>沒有帳號</p>
            </div>
          )}
          {filteredUsers.length === 0 && users.length > 0 && (
            <div className="text-center text-gray-400 text-sm py-8">
              <div className="text-2xl mb-2">🔍</div>
              <p>沒有符合的帳號</p>
            </div>
          )}
          {sortedUsers.map(u => (
            <button key={u.id} onClick={() => selectUser(u)}
              className={`w-full flex items-center gap-3 px-4 py-3 border-b border-gray-50 transition-colors text-left ${
                selected?.id === u.id ? 'bg-blue-50 border-r-2 border-blue-600' : 'hover:bg-gray-50'
              }`}
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-slate-500 to-slate-700 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 uppercase">
                {u.username.charAt(0)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-gray-800 truncate">{u.username}</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${ROLE_COLORS[u.role] || 'bg-gray-100 text-gray-600'}`}>
                    {ROLE_LABELS[u.role] || u.role}
                  </span>
                  {!u.is_active && <span className="text-xs text-red-500">停用</span>}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右欄：編輯區 */}
      <div className="flex-1 overflow-y-auto bg-white">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center"><div className="text-4xl mb-2">👤</div><p>請從左側選擇帳號</p></div>
          </div>
        ) : (
          <div className="max-w-xl mx-auto px-8 py-6">
            {/* 標題列 */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-slate-500 to-slate-700 flex items-center justify-center text-white text-xl font-bold uppercase">
                  {selected.username.charAt(0)}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-800">{selected.username}</h2>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${ROLE_COLORS[selected.role] || 'bg-gray-100 text-gray-600'}`}>
                    {ROLE_LABELS[selected.role] || selected.role}
                  </span>
                </div>
              </div>
              {isSuperAdmin && (
                <button onClick={handleDelete}
                  className="text-xs text-red-500 hover:text-red-700 px-3 py-1.5 border border-red-200 rounded-lg hover:bg-red-50">
                  刪除
                </button>
              )}
            </div>

            {/* 基本資料 */}
            <div className="grid grid-cols-2 gap-x-4">
              <Field label="帳號" value={editForm.username} onChange={v => set('username', v)} />
              <Field label="Email" value={editForm.email} onChange={v => set('email', v)} type="email" />
              <Field label="名字" value={editForm.first_name} onChange={v => set('first_name', v)} />
              <Field label="姓氏" value={editForm.last_name} onChange={v => set('last_name', v)} />
            </div>

            <div className="grid grid-cols-2 gap-x-4">
              {/* 角色選擇（僅超級管理員可改） */}
              <div className="mb-3">
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">角色</label>
                <select
                  value={editForm.role}
                  onChange={e => set('role', e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400 disabled:bg-gray-50 disabled:cursor-not-allowed"
                >
                  <option value="superadmin">超級管理員</option>
                  <option value="admin">一般管理員</option>
                </select>
              </div>

              {/* 帳號啟用 */}
              <div className="mb-3 flex items-end pb-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!editForm.is_active}
                    onChange={e => set('is_active', e.target.checked)}
                    disabled={!isSuperAdmin}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">帳號啟用中</span>
                </label>
              </div>
            </div>

            <Field label="新密碼（留空不更改）" value={editForm.password} onChange={v => set('password', v)} type="password" />

            {/* 功能權限開關（角色為 admin 時顯示，僅超級管理員可設定） */}
            {editForm.role === 'admin' && (
              <div className="mt-4 mb-4">
                <div className="flex items-center gap-2 mb-3">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">功能權限</h3>
                  {!isSuperAdmin && (
                    <span className="text-xs text-gray-400 italic">（僅超級管理員可修改）</span>
                  )}
                </div>
                <div className="bg-slate-50 rounded-xl p-4 space-y-3">
                  {PERMISSION_OPTIONS.map(opt => {
                    const enabled = (editForm.permissions || []).includes(opt.id)
                    return (
                      <div key={opt.id} className="flex items-center justify-between">
                        <span className="text-sm text-gray-700">{opt.label}</span>
                        <ToggleSwitch
                          value={enabled}
                          onChange={() => togglePermission(opt.id, true)}
                          disabled={!isSuperAdmin}
                        />
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 儲存按鈕（僅超級管理員） */}
            {isSuperAdmin && (
              <div className="flex items-center gap-3 pt-2 border-t border-gray-100 mt-2">
                <button onClick={handleSave} disabled={saving}
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
                  {saving ? '儲存中...' : '儲存變更'}
                </button>
                {saved && <span className="text-green-500 text-sm">✓ 已儲存</span>}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 新增帳號 Modal（僅超級管理員） */}
      {modal && (
        <Modal title="新增帳號" onClose={() => setModal(false)}>
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="帳號" value={newForm.username} onChange={v => setNewForm(p => ({ ...p, username: v }))} />
            <Field label="Email" value={newForm.email} onChange={v => setNewForm(p => ({ ...p, email: v }))} type="email" />
          </div>
          <Field label="密碼" value={newForm.password} onChange={v => setNewForm(p => ({ ...p, password: v }))} type="password" />

          {/* 角色下拉（文字已修正為黑色） */}
          <div className="mb-3">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">角色</label>
            <select
              value={newForm.role}
              onChange={e => setNewForm(p => ({ ...p, role: e.target.value, permissions: [] }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400"
            >
              <option value="superadmin">超級管理員</option>
              <option value="admin">一般管理員</option>
            </select>
          </div>

          {/* 新增帳號時設定功能權限 */}
          {newForm.role === 'admin' && (
            <div className="mb-4">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">功能權限</h3>
              <div className="bg-slate-50 rounded-xl p-4 space-y-3">
                {PERMISSION_OPTIONS.map(opt => {
                  const enabled = (newForm.permissions || []).includes(opt.id)
                  return (
                    <div key={opt.id} className="flex items-center justify-between">
                      <span className="text-sm text-gray-700">{opt.label}</span>
                      <ToggleSwitch
                        value={enabled}
                        onChange={() => togglePermission(opt.id, false)}
                      />
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-gray-600">取消</button>
            <button onClick={handleCreate} disabled={newSaving}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg disabled:opacity-50">
              {newSaving ? '建立中...' : '建立帳號'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
