import { useState, useEffect, useCallback } from 'react'
import {
  deviceLogin,
  deviceGetUsers, deviceCreateUser, deviceUpdateUser, deviceDeleteUser,
  deviceGetContacts, deviceAddContact, deviceUpdateContact, deviceDeleteContact,
  deviceGetImpacts,
  deviceGetSettings, deviceUpdateSettings,
} from '../api'

// ── 角色設定 ───────────────────────────────────────────────────────────────
const ROLE_LABELS = { admin: '管理員', operator: '操作員', user: '使用者' }
const ROLE_COLORS = {
  admin:    'bg-red-100 text-red-700',
  operator: 'bg-yellow-100 text-yellow-700',
  user:     'bg-blue-100 text-blue-700',
}

// ── 共用欄位元件 ────────────────────────────────────────────────────────────
function Field({ label, value, onChange, type = 'text', placeholder = '' }) {
  return (
    <div className="mb-3">
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{label}</label>
      <input type={type} value={value ?? ''} placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400" />
    </div>
  )
}

// ── 自動連線狀態顯示 ────────────────────────────────────────────────────────
function ConnectingScreen() {
  return (
    <div className="flex items-center justify-center h-full bg-slate-50">
      <div className="text-center text-gray-400">
        <div className="text-3xl mb-3 animate-pulse">📡</div>
        <p className="text-sm">正在連線眼鏡伺服器…</p>
      </div>
    </div>
  )
}

function ConnectErrorScreen({ onRetry }) {
  return (
    <div className="flex items-center justify-center h-full bg-slate-50">
      <div className="text-center">
        <div className="text-3xl mb-3">⚠️</div>
        <p className="text-sm text-gray-600 mb-1">無法連線眼鏡伺服器（port 8081）</p>
        <p className="text-xs text-gray-400 mb-4">請確認 <code>uv run python app_main.py</code> 已啟動</p>
        <button onClick={onRetry}
          className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-500">
          重試
        </button>
      </div>
    </div>
  )
}

// ── 使用者管理 Tab ──────────────────────────────────────────────────────────
function UsersTab() {
  const [users, setUsers]       = useState([])
  const [selected, setSel]      = useState(null)
  const [editForm, setEdit]     = useState({})
  const [saving, setSaving]     = useState(false)
  const [saved, setSaved]       = useState(false)
  const [showNew, setShowNew]   = useState(false)
  const [newForm, setNew]       = useState({ username: '', password: '', role: 'user' })
  const [creating, setCreating] = useState(false)

  // ── 感測器設定 ──
  const [sensor, setSensor]         = useState({ impact_threshold: 30.0, cooldown_seconds: 30 })
  const [savingSensor, setSavingSens] = useState(false)
  const [savedSensor, setSavedSens]   = useState(false)
  const setSens = (f, v) => { setSensor(p => ({ ...p, [f]: v })); setSavedSens(false) }

  const load = useCallback(() =>
    deviceGetUsers().then(r => setUsers(r.data)).catch(() => {}), [])

  useEffect(() => { load() }, [load])

  const selectUser = (u) => {
    setSel(u); setEdit({ ...u, password: '' }); setSaved(false); setSavedSens(false)
    // 載入該使用者的感測器設定
    deviceGetSettings(u.id)
      .then(r => setSensor(r.data))
      .catch(() => setSensor({ impact_threshold: 30.0, cooldown_seconds: 30 }))
  }
  const set = (f, v) => { setEdit(p => ({ ...p, [f]: v })); setSaved(false) }

  const handleSaveSensor = async () => {
    setSavingSens(true)
    try {
      await deviceUpdateSettings(selected.id, sensor)
      setSavedSens(true)
    } catch (e) { alert('儲存失敗：' + JSON.stringify(e.response?.data)) }
    finally { setSavingSens(false) }
  }

  // G 值換算（顯示用）
  const gVal = (ms2) => (ms2 / 9.8).toFixed(1)

  const handleSave = async () => {
    setSaving(true)
    const payload = {}
    if (editForm.role    !== selected.role)    payload.role    = editForm.role
    if (editForm.enabled !== selected.enabled) payload.enabled = editForm.enabled
    if (editForm.password) payload.password = editForm.password
    try {
      await deviceUpdateUser(selected.id, payload)
      setSaved(true); load()
    } catch (e) { alert('儲存失敗：' + JSON.stringify(e.response?.data)) }
    finally { setSaving(false) }
  }

  const handleDelete = async () => {
    if (!confirm(`確定刪除帳號「${selected.username}」？`)) return
    await deviceDeleteUser(selected.id)
    setSel(null); load()
  }

  const handleCreate = async () => {
    if (!newForm.username || !newForm.password) { alert('帳號和密碼為必填'); return }
    setCreating(true)
    try {
      await deviceCreateUser(newForm)
      setShowNew(false); setNew({ username: '', password: '', role: 'user' }); load()
    } catch (e) { alert('建立失敗：' + JSON.stringify(e.response?.data)) }
    finally { setCreating(false) }
  }

  return (
    <div className="flex h-full">
      {/* 左欄：使用者清單 */}
      <div className="w-64 bg-white border-r border-gray-100 flex-shrink-0 flex flex-col">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">APP 使用者</h3>
          <button onClick={() => setShowNew(true)}
            className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-500">+ 新增</button>
        </div>
        <div className="overflow-y-auto flex-1">
          {users.map(u => (
            <button key={u.id} onClick={() => selectUser(u)}
              className={`w-full flex items-center gap-3 px-4 py-3 border-b border-gray-50 transition-colors text-left ${
                selected?.id === u.id ? 'bg-green-50 border-r-2 border-green-600' : 'hover:bg-gray-50'
              }`}
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 uppercase">
                {u.username.charAt(0)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-gray-800 truncate">{u.username}</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${ROLE_COLORS[u.role] || ROLE_COLORS.user}`}>
                    {ROLE_LABELS[u.role] || u.role}
                  </span>
                  {!u.enabled && <span className="text-xs text-red-500">停用</span>}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右欄：編輯 */}
      <div className="flex-1 overflow-y-auto bg-white">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center"><div className="text-4xl mb-2">📱</div><p>請從左側選擇使用者</p></div>
          </div>
        ) : (
          <div className="max-w-md mx-auto px-8 py-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center text-white text-xl font-bold uppercase">
                  {selected.username.charAt(0)}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-800">{selected.username}</h2>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${ROLE_COLORS[selected.role]}`}>
                    {ROLE_LABELS[selected.role] || selected.role}
                  </span>
                </div>
              </div>
              <button onClick={handleDelete}
                className="text-xs text-red-500 hover:text-red-700 px-3 py-1.5 border border-red-200 rounded-lg hover:bg-red-50">刪除</button>
            </div>

            <div className="mb-3">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">角色</label>
              <select value={editForm.role} onChange={e => set('role', e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400">
                <option value="admin">管理員</option>
                <option value="operator">操作員</option>
                <option value="user">使用者</option>
              </select>
            </div>

            <div className="mb-4 flex items-center gap-2">
              <input type="checkbox" id="chkEnabled" checked={!!editForm.enabled}
                onChange={e => set('enabled', e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-green-600" />
              <label htmlFor="chkEnabled" className="text-sm text-gray-700 cursor-pointer">帳號啟用中</label>
            </div>

            <Field label="新密碼（留空不更改）" value={editForm.password} onChange={v => set('password', v)} type="password" />

            <div className="flex items-center gap-3 pt-2 border-t border-gray-100 mt-2">
              <button onClick={handleSave} disabled={saving}
                className="px-5 py-2 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
                {saving ? '儲存中…' : '儲存變更'}
              </button>
              {saved && <span className="text-green-500 text-sm">✓ 已儲存</span>}
            </div>

            {/* ── 感測器設定 ── */}
            <div className="mt-6 pt-5 border-t border-gray-100">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">
                📡 撞擊感測器設定
              </h3>

              {/* 觸發閾值 */}
              <div className="mb-5">
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">觸發閾值</label>
                  <span className="text-sm font-bold text-gray-800">
                    {gVal(sensor.impact_threshold)} G
                    <span className="text-xs text-gray-400 font-normal ml-1">
                      ({parseFloat(sensor.impact_threshold).toFixed(1)} m/s²)
                    </span>
                  </span>
                </div>
                <input type="range" min="9.8" max="98" step="0.5"
                  value={sensor.impact_threshold}
                  onChange={e => setSens('impact_threshold', parseFloat(e.target.value))}
                  className="w-full accent-green-600" />
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>1.0 G（極敏感）</span><span>3.0 G（預設）</span><span>10.0 G（極遲鈍）</span>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  數值越低越敏感，輕碰也觸發；越高則只有劇烈撞擊才觸發。
                </p>
              </div>

              {/* 冷卻時間 */}
              <div className="mb-5">
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">觸發後冷卻時間</label>
                  <span className="text-sm font-bold text-gray-800">{sensor.cooldown_seconds} 秒</span>
                </div>
                <input type="range" min="10" max="120" step="5"
                  value={sensor.cooldown_seconds}
                  onChange={e => setSens('cooldown_seconds', parseInt(e.target.value))}
                  className="w-full accent-green-600" />
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>10 秒</span><span>30 秒（預設）</span><span>120 秒</span>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  觸發後等待時間，防止連續誤觸；撥電話期間不會再次觸發。
                </p>
              </div>

              <div className="flex items-center gap-3">
                <button onClick={handleSaveSensor} disabled={savingSensor}
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
                  {savingSensor ? '套用中…' : '套用感測器設定'}
                </button>
                {savedSensor && <span className="text-blue-500 text-sm">✓ 已套用（下次 APP 連線後生效）</span>}
              </div>
            </div>

          </div>
        )}
      </div>

      {/* 新增帳號 Modal */}
      {showNew && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80">
            <h3 className="text-sm font-bold text-gray-800 mb-4">新增 APP 帳號</h3>
            <Field label="帳號" value={newForm.username} onChange={v => setNew(p => ({ ...p, username: v }))} />
            <Field label="密碼" value={newForm.password} onChange={v => setNew(p => ({ ...p, password: v }))} type="password" />
            <div className="mb-3">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">角色</label>
              <select value={newForm.role} onChange={e => setNew(p => ({ ...p, role: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none">
                <option value="admin">管理員</option>
                <option value="operator">操作員</option>
                <option value="user">使用者</option>
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowNew(false)} className="px-4 py-2 text-sm text-gray-600">取消</button>
              <button onClick={handleCreate} disabled={creating}
                className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg disabled:opacity-50">
                {creating ? '建立中…' : '建立帳號'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 緊急連絡人 Tab ──────────────────────────────────────────────────────────
function ContactsTab({ users }) {
  const [selectedUid, setSelectedUid] = useState(null)
  const [contacts, setContacts]       = useState([])
  const [selectedC, setSelC]          = useState(null)
  const [editForm, setEdit]           = useState({})
  const [saving, setSaving]           = useState(false)
  const [saved, setSaved]             = useState(false)
  const [showNew, setShowNew]         = useState(false)
  const [newForm, setNew]             = useState({ name: '', phone: '' })
  const [creating, setCreating]       = useState(false)

  const loadContacts = useCallback((uid) => {
    if (!uid) return
    deviceGetContacts(uid).then(r => setContacts(r.data)).catch(() => setContacts([]))
  }, [])

  const pickUser = (uid) => {
    setSelectedUid(uid); setSelC(null); setContacts([]); loadContacts(uid)
  }

  const pickContact = (c) => { setSelC(c); setEdit({ ...c }); setSaved(false) }
  const set = (f, v) => { setEdit(p => ({ ...p, [f]: v })); setSaved(false) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await deviceUpdateContact(selectedC.id, selectedUid, editForm)
      setSaved(true); loadContacts(selectedUid)
    } catch (e) { alert('儲存失敗：' + JSON.stringify(e.response?.data)) }
    finally { setSaving(false) }
  }

  const handleDelete = async () => {
    if (!confirm(`確定刪除連絡人「${selectedC.name}」？`)) return
    await deviceDeleteContact(selectedC.id, selectedUid)
    setSelC(null); loadContacts(selectedUid)
  }

  const handleCreate = async () => {
    if (!newForm.name || !newForm.phone) { alert('姓名和電話為必填'); return }
    setCreating(true)
    try {
      await deviceAddContact(selectedUid, newForm)
      setShowNew(false); setNew({ name: '', phone: '' }); loadContacts(selectedUid)
    } catch (e) { alert('新增失敗：' + JSON.stringify(e.response?.data)) }
    finally { setCreating(false) }
  }

  const selectedUser = users.find(u => u.id === selectedUid)

  return (
    <div className="flex h-full">
      {/* 左欄：使用者選擇 */}
      <div className="w-52 bg-white border-r border-gray-100 flex-shrink-0 flex flex-col">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">選擇使用者</h3>
        </div>
        <div className="overflow-y-auto flex-1">
          {users.map(u => (
            <button key={u.id} onClick={() => pickUser(u.id)}
              className={`w-full flex items-center gap-2.5 px-4 py-3 border-b border-gray-50 text-left transition-colors ${
                selectedUid === u.id ? 'bg-green-50 border-r-2 border-green-600' : 'hover:bg-gray-50'
              }`}
            >
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 uppercase">
                {u.username.charAt(0)}
              </div>
              <span className="text-sm text-gray-700 truncate">{u.username}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 中欄：連絡人清單 */}
      <div className="w-56 bg-white border-r border-gray-100 flex-shrink-0 flex flex-col">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">
            {selectedUser ? selectedUser.username + ' 的連絡人' : '連絡人'}
          </h3>
          {selectedUid && (
            <button onClick={() => setShowNew(true)}
              className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-500">+ 新增</button>
          )}
        </div>
        <div className="overflow-y-auto flex-1">
          {!selectedUid ? (
            <div className="text-xs text-gray-400 text-center py-8">請先選擇使用者</div>
          ) : contacts.length === 0 ? (
            <div className="text-xs text-gray-400 text-center py-8">無連絡人</div>
          ) : contacts.map(c => (
            <button key={c.id} onClick={() => pickContact(c)}
              className={`w-full flex items-center gap-2.5 px-4 py-3 border-b border-gray-50 text-left transition-colors ${
                selectedC?.id === c.id ? 'bg-green-50 border-r-2 border-green-600' : 'hover:bg-gray-50'
              }`}
            >
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-slate-400 to-slate-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                {c.name.charAt(0)}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-800 truncate">{c.name}</div>
                <div className="text-xs text-gray-400 truncate">{c.phone}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右欄：編輯連絡人 */}
      <div className="flex-1 overflow-y-auto bg-white">
        {!selectedC ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center"><div className="text-4xl mb-2">📞</div><p>請從左側選擇連絡人</p></div>
          </div>
        ) : (
          <div className="max-w-sm mx-auto px-8 py-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-gray-800">編輯連絡人</h2>
              <button onClick={handleDelete}
                className="text-xs text-red-500 hover:text-red-700 px-3 py-1.5 border border-red-200 rounded-lg hover:bg-red-50">刪除</button>
            </div>
            <Field label="姓名" value={editForm.name}  onChange={v => set('name', v)} />
            <Field label="電話" value={editForm.phone} onChange={v => set('phone', v)} />
            <div className="flex items-center gap-3 pt-2 border-t border-gray-100 mt-2">
              <button onClick={handleSave} disabled={saving}
                className="px-5 py-2 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
                {saving ? '儲存中…' : '儲存變更'}
              </button>
              {saved && <span className="text-green-500 text-sm">✓ 已儲存</span>}
            </div>
          </div>
        )}
      </div>

      {/* 新增連絡人 Modal */}
      {showNew && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-72">
            <h3 className="text-sm font-bold text-gray-800 mb-4">
              新增連絡人（{selectedUser?.username}）
            </h3>
            <Field label="姓名" value={newForm.name}  onChange={v => setNew(p => ({ ...p, name: v }))} />
            <Field label="電話" value={newForm.phone} onChange={v => setNew(p => ({ ...p, phone: v }))} />
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowNew(false)} className="px-4 py-2 text-sm text-gray-600">取消</button>
              <button onClick={handleCreate} disabled={creating}
                className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg disabled:opacity-50">
                {creating ? '新增中…' : '新增'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 撞擊記錄 Tab ────────────────────────────────────────────────────────────
function ImpactsTab({ users }) {
  const [impacts, setImpacts]     = useState([])
  const [filterUser, setFilter]   = useState('')
  const [loading, setLoading]     = useState(false)

  const OUTCOME = {
    auto_dialed: { cls: 'bg-red-100 text-red-700',      label: '已自動撥打' },
    cancelled:   { cls: 'bg-yellow-100 text-yellow-700', label: '使用者取消' },
    no_contacts: { cls: 'bg-gray-100 text-gray-500',    label: '無緊急連絡人' },
    triggered:   { cls: 'bg-blue-100 text-blue-700',    label: '觸發中' },
  }

  const fmtTime = (ts) => new Date(ts * 1000).toLocaleString('zh-TW')
  const fmtG    = (m)  => (m / 9.8).toFixed(2) + ' G'

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const uid = filterUser ? parseInt(filterUser) : null
      const r = await deviceGetImpacts(uid)
      setImpacts(r.data)
    } catch {}
    setLoading(false)
  }, [filterUser])

  useEffect(() => { load() }, [load])

  return (
    <div className="p-6 h-full overflow-y-auto">
      {/* 篩選列 */}
      <div className="flex items-center gap-3 mb-4">
        <label className="text-sm text-gray-600">篩選使用者：</label>
        <select value={filterUser} onChange={e => setFilter(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:border-blue-400">
          <option value="">全部</option>
          {users.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}
        </select>
        <button onClick={load}
          className="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-500">
          重新整理
        </button>
        <span className="text-xs text-gray-400 ml-auto">共 {impacts.length} 筆</span>
      </div>

      {loading ? (
        <div className="text-center text-gray-400 py-12">載入中…</div>
      ) : impacts.length === 0 ? (
        <div className="text-center text-gray-400 py-12">尚無撞擊記錄</div>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-slate-50 text-left">
              <th className="px-3 py-2 font-semibold text-gray-600">時間</th>
              <th className="px-3 py-2 font-semibold text-gray-600">使用者</th>
              <th className="px-3 py-2 font-semibold text-gray-600">強度</th>
              <th className="px-3 py-2 font-semibold text-gray-600">處置結果</th>
            </tr>
          </thead>
          <tbody>
            {impacts.map(e => {
              const o = OUTCOME[e.outcome] ?? { cls: 'bg-gray-100 text-gray-500', label: e.outcome }
              return (
                <tr key={e.id} className="border-t border-gray-100 hover:bg-slate-50">
                  <td className="px-3 py-2 text-gray-700 whitespace-nowrap">{fmtTime(e.timestamp)}</td>
                  <td className="px-3 py-2 text-gray-700">{e.username}</td>
                  <td className="px-3 py-2 text-gray-600">{fmtG(e.magnitude)}</td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${o.cls}`}>{o.label}</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <p className="text-xs text-gray-400 mt-4">
        ※ 強度以 G 值顯示（1 G ≈ 9.8 m/s²，目前觸發閾值約 3 G）。
        若某使用者頻繁「使用者取消」，表示可能過於敏感，可調高 <code>_impactThreshold</code>（imu_service.dart）。
        若「無緊急連絡人」出現，請提醒該使用者在 APP 設定頁面新增連絡人。
      </p>
    </div>
  )
}

// ── 主元件 ──────────────────────────────────────────────────────────────────
export default function AppDevice() {
  const [status, setStatus] = useState('connecting') // connecting | ok | error
  const [tab, setTab]       = useState('users')
  const [users, setUsers]   = useState([])

  const loadUsers = useCallback(() =>
    deviceGetUsers().then(r => setUsers(r.data)).catch(() => {}), [])

  // 進入頁面時自動登入 FastAPI（使用後台預設管理員帳密）
  const autoLogin = useCallback(async () => {
    setStatus('connecting')
    try {
      // 若已有有效 token，直接試一次 API
      if (localStorage.getItem('device_access')) {
        await deviceGetUsers()
        setStatus('ok')
        loadUsers()
        return
      }
      const res = await deviceLogin('1124', '1124')
      localStorage.setItem('device_access', res.data.token)
      setStatus('ok')
      loadUsers()
    } catch {
      // token 失效時重新登入
      localStorage.removeItem('device_access')
      try {
        const res = await deviceLogin('1124', '1124')
        localStorage.setItem('device_access', res.data.token)
        setStatus('ok')
        loadUsers()
      } catch {
        setStatus('error')
      }
    }
  }, [loadUsers])

  useEffect(() => { autoLogin() }, [autoLogin])

  if (status === 'connecting') return <ConnectingScreen />
  if (status === 'error')      return <ConnectErrorScreen onRetry={autoLogin} />

  return (
    <div className="flex flex-col h-full">
      {/* 子頁籤列 */}
      <div className="bg-white border-b border-gray-100 px-6 flex items-center gap-1 flex-shrink-0">
        {[
          { id: 'users',    label: '👤 APP 使用者' },
          { id: 'contacts', label: '📞 緊急連絡人' },
          { id: 'impacts',  label: '⚠️ 撞擊記錄' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id
                ? 'border-green-600 text-green-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >{t.label}</button>
        ))}
        <div className="flex-1" />
        {/* 連線狀態指示 */}
        <div className="flex items-center gap-1.5 text-xs text-green-600 my-2 mr-2">
          <span className="w-2 h-2 rounded-full bg-green-500 inline-block"></span>
          眼鏡伺服器已連線
        </div>
      </div>

      {/* 內容 */}
      <div className="flex-1 overflow-hidden">
        {tab === 'users'    && <UsersTab />}
        {tab === 'contacts' && <ContactsTab users={users} />}
        {tab === 'impacts'  && <ImpactsTab  users={users} />}
      </div>
    </div>
  )
}
