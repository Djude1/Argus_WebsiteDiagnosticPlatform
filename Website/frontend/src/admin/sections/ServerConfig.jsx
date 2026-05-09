/**
 * APP 伺服器設定管理
 * - 管理員在後台設定 AI 伺服器連線 URL
 * - APP 啟動時自動從 /api/content/app-config/ 讀取此設定
 */
import { useState, useEffect, useCallback } from 'react'
import { getContentSection, updateContentSection } from '../api'

// URL 驗證函式
function isValidUrl(str) {
  if (!str.trim()) return true // 允許空值
  try {
    const url = new URL(str)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export default function ServerConfig() {
  const [serverUrl, setServerUrl] = useState('')
  const [note, setNote]           = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState(false)
  const [message, setMessage]     = useState(null) // { type: 'success'|'error', text }
  const [urlError, setUrlError]   = useState('') // URL 驗證錯誤訊息
  const [savedAt, setSavedAt]     = useState(null) // 儲存成功時間戳

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getContentSection('app-config')
      setServerUrl(res.data.server_url ?? '')
      setNote(res.data.note ?? '')
      setUpdatedAt(res.data.updated_at ?? null)
    } catch {
      setMessage({ type: 'error', text: '載入失敗，請確認登入狀態' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    // URL 格式驗證
    if (!isValidUrl(serverUrl)) {
      setUrlError('請輸入有效的 URL（需以 http:// 或 https:// 開頭）')
      return
    }
    setUrlError('')
    setSaving(true)
    setMessage(null)
    try {
      const res = await updateContentSection('app-config', {
        server_url: serverUrl.trim(),
        note:       note.trim(),
      })
      setServerUrl(res.data.server_url ?? '')
      setNote(res.data.note ?? '')
      setUpdatedAt(res.data.updated_at ?? null)
      setMessage({ type: 'success', text: '儲存成功！APP 下次啟動將套用新設定' })
      setSavedAt(Date.now())
      // 3 秒後自動隱藏成功提示
      setTimeout(() => setSavedAt(null), 3000)
    } catch {
      setMessage({ type: 'error', text: '儲存失敗，請確認權限或網路' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="text-center">
          <div className="relative w-10 h-10 mx-auto mb-3">
            <div className="absolute inset-0 border-2 border-gray-200 rounded-full" />
            <div className="absolute inset-0 border-2 border-blue-500 rounded-full border-t-transparent animate-spin" />
          </div>
          <p className="text-sm">載入設定中…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* 標題 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">APP 伺服器設定</h1>
        <p className="text-sm text-slate-500 mt-1">
          設定 AI 眼鏡 APP 連線的伺服器位址。APP 啟動時會自動從網站讀取此 URL。
        </p>
        {updatedAt && (
          <p className="text-xs text-slate-400 mt-1">
            最後更新：{new Date(updatedAt).toLocaleString('zh-TW')}
          </p>
        )}
      </div>

      {/* 說明區塊 */}
      <div className="mb-6 p-4 rounded-xl bg-blue-50 border border-blue-200 text-sm text-blue-800 space-y-1">
        <div className="font-semibold mb-1">📱 運作流程</div>
        <div>1. 管理員在此設定 AI 伺服器 URL（例如 Cloudflare Tunnel 位址）</div>
        <div>2. APP 在設定頁填入網站網址（例如 <code className="bg-blue-100 px-1 rounded">https://aiglasses.qzz.io</code>）</div>
        <div>3. APP 啟動時自動呼叫 <code className="bg-blue-100 px-1 rounded">/api/content/app-config/</code> 取得此 URL</div>
        <div>4. APP 使用此 URL 連線 AI 伺服器（WebSocket + HTTP）</div>
      </div>

      {/* 表單 */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-5">

        {/* AI 伺服器 URL */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
            AI 伺服器 URL <span className="text-red-400">*</span>
          </label>
          <input
            type="url"
            value={serverUrl}
            onChange={e => { setServerUrl(e.target.value); setUrlError(''); setMessage(null) }}
            onBlur={() => { if (serverUrl.trim() && !isValidUrl(serverUrl)) setUrlError('請輸入有效的 URL（需以 http:// 或 https:// 開頭）') }}
            placeholder="https://xxxx.trycloudflare.com/GlassesBackstage/"
            className={`w-full border rounded-xl px-4 py-3 text-sm text-gray-800 focus:outline-none focus:ring-1 ${
              urlError ? 'border-red-300 focus:border-red-400 focus:ring-red-200' : 'border-gray-200 focus:border-blue-400 focus:ring-blue-200'
            }`}
          />
          {urlError && (
            <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
              <span>⚠️</span> {urlError}
            </p>
          )}
          <p className="text-xs text-slate-400 mt-1">
            需包含路徑（例如 <code>/GlassesBackstage/</code> 或 <code>/device/1/</code>），WebSocket 才能正確連線
          </p>
        </div>

        {/* 備註 */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
            備註（選填）
          </label>
          <textarea
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={3}
            placeholder="例如：DevTunnel URL，每次重啟需更新；目前為 Cloudflare 固定 Tunnel"
            className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-800 focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200 resize-none"
          />
        </div>

        {/* 訊息提示 */}
        {message && message.type === 'error' && (
          <div className="px-4 py-3 rounded-xl text-sm font-medium bg-red-50 border border-red-200 text-red-700">
            ❌ {message.text}
          </div>
        )}

        {/* 儲存按鈕 + 成功提示 */}
        <div className="flex items-center justify-end gap-3">
          {savedAt && (
            <span className="text-green-500 text-sm font-medium transition-opacity">
              ✓ 已儲存
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={saving || !!urlError}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-300 text-white text-sm font-semibold rounded-xl transition-colors"
          >
            {saving ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                儲存中…
              </span>
            ) : '儲存設定'}
          </button>
        </div>
      </div>

      {/* 目前公開 API */}
      <div className="mt-6 p-4 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-600">
        <div className="font-semibold text-slate-700 mb-2">🔗 公開 API 端點</div>
        <div className="font-mono text-xs bg-white border border-slate-200 rounded-lg px-3 py-2 break-all">
          GET /api/content/app-config/
        </div>
        <p className="text-xs text-slate-400 mt-2">此端點無需認證，APP 可直接呼叫取得 server_url</p>
      </div>
    </div>
  )
}
