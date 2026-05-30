import { useState, useEffect, useCallback } from 'react'
import { getTeamMembers, createTeamMember, updateTeamMember, deleteTeamMember } from '../api'
import Modal from '../components/Modal'

function Field({ label, value, onChange, multiline, type = 'text' }) {
  return (
    <div className="mb-3">
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{label}</label>
      {multiline ? (
        <textarea value={value ?? ''} onChange={e => onChange(e.target.value)} rows={3}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400 resize-none" />
      ) : (
        <input type={type} value={value ?? ''} onChange={e => onChange(e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400" />
      )}
    </div>
  )
}

const emptyMember = { name: '', member_type: 'developer', role: '', bio: '', github_url: '', linkedin_url: '', email: '', order: 0 }

/** 排序圖示元件 */
function SortIcon({ field, sortField, sortDir }) {
  if (sortField !== field) return <span className="text-gray-300 ml-0.5">↕</span>
  return sortDir === 'asc' ? <span className="text-blue-500 ml-0.5">↑</span> : <span className="text-blue-500 ml-0.5">↓</span>
}

export default function TeamMembers() {
  const [members, setMembers]     = useState([])
  const [selected, setSelected]   = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [editForm, setEditForm]   = useState({})
  const [saving, setSaving]       = useState(false)
  const [saved, setSaved]         = useState(false)
  const [modal, setModal]         = useState(false)
  const [newForm, setNewForm]     = useState(emptyMember)
  const [newSaving, setNewSaving] = useState(false)
  const [sortField, setSortField] = useState('name')   // 排序欄位
  const [sortDir, setSortDir]     = useState('asc')    // asc 或 desc

  const load = useCallback(() =>
    getTeamMembers().then(r => setMembers(r.data.results || r.data)), [])

  useEffect(() => { load() }, [load])

  const selectMember = (m) => { setSelected(m); setEditForm({ ...m }); setSaved(false) }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await updateTeamMember(selected.id, editForm)
      setSelected(res.data)
      setSaved(true)
      load()
    } catch (e) { alert('儲存失敗') }
    finally { setSaving(false) }
  }

  const handleDelete = async () => {
    if (!confirm(`確定刪除「${selected.name}」？`)) return
    await deleteTeamMember(selected.id)
    setSelected(null)
    load()
  }

  const handleCreate = async () => {
    setNewSaving(true)
    try {
      await createTeamMember(newForm)
      setModal(false)
      setNewForm(emptyMember)
      load()
    } catch { alert('建立失敗') }
    finally { setNewSaving(false) }
  }

  const set = (f, v) => { setEditForm(p => ({...p, [f]: v})); setSaved(false) }

  // 排序切換函式
  function toggleSort(field) {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  // 搜尋篩選：依成員姓名
  const filteredMembers = members.filter(m => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return m.name && m.name.toLowerCase().includes(term)
  })

  // 排序後的成員
  const sortedRefMembers = [...filteredMembers.filter(m => m.member_type === 'reference')].sort((a, b) => {
    const aVal = a[sortField] ?? ''
    const bVal = b[sortField] ?? ''
    const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal), 'zh-TW')
    return sortDir === 'asc' ? cmp : -cmp
  })
  const sortedDevMembers = [...filteredMembers.filter(m => m.member_type === 'developer')].sort((a, b) => {
    const aVal = a[sortField] ?? ''
    const bVal = b[sortField] ?? ''
    const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal), 'zh-TW')
    return sortDir === 'asc' ? cmp : -cmp
  })

  const refMembers = filteredMembers.filter(m => m.member_type === 'reference')
  const devMembers = filteredMembers.filter(m => m.member_type === 'developer')

  return (
    <div className="flex h-full">
      {/* 中欄：成員清單 */}
      <div className="w-64 bg-white border-r border-gray-100 flex-shrink-0 flex flex-col">
        {/* 搜尋 */}
        <div className="px-4 py-2 border-b border-gray-100">
          <input
            type="text"
            placeholder="搜尋成員姓名..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400"
          />
        </div>
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">成員管理</h3>
          <button onClick={() => setModal(true)}
            className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-500">+ 新增</button>
        </div>
        {/* 排序控制 */}
        <div className="px-4 py-1.5 border-b border-gray-100 flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-400">排序：</span>
          {[
            { field: 'name', label: '姓名' },
            { field: 'order', label: '排序' },
            { field: 'member_type', label: '類型' },
          ].map(({ field, label }) => (
            <button key={field} onClick={() => toggleSort(field)}
              className="text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors flex items-center">
              {label}<SortIcon field={field} sortField={sortField} sortDir={sortDir} />
            </button>
          ))}
        </div>
        <div className="overflow-y-auto flex-1">
          {filteredMembers.length === 0 && members.length === 0 && (
            <div className="text-center text-gray-400 text-sm py-8">
              <div className="text-2xl mb-2">📭</div>
              <p>沒有成員</p>
            </div>
          )}
          {filteredMembers.length === 0 && members.length > 0 && (
            <div className="text-center text-gray-400 text-sm py-8">
              <div className="text-2xl mb-2">🔍</div>
              <p>沒有符合的成員</p>
            </div>
          )}
          {sortedRefMembers.length > 0 && (
            <div>
              <div className="px-4 py-2 text-xs font-semibold text-blue-500 uppercase tracking-wider bg-blue-50">原專案參考者</div>
              {sortedRefMembers.map(m => <MemberRow key={m.id} m={m} selected={selected} onClick={selectMember} />)}
            </div>
          )}
          {sortedDevMembers.length > 0 && (
            <div>
              <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider bg-gray-50">開發團隊</div>
              {sortedDevMembers.map(m => <MemberRow key={m.id} m={m} selected={selected} onClick={selectMember} />)}
            </div>
          )}
        </div>
      </div>

      {/* 右欄 */}
      <div className="flex-1 overflow-y-auto bg-white">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center"><div className="text-4xl mb-2">👥</div><p>請從左側選擇成員</p></div>
          </div>
        ) : (
          <div className="max-w-xl mx-auto px-8 py-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white text-xl font-bold">
                  {selected.name.charAt(0)}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-800">{selected.name}</h2>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${selected.member_type === 'reference' ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-600'}`}>
                    {selected.member_type === 'reference' ? '原專案參考者' : '開發團隊'}
                  </span>
                </div>
              </div>
              <button onClick={handleDelete} className="text-xs text-red-500 hover:text-red-700 px-3 py-1.5 border border-red-200 rounded-lg hover:bg-red-50">刪除</button>
            </div>

            <div className="grid grid-cols-2 gap-x-4">
              <Field label="姓名" value={editForm.name} onChange={v => set('name', v)} />
              <div className="mb-3">
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">成員類型</label>
                <select value={editForm.member_type} onChange={e => set('member_type', e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400">
                  <option value="developer">開發團隊</option>
                  <option value="reference">原專案參考者</option>
                </select>
              </div>
            </div>
            <Field label="職稱 / 負責領域" value={editForm.role} onChange={v => set('role', v)} />
            <Field label="個人介紹" value={editForm.bio} onChange={v => set('bio', v)} multiline />
            <div className="grid grid-cols-2 gap-x-4">
              <Field label="GitHub URL" value={editForm.github_url} onChange={v => set('github_url', v)} />
              <Field label="LinkedIn URL" value={editForm.linkedin_url} onChange={v => set('linkedin_url', v)} />
            </div>
            <div className="grid grid-cols-2 gap-x-4">
              <Field label="Email" value={editForm.email} onChange={v => set('email', v)} type="email" />
              <Field label="排序" value={editForm.order} onChange={v => set('order', Number(v))} type="number" />
            </div>

            <div className="flex items-center gap-3 pt-2 border-t border-gray-100 mt-2">
              <button onClick={handleSave} disabled={saving}
                className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
                {saving ? '儲存中...' : '儲存變更'}
              </button>
              {saved && <span className="text-green-500 text-sm">✓ 已儲存</span>}
            </div>
          </div>
        )}
      </div>

      {/* 新增成員 Modal */}
      {modal && (
        <Modal title="新增成員" onClose={() => setModal(false)} size="lg">
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="姓名" value={newForm.name} onChange={v => setNewForm(p => ({...p, name: v}))} />
            <div className="mb-3">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">成員類型</label>
              <select value={newForm.member_type} onChange={e => setNewForm(p => ({...p, member_type: e.target.value}))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none">
                <option value="developer">開發團隊</option>
                <option value="reference">原專案參考者</option>
              </select>
            </div>
          </div>
          <Field label="職稱" value={newForm.role} onChange={v => setNewForm(p => ({...p, role: v}))} />
          <Field label="個人介紹" value={newForm.bio} onChange={v => setNewForm(p => ({...p, bio: v}))} multiline />
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="GitHub URL" value={newForm.github_url} onChange={v => setNewForm(p => ({...p, github_url: v}))} />
            <Field label="Email" value={newForm.email} onChange={v => setNewForm(p => ({...p, email: v}))} type="email" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-gray-600">取消</button>
            <button onClick={handleCreate} disabled={newSaving} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg disabled:opacity-50">
              {newSaving ? '建立中...' : '建立成員'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function MemberRow({ m, selected, onClick }) {
  return (
    <button onClick={() => onClick(m)}
      className={`w-full flex items-center gap-3 px-4 py-3 border-b border-gray-50 transition-colors text-left ${
        selected?.id === m.id ? 'bg-blue-50 border-r-2 border-blue-600' : 'hover:bg-gray-50'
      }`}
    >
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
        {m.name.charAt(0)}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium text-gray-800 truncate">{m.name}</div>
        <div className="text-xs text-gray-500 truncate">{m.role}</div>
      </div>
    </button>
  )
}
