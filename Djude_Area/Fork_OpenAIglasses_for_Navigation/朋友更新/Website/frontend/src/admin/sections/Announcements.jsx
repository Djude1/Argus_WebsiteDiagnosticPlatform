/**
 * 公告管理（重構版）
 * - 管理公告的新增、編輯、刪除
 * - 標籤管理（CRUD）
 * - 支援網站前台顯示設定
 * - 查看前台公告頁面按鈕
 */
import { useState, useEffect, useCallback } from 'react'
import {
  getAnnouncements, createAnnouncement,
  updateAnnouncement, deleteAnnouncement,
  getAnnouncementTags, createAnnouncementTag,
  updateAnnouncementTag, deleteAnnouncementTag,
} from '../api'

// ── 類型設定 ────────────────────────────────────────────────────────────────
const TYPE_LABELS = {
  version_update: '版本更新',
  maintenance:    '系統維護',
  new_feature:    '新功能',
  general:        '一般通知',
}
const TYPE_COLORS = {
  version_update: 'bg-blue-100 text-blue-700 border-blue-200',
  maintenance:    'bg-yellow-100 text-yellow-700 border-yellow-200',
  new_feature:    'bg-green-100 text-green-700 border-green-200',
  general:        'bg-gray-100 text-gray-600 border-gray-200',
}
const TYPE_ICON = {
  version_update: '🔄',
  maintenance:    '🔧',
  new_feature:    '✨',
  general:        '📢',
}

// ── 時間格式化 ──────────────────────────────────────────────────────────────
function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

// ── 標籤管理 Modal ──────────────────────────────────────────────────────────
function TagManagerModal({ tags, onClose, onCreate, onUpdate, onDelete }) {
  const [newTag, setNewTag] = useState({ name: '', slug: '', color: '#6366f1' })
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', slug: '', color: '#6366f1' })

  const handleCreate = async () => {
    if (!newTag.name.trim()) return
    await onCreate(newTag)
    setNewTag({ name: '', slug: '', color: '#6366f1' })
  }

  const handleUpdate = async (id) => {
    if (!editForm.name.trim()) return
    await onUpdate(id, editForm)
    setEditingId(null)
  }

  const startEdit = (tag) => {
    setEditingId(tag.id)
    setEditForm({ name: tag.name, slug: tag.slug, color: tag.color || '#6366f1' })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-800">標籤管理</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 新增標籤 */}
        <div className="px-5 py-4 border-b border-gray-100 bg-slate-50">
          <p className="text-xs font-medium text-gray-600 mb-2">新增標籤</p>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="標籤名稱"
              value={newTag.name}
              onChange={(e) => setNewTag(f => ({ ...f, name: e.target.value, slug: e.target.value.toLowerCase().replace(/\s+/g, '-') }))}
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <input
              type="color"
              value={newTag.color}
              onChange={(e) => setNewTag(f => ({ ...f, color: e.target.value }))}
              className="w-10 h-10 rounded-lg border border-gray-200 cursor-pointer"
            />
            <button
              onClick={handleCreate}
              disabled={!newTag.name.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              新增
            </button>
          </div>
        </div>

        {/* 標籤列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {tags.length === 0 ? (
            <div className="text-center text-gray-400 py-8">
              <p className="text-sm">尚無標籤</p>
            </div>
          ) : (
            tags.map((tag) => (
              <div key={tag.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl">
                {editingId === tag.id ? (
                  <>
                    <input
                      type="text"
                      value={editForm.name}
                      onChange={(e) => setEditForm(f => ({ ...f, name: e.target.value, slug: e.target.value.toLowerCase().replace(/\s+/g, '-') }))}
                      className="flex-1 border border-gray-200 rounded-lg px-2 py-1 text-sm text-gray-800"
                    />
                    <input
                      type="color"
                      value={editForm.color}
                      onChange={(e) => setEditForm(f => ({ ...f, color: e.target.value }))}
                      className="w-8 h-8 rounded border border-gray-200 cursor-pointer"
                    />
                    <button
                      onClick={() => handleUpdate(tag.id)}
                      className="text-green-600 hover:text-green-700 text-sm font-medium"
                    >
                      儲存
                    </button>
                    <button onClick={() => setEditingId(null)} className="text-gray-400 hover:text-gray-600 text-sm">
                      取消
                    </button>
                  </>
                ) : (
                  <>
                    <span
                      className="w-4 h-4 rounded-full flex-shrink-0"
                      style={{ backgroundColor: tag.color || '#6366f1' }}
                    />
                    <span className="flex-1 text-sm font-medium text-gray-700">{tag.name}</span>
                    <span className="text-xs text-gray-400">#{tag.slug}</span>
                    <button onClick={() => startEdit(tag)} className="text-gray-400 hover:text-blue-600">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button onClick={() => onDelete(tag.id)} className="text-gray-400 hover:text-red-500">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

/** 排序圖示元件 */
function SortIcon({ field, sortField, sortDir }) {
  if (sortField !== field) return <span className="text-gray-300 ml-0.5">↕</span>
  return sortDir === 'asc' ? <span className="text-blue-500 ml-0.5">↑</span> : <span className="text-blue-500 ml-0.5">↓</span>
}

// ── 主元件 ──────────────────────────────────────────────────────────────────
export default function Announcements() {
  const [announcements, setAnnouncements] = useState([])
  const [tags, setTags] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [toggling, setToggling] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [showTagManager, setShowTagManager] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [sortField, setSortField] = useState('created_at')  // 排序欄位
  const [sortDir, setSortDir] = useState('desc')            // 預設最新在前
  const [form, setForm] = useState({
    type: 'general', title: '', body: '', scheduled_at: '',
    is_active: true, show_on_website: false, tags: [],
  })

  // ── 載入資料 ──────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [annRes, tagRes] = await Promise.all([
        getAnnouncements(),
        getAnnouncementTags(),
      ])
      setAnnouncements(Array.isArray(annRes?.data?.results) ? annRes.data.results : (Array.isArray(annRes?.data) ? annRes.data : []))
      setTags(Array.isArray(tagRes?.data?.results) ? tagRes.data.results : (Array.isArray(tagRes?.data) ? tagRes.data : []))
    } catch (err) {
      console.error('載入公告失敗:', err)
      setAnnouncements([])
      setTags([])
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  // ── 搜尋篩選 ──────────────────────────────────────────────────────────────
  const filteredAnnouncements = announcements.filter(item => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return (
      (item.title && item.title.toLowerCase().includes(term)) ||
      (item.body && item.body.toLowerCase().includes(term)) ||
      (item.type_display && item.type_display.toLowerCase().includes(term))
    )
  })

  // ── 排序 ──────────────────────────────────────────────────────────────────
  function toggleSort(field) {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const sortedAnnouncements = [...filteredAnnouncements].sort((a, b) => {
    const aVal = a[sortField] ?? ''
    const bVal = b[sortField] ?? ''
    let cmp
    if (sortField === 'created_at' || sortField === 'scheduled_at') {
      cmp = new Date(aVal) - new Date(bVal)
    } else if (typeof aVal === 'boolean') {
      cmp = (aVal === bVal ? 0 : aVal ? -1 : 1)
    } else {
      cmp = String(aVal).localeCompare(String(bVal), 'zh-TW')
    }
    return sortDir === 'asc' ? cmp : -cmp
  })

  // ── 標籤操作 ──────────────────────────────────────────────────────────────
  const handleCreateTag = async (data) => {
    try {
      await createAnnouncementTag(data)
      await load()
    } catch (err) {
      console.error('建立標籤失敗:', err)
    }
  }

  const handleUpdateTag = async (id, data) => {
    try {
      await updateAnnouncementTag(id, data)
      await load()
    } catch (err) {
      console.error('更新標籤失敗:', err)
    }
  }

  const handleDeleteTag = async (id) => {
    if (!window.confirm('確定要刪除此標籤？')) return
    try {
      await deleteAnnouncementTag(id)
      await load()
    } catch (err) {
      console.error('刪除標籤失敗:', err)
    }
  }

  // ── 切換啟用狀態 ──────────────────────────────────────────────────────────
  const handleToggle = async (item) => {
    setToggling(item.id)
    try {
      await updateAnnouncement(item.id, { is_active: !item.is_active })
      await load()
    } catch (err) {
      console.error('切換狀態失敗:', err)
    }
    setToggling(null)
  }

  // ── 切換前台顯示 ──────────────────────────────────────────────────────────
  const handleToggleWebsite = async (item) => {
    setToggling(item.id)
    try {
      await updateAnnouncement(item.id, { show_on_website: !item.show_on_website })
      await load()
    } catch (err) {
      console.error('切換前台顯示失敗:', err)
    }
    setToggling(null)
  }

  // ── 刪除 ──────────────────────────────────────────────────────────────────
  const handleDelete = async (item) => {
    if (!window.confirm(`確定要刪除「${item.title}」？`)) return
    setDeleting(item.id)
    try {
      await deleteAnnouncement(item.id)
      await load()
    } catch (err) {
      console.error('刪除失敗:', err)
    }
    setDeleting(null)
  }

  // ── 新增 ──────────────────────────────────────────────────────────────────
  const handleCreate = async () => {
    if (!form.title.trim() || !form.body.trim()) return
    setSaving(true)
    try {
      const payload = {
        type: form.type,
        title: form.title.trim(),
        body: form.body.trim(),
        is_active: form.is_active,
        show_on_website: form.show_on_website,
        scheduled_at: form.scheduled_at || null,
        tags: form.tags,
      }
      await createAnnouncement(payload)
      setForm({
        type: 'general', title: '', body: '', scheduled_at: '',
        is_active: true, show_on_website: false, tags: [],
      })
      await load()
    } catch (err) {
      console.error('新增失敗:', err)
    }
    setSaving(false)
  }

  // ── 切換標籤選取 ──────────────────────────────────────────────────────────
  const toggleTag = (tagId) => {
    setForm(f => ({
      ...f,
      tags: f.tags.includes(tagId)
        ? f.tags.filter(id => id !== tagId)
        : [...f.tags, tagId],
    }))
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex-1 flex overflow-hidden">
      {/* ── 左欄：公告列表 ───────────────────────────────────────────── */}
      <div className="w-96 bg-white border-r border-gray-100 flex flex-col flex-shrink-0">
        {/* 標頭 */}
        <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2 flex-shrink-0">
          <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
          </svg>
          <span className="text-sm font-semibold text-gray-700">公告列表</span>
          <span className="ml-auto text-xs text-gray-400">{filteredAnnouncements.length} 筆</span>
          {/* 查看前台按鈕 */}
          <a
            href="/announcements"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-600 rounded-lg text-xs font-medium hover:bg-blue-100 transition-colors"
            title="在新視窗開啟前台公告頁"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            前台
          </a>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto">
          {/* 搜尋欄 + 排序控制 */}
          <div className="px-4 py-2 border-b border-gray-100">
            <input
              type="text"
              placeholder="搜尋公告標題、內容..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400 mb-2"
            />
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-gray-400">排序：</span>
              {[
                { field: 'created_at', label: '建立日期' },
                { field: 'title', label: '標題' },
                { field: 'is_active', label: '啟用狀態' },
                { field: 'type', label: '類型' },
              ].map(({ field, label }) => (
                <button key={field} onClick={() => toggleSort(field)}
                  className="text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors flex items-center">
                  {label}<SortIcon field={field} sortField={sortField} sortDir={sortDir} />
                </button>
              ))}
            </div>
          </div>
          {loading ? (
            <div className="flex flex-col items-center justify-center h-32 text-gray-400">
              <div className="w-7 h-7 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mb-3" />
              <span className="text-sm">載入中…</span>
            </div>
          ) : filteredAnnouncements.length === 0 && announcements.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-400 gap-2">
              <div className="text-3xl">📭</div>
              <span className="text-xs">尚無公告</span>
            </div>
          ) : filteredAnnouncements.length === 0 && announcements.length > 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-400 gap-2">
              <div className="text-3xl">🔍</div>
              <span className="text-xs">沒有符合的公告</span>
            </div>
          ) : (
            sortedAnnouncements.map(item => (
              <div
                key={item.id}
                className={`px-4 py-3 border-b border-gray-50 transition-colors ${item.is_active ? '' : 'opacity-50'}`}
              >
                {/* 類型徽章 + 標題列 */}
                <div className="flex items-start gap-2 mb-1">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border flex-shrink-0 ${TYPE_COLORS[item.type] || TYPE_COLORS.general}`}>
                    <span>{TYPE_ICON[item.type] || '📢'}</span>
                    {item.type_display || TYPE_LABELS[item.type] || item.type}
                  </span>
                  <span className="text-sm font-medium text-gray-800 leading-tight">{item.title}</span>
                </div>

                {/* 標籤顯示 */}
                {item.tags_detail && item.tags_detail.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-1.5">
                    {item.tags_detail.map(tag => (
                      <span
                        key={tag.id}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
                        style={{
                          backgroundColor: `${tag.color || '#6366f1'}20`,
                          color: tag.color || '#6366f1',
                        }}
                      >
                        {tag.name}
                      </span>
                    ))}
                  </div>
                )}

                {/* 內容摘要 */}
                <p className="text-xs text-gray-500 line-clamp-2 mb-2">{item.body}</p>

                {/* 狀態指示 */}
                <div className="flex items-center gap-2 mb-2">
                  {item.show_on_website && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-50 text-green-600 rounded-full text-xs">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      前台顯示
                    </span>
                  )}
                  {item.scheduled_at && (
                    <span className="text-xs text-amber-600">
                      ⏰ {fmtTime(item.scheduled_at)}
                    </span>
                  )}
                </div>

                {/* 操作列 */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{fmtTime(item.created_at)}</span>
                  <div className="ml-auto flex items-center gap-2">
                    {/* 前台顯示 Toggle */}
                    <button
                      onClick={() => handleToggleWebsite(item)}
                      disabled={toggling === item.id}
                      title={item.show_on_website ? '隱藏於前台' : '顯示於前台'}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                        item.show_on_website ? 'bg-green-500' : 'bg-gray-300'
                      } ${toggling === item.id ? 'opacity-50' : ''}`}
                    >
                      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
                        item.show_on_website ? 'translate-x-[18px]' : 'translate-x-0.5'
                      }`} />
                    </button>
                    {/* 啟用 Toggle */}
                    <button
                      onClick={() => handleToggle(item)}
                      disabled={toggling === item.id}
                      title={item.is_active ? '停用' : '啟用'}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                        item.is_active ? 'bg-blue-500' : 'bg-gray-300'
                      } ${toggling === item.id ? 'opacity-50' : ''}`}
                    >
                      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
                        item.is_active ? 'translate-x-[18px]' : 'translate-x-0.5'
                      }`} />
                    </button>
                    {/* 刪除 */}
                    <button
                      onClick={() => handleDelete(item)}
                      disabled={deleting === item.id}
                      className="text-gray-300 hover:text-red-400 transition-colors"
                      title="刪除公告"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── 右欄：新增表單 ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto bg-slate-50 p-6">
        <div className="max-w-2xl">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-800">新增公告</h2>
            <button
              onClick={() => setShowTagManager(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              管理標籤
            </button>
          </div>

          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 space-y-4">
            {/* 類型選擇 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">公告類型</label>
              <select
                value={form.type}
                onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {Object.entries(TYPE_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{TYPE_ICON[v]} {l}</option>
                ))}
              </select>
            </div>

            {/* 標題 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                標題 <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={form.title}
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                placeholder="例如：APP 版本更新通知"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 內容 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                內容 <span className="text-red-400">*</span>
              </label>
              <textarea
                value={form.body}
                onChange={e => setForm(f => ({ ...f, body: e.target.value }))}
                rows={4}
                placeholder="輸入公告內容…"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>

            {/* 標籤選擇 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">
                標籤 <span className="text-gray-400 font-normal">（可複選）</span>
              </label>
              {tags.length === 0 ? (
                <p className="text-xs text-gray-400">尚無標籤，請先點擊「管理標籤」新增</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {tags.map(tag => (
                    <button
                      key={tag.id}
                      onClick={() => toggleTag(tag.id)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                        form.tags.includes(tag.id)
                          ? 'ring-2 ring-offset-1'
                          : 'opacity-60 hover:opacity-100'
                      }`}
                      style={{
                        backgroundColor: `${tag.color || '#6366f1'}20`,
                        color: tag.color || '#6366f1',
                      }}
                    >
                      {tag.name}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 排程時間 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                排程時間
                <span className="ml-2 text-gray-400 font-normal">（選填）</span>
              </label>
              <input
                type="datetime-local"
                value={form.scheduled_at}
                onChange={e => setForm(f => ({ ...f, scheduled_at: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 開關設定 */}
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                    form.is_active ? 'bg-blue-500' : 'bg-gray-300'
                  }`}
                >
                  <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    form.is_active ? 'translate-x-6' : 'translate-x-1'
                  }`} />
                </button>
                <span className="text-sm text-gray-600">
                  {form.is_active ? '啟用' : '停用'}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setForm(f => ({ ...f, show_on_website: !f.show_on_website }))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                    form.show_on_website ? 'bg-green-500' : 'bg-gray-300'
                  }`}
                >
                  <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    form.show_on_website ? 'translate-x-6' : 'translate-x-1'
                  }`} />
                </button>
                <span className="text-sm text-gray-600">
                  {form.show_on_website ? '前台顯示' : '僅後台'}
                </span>
              </div>
            </div>

            {/* 送出 */}
            <div className="pt-2">
              <button
                onClick={handleCreate}
                disabled={saving || !form.title.trim() || !form.body.trim()}
                className="w-full bg-blue-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium
                           hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? '新增中…' : '✚ 新增公告'}
              </button>
            </div>
          </div>

          {/* 說明 */}
          <div className="mt-4 bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-xs text-blue-700 space-y-1">
            <p className="font-semibold">📋 功能說明</p>
            <p>• <strong>啟用</strong>：APP 啟動時會以 TTS 語音播報公告</p>
            <p>• <strong>前台顯示</strong>：公告會顯示於網站前台公告頁面</p>
            <p>• <strong>標籤</strong>：用於前台公告頁面篩選功能</p>
            <p>• 點擊列表右上角「前台」按鈕可預覽前台公告頁面</p>
          </div>
        </div>
      </div>

      {/* 標籤管理 Modal */}
      {showTagManager && (
        <TagManagerModal
          tags={tags}
          onClose={() => setShowTagManager(false)}
          onCreate={handleCreateTag}
          onUpdate={handleUpdateTag}
          onDelete={handleDeleteTag}
        />
      )}
    </div>
  )
}
