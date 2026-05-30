import { useState, useEffect } from 'react'
import { getActivityLogs } from '../api'

const ACTION_STYLE = {
  create: 'bg-emerald-100 text-emerald-700',
  update: 'bg-blue-100 text-blue-700',
  delete: 'bg-red-100 text-red-600',
}

const ACTION_FILTERS = [
  { value: '',       label: '全部' },
  { value: 'create', label: '新增' },
  { value: 'update', label: '修改' },
  { value: 'delete', label: '刪除' },
]

function formatTime(iso) {
  const d = new Date(iso)
  return d.toLocaleString('zh-TW', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

/** 排序圖示元件 */
function SortIcon({ field, sortField, sortDir }) {
  if (sortField !== field) return <span className="text-gray-300 ml-0.5">↕</span>
  return sortDir === 'asc' ? <span className="text-blue-500 ml-0.5">↑</span> : <span className="text-blue-500 ml-0.5">↓</span>
}

export default function ActivityLogs() {
  const [logs, setLogs]       = useState([])
  const [filter, setFilter]   = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortField, setSortField] = useState('timestamp')  // 排序欄位
  const [sortDir, setSortDir]     = useState('desc')       // 預設最新在前

  // 排序切換函式
  function toggleSort(field) {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const load = (action) => {
    setLoading(true)
    getActivityLogs(action)
      .then(r => setLogs(r.data))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(filter) }, [filter])

  // 搜尋篩選：比對操作者、動作、類型、對象
  const filteredLogs = logs.filter(log => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return (
      (log.user && log.user.toLowerCase().includes(term)) ||
      (log.action_display && log.action_display.toLowerCase().includes(term)) ||
      (log.resource_type && log.resource_type.toLowerCase().includes(term)) ||
      (log.resource_name && log.resource_name.toLowerCase().includes(term))
    )
  })

  // 排序後的日誌
  const sortedLogs = [...filteredLogs].sort((a, b) => {
    const aVal = a[sortField] ?? ''
    const bVal = b[sortField] ?? ''
    let cmp
    if (sortField === 'timestamp') {
      cmp = new Date(aVal) - new Date(bVal)
    } else {
      cmp = String(aVal).localeCompare(String(bVal), 'zh-TW')
    }
    return sortDir === 'asc' ? cmp : -cmp
  })

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* 頂部工具列 */}
      <div className="bg-white border-b border-gray-100 px-6 py-3 flex items-center gap-4 flex-shrink-0">
        <h2 className="text-sm font-bold text-gray-700">後台操作日誌</h2>
        <div className="flex gap-1.5 ml-auto">
          {ACTION_FILTERS.map(f => (
            <button key={f.value} onClick={() => setFilter(f.value)}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                filter === f.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}>
              {f.label}
            </button>
          ))}
          <button onClick={() => load(filter)}
            className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 ml-2">
            重新整理
          </button>
        </div>
      </div>

      {/* 搜尋欄 */}
      <div className="bg-white border-b border-gray-100 px-6 py-2 flex-shrink-0">
        <input
          type="text"
          placeholder="搜尋操作者、動作、類型或對象..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400"
        />
      </div>

      {/* 日誌列表 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mb-3" />
            <span className="text-sm">載入中...</span>
          </div>
        ) : filteredLogs.length === 0 && logs.length === 0 ? (
          <div className="text-center text-gray-400 text-sm py-12">
            <div className="text-3xl mb-2">📋</div>
            <p>尚無操作記錄</p>
          </div>
        ) : filteredLogs.length === 0 && logs.length > 0 ? (
          <div className="text-center text-gray-400 text-sm py-12">
            <div className="text-3xl mb-2">🔍</div>
            <p>沒有符合的操作記錄</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide w-36">
                    <button onClick={() => toggleSort('timestamp')} className="flex items-center hover:text-gray-600 transition-colors">
                      時間<SortIcon field="timestamp" sortField={sortField} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide w-24">
                    <button onClick={() => toggleSort('user')} className="flex items-center hover:text-gray-600 transition-colors">
                      操作者<SortIcon field="user" sortField={sortField} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide w-16">
                    <button onClick={() => toggleSort('action')} className="flex items-center hover:text-gray-600 transition-colors">
                      動作<SortIcon field="action" sortField={sortField} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide w-24">類型</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">對象</th>
                </tr>
              </thead>
              <tbody>
                {sortedLogs.map((log, i) => (
                  <tr key={log.id}
                    className={`border-b border-gray-50 hover:bg-gray-50 transition-colors ${
                      i % 2 === 0 ? '' : 'bg-gray-50/30'
                    }`}>
                    <td className="px-4 py-2.5 text-gray-500 text-xs font-mono whitespace-nowrap">
                      {formatTime(log.timestamp)}
                    </td>
                    <td className="px-4 py-2.5 text-gray-700 font-medium truncate max-w-[96px]">
                      {log.user}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ACTION_STYLE[log.action] || 'bg-gray-100 text-gray-600'}`}>
                        {log.action_display}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-600 text-xs">{log.resource_type}</td>
                    <td className="px-4 py-2.5 text-gray-800 truncate max-w-xs">{log.resource_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
