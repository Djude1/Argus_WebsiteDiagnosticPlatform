import { useState, useEffect } from 'react'
import { getOrders, updateOrder } from '../api'

const STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'pending',   label: '待處理' },
  { value: 'confirmed', label: '已確認' },
  { value: 'shipping',  label: '運送中' },
  { value: 'delivered', label: '已送達' },
  { value: 'cancelled', label: '已取消' },
]

const STATUS_COLORS = {
  pending:   'bg-yellow-100 text-yellow-700',
  confirmed: 'bg-blue-100 text-blue-700',
  shipping:  'bg-purple-100 text-purple-700',
  delivered: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-500',
}

export default function Orders() {
  const [orders, setOrders]       = useState([])
  const [selected, setSelected]   = useState(null)
  const [statusFilter, setFilter] = useState('')
  const [newStatus, setNewStatus] = useState('')
  const [saving, setSaving]       = useState(false)
  const [saved, setSaved]         = useState(false)

  const load = (s) => getOrders(s).then(r => setOrders(r.data.results || r.data))

  useEffect(() => { load(statusFilter) }, [statusFilter])

  const selectOrder = (o) => { setSelected(o); setNewStatus(o.status); setSaved(false) }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await updateOrder(selected.id, { status: newStatus })
      setSelected(res.data)
      setSaved(true)
      load(statusFilter)
    } catch { alert('更新失敗') }
    finally { setSaving(false) }
  }

  return (
    <div className="flex h-full">
      {/* 中欄：訂單清單 */}
      <div className="w-72 bg-white border-r border-gray-100 flex-shrink-0 flex flex-col">
        {/* 狀態篩選 */}
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">訂單管理</h3>
          <select value={statusFilter} onChange={e => setFilter(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:border-blue-400">
            {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        <div className="overflow-y-auto flex-1">
          {orders.length === 0 && (
            <div className="text-center text-gray-400 text-sm py-8">沒有訂單</div>
          )}
          {orders.map(o => (
            <button key={o.id} onClick={() => selectOrder(o)}
              className={`w-full text-left px-4 py-3 border-b border-gray-50 transition-colors ${
                selected?.id === o.id ? 'bg-blue-50 border-r-2 border-blue-600' : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-mono text-gray-700">{o.order_number}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLORS[o.status] || ''}`}>
                  {o.status_display}
                </span>
              </div>
              <div className="text-sm font-medium text-gray-800 truncate">{o.customer_name}</div>
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-xs text-gray-500">{new Date(o.created_at).toLocaleDateString('zh-TW')}</span>
                <span className="text-xs font-semibold text-gray-700">NT${Number(o.total_price).toLocaleString()}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右欄：訂單詳情 */}
      <div className="flex-1 overflow-y-auto bg-white">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <div className="text-4xl mb-2">📋</div>
              <p>請從左側選擇訂單</p>
            </div>
          </div>
        ) : (
          <div className="max-w-xl mx-auto px-8 py-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-gray-800">{selected.order_number}</h2>
              <span className={`text-sm px-3 py-1 rounded-full font-medium ${STATUS_COLORS[selected.status]}`}>
                {selected.status_display}
              </span>
            </div>

            {/* 顧客資訊 */}
            <div className="bg-gray-50 rounded-xl p-5 mb-5 space-y-2">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">顧客資訊</h3>
              {[
                ['姓名', selected.customer_name],
                ['Email', selected.customer_email],
                ['電話', selected.customer_phone],
                ['地址', selected.shipping_address],
              ].map(([l, v]) => (
                <div key={l} className="flex gap-3 text-sm">
                  <span className="text-gray-500 w-12 flex-shrink-0">{l}</span>
                  <span className="text-gray-800">{v}</span>
                </div>
              ))}
            </div>

            {/* 訂單明細 */}
            <div className="bg-gray-50 rounded-xl p-5 mb-5">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">訂單明細</h3>
              {(selected.items || []).map(item => (
                <div key={item.id} className="flex items-center justify-between text-sm py-2 border-b border-gray-200 last:border-0">
                  <span className="text-gray-700">{item.product_name}</span>
                  <span className="text-gray-500">x{item.quantity}</span>
                  <span className="font-medium text-gray-800">NT${Number(item.price * item.quantity).toLocaleString()}</span>
                </div>
              ))}
              <div className="flex justify-between font-semibold text-sm pt-2 mt-1">
                <span>總計</span>
                <span className="text-blue-600">NT${Number(selected.total_price).toLocaleString()}</span>
              </div>
            </div>

            {selected.notes && (
              <div className="bg-gray-50 rounded-xl p-5 mb-5">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">備註</h3>
                <p className="text-sm text-gray-700">{selected.notes}</p>
              </div>
            )}

            {/* 更新狀態 */}
            <div className="bg-blue-50 rounded-xl p-5">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">更新訂單狀態</h3>
              <select value={newStatus} onChange={e => { setNewStatus(e.target.value); setSaved(false) }}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400 mb-3 bg-white">
                {STATUS_OPTIONS.slice(1).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <div className="flex items-center gap-3">
                <button onClick={handleSave} disabled={saving || newStatus === selected.status}
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-semibold rounded-lg transition-colors">
                  {saving ? '更新中...' : '更新狀態'}
                </button>
                {saved && <span className="text-green-600 text-sm">✓ 已更新</span>}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
