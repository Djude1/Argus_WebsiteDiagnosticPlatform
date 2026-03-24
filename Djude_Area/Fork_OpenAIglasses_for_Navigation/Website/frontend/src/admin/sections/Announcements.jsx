/**
 * APP 公告管理
 * 管理員可新增、啟用/停用、刪除發送給視障 APP 使用者的通知訊息
 * APP 啟動時會透過 TTS 播報所有啟用中的公告
 */
import { useState, useEffect, useCallback } from 'react'
import {
  getAnnouncements, createAnnouncement,
  updateAnnouncement, deleteAnnouncement,
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

// ── 範本預填 ────────────────────────────────────────────────────────────────
const TEMPLATES = [
  {
    type:  'version_update',
    title: 'APP 版本更新通知',
    body:  '新版本已發布，請至官方網站下載最新版本以獲得最佳使用體驗。如有任何問題，歡迎聯絡我們。',
  },
  {
    type:  'maintenance',
    title: '系統維護公告',
    body:  '系統將於 xx月xx日 xx:xx 進行例行維護，預計維護時間為 2 小時，期間部分功能可能暫時無法使用，敬請見諒。',
  },
  {
    type:  'new_feature',
    title: '新功能上線',
    body:  '我們新增了新功能，歡迎您在 APP 中體驗使用。如有任何問題或建議，歡迎聯絡我們。',
  },
  {
    type:  'general',
    title: '重要通知',
    body:  '（在此輸入通知內容）',
  },
]

// ── 時間格式化 ──────────────────────────────────────────────────────────────
function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

// ── 主元件 ──────────────────────────────────────────────────────────────────
export default function Announcements() {
  const [announcements, setAnnouncements] = useState([])
  const [loading,  setLoading]  = useState(false)
  const [saving,   setSaving]   = useState(false)
  const [toggling, setToggling] = useState(null)   // 正在 toggle 的 id
  const [deleting, setDeleting] = useState(null)   // 正在刪除的 id
  const [form, setForm] = useState({
    type: 'general', title: '', body: '', scheduled_at: '', is_active: true,
  })

  // ── 讀取列表 ──────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await getAnnouncements()
      setAnnouncements(r.data)
    } catch {
      // 靜默失敗
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  // ── 套用範本 ──────────────────────────────────────────────────────────────
  const applyTemplate = (tpl) => {
    setForm(f => ({ ...f, type: tpl.type, title: tpl.title, body: tpl.body }))
  }

  // ── 即時切換啟用狀態 ──────────────────────────────────────────────────────
  const handleToggle = async (item) => {
    setToggling(item.id)
    try {
      await updateAnnouncement(item.id, { is_active: !item.is_active })
      await load()
    } catch {
      // 靜默失敗
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
    } catch {
      // 靜默失敗
    }
    setDeleting(null)
  }

  // ── 新增 ──────────────────────────────────────────────────────────────────
  const handleCreate = async () => {
    if (!form.title.trim() || !form.body.trim()) return
    setSaving(true)
    try {
      const payload = {
        type:         form.type,
        title:        form.title.trim(),
        body:         form.body.trim(),
        is_active:    form.is_active,
        scheduled_at: form.scheduled_at || null,
      }
      await createAnnouncement(payload)
      setForm({ type: 'general', title: '', body: '', scheduled_at: '', is_active: true })
      await load()
    } catch {
      // 靜默失敗
    }
    setSaving(false)
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full overflow-hidden">

      {/* ── 左欄：公告列表 ───────────────────────────────────────────── */}
      <div className="w-96 bg-white border-r border-gray-100 flex flex-col flex-shrink-0">
        {/* 標頭 */}
        <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2 flex-shrink-0">
          <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
          </svg>
          <span className="text-sm font-semibold text-gray-700">公告列表</span>
          <span className="ml-auto text-xs text-gray-400">{announcements.length} 筆</span>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-gray-400 text-sm">載入中…</div>
          ) : announcements.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-400 gap-2">
              <svg className="w-10 h-10 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
              </svg>
              <span className="text-xs">尚無公告</span>
            </div>
          ) : (
            announcements.map(item => (
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
                {/* 內容摘要 */}
                <p className="text-xs text-gray-500 line-clamp-2 mb-2">{item.body}</p>
                {/* 排程時間（若有）*/}
                {item.scheduled_at && (
                  <p className="text-xs text-amber-600 mb-1.5">
                    ⏰ 排程：{fmtTime(item.scheduled_at)}
                  </p>
                )}
                {/* 操作列 */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{fmtTime(item.created_at)}</span>
                  <div className="ml-auto flex items-center gap-2">
                    {/* 啟用 Toggle */}
                    <button
                      onClick={() => handleToggle(item)}
                      disabled={toggling === item.id}
                      title={item.is_active ? '點擊停用' : '點擊啟用'}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                        item.is_active ? 'bg-green-500' : 'bg-gray-300'
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
          <h2 className="text-base font-semibold text-gray-800 mb-4">新增公告</h2>

          {/* 範本按鈕列 */}
          <div className="mb-5">
            <p className="text-xs text-gray-500 mb-2">快速套用範本：</p>
            <div className="flex flex-wrap gap-2">
              {TEMPLATES.map(tpl => (
                <button
                  key={tpl.type}
                  onClick={() => applyTemplate(tpl)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all hover:shadow-sm ${TYPE_COLORS[tpl.type]}`}
                >
                  <span>{TYPE_ICON[tpl.type]}</span>
                  {TYPE_LABELS[tpl.type]}
                </button>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 space-y-4">
            {/* 類型選擇 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">公告類型</label>
              <select
                value={form.type}
                onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 內容 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                內容 <span className="text-red-400">*</span>
                <span className="ml-2 text-gray-400 font-normal">（APP 啟動時 TTS 會完整播報）</span>
              </label>
              <textarea
                value={form.body}
                onChange={e => setForm(f => ({ ...f, body: e.target.value }))}
                rows={4}
                placeholder="輸入要播報給視障使用者的通知內容…"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>

            {/* 排程時間 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                排程時間
                <span className="ml-2 text-gray-400 font-normal">（選填，留空表示立即生效）</span>
              </label>
              <input
                type="datetime-local"
                value={form.scheduled_at}
                onChange={e => setForm(f => ({ ...f, scheduled_at: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 啟用開關 */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                  form.is_active ? 'bg-green-500' : 'bg-gray-300'
                }`}
              >
                <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  form.is_active ? 'translate-x-6' : 'translate-x-1'
                }`} />
              </button>
              <span className="text-sm text-gray-600">
                {form.is_active ? '建立後立即啟用' : '建立後先停用'}
              </span>
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
          <div className="mt-4 bg-amber-50 border border-amber-100 rounded-xl px-4 py-3 text-xs text-amber-700 space-y-1">
            <p className="font-semibold">📱 APP 端播報說明</p>
            <p>• 視障使用者啟動 APP 時，系統自動以 TTS 語音播報所有「啟用中」的公告</p>
            <p>• 多則公告會逐一播報，每則間隔約 3.5 秒</p>
            <p>• 設定排程時間後，只有在到達該時間後公告才會對 APP 可見</p>
            <p>• 需在 APP 設定頁面填入「網站 URL」才能接收公告</p>
          </div>
        </div>
      </div>
    </div>
  )
}
