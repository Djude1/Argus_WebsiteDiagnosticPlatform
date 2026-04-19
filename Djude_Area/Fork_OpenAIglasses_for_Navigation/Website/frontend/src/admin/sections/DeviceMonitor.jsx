/**
 * 裝置監控面板
 * 即時顯示 4 台 AI 智慧眼鏡裝置的運行狀態
 * 透過 nginx 代理查詢各裝置 FastAPI 的 /api/debug_status
 */
import { useState, useEffect, useRef, useCallback } from 'react'

const DEVICE_COUNT = 4
const POLL_INTERVAL = 3000 // 3 秒輪詢一次

// 狀態中文對照
const STATE_LABELS = {
  IDLE: '待機',
  CHAT: '對話中',
  BLINDPATH_NAV: '盲道導航',
  SEEKING_CROSSWALK: '尋找斑馬線',
  WAIT_TRAFFIC_LIGHT: '等待紅綠燈',
  CROSSING: '過馬路中',
  SEEKING_NEXT_BLINDPATH: '尋找下一段盲道',
  RECOVERY: '恢復中',
  TRAFFIC_LIGHT_DETECTION: '紅綠燈偵測',
  ITEM_SEARCH: '物品搜尋',
  '未初始化': '未初始化',
}

// 狀態顏色對照
const STATE_COLORS = {
  IDLE: 'text-gray-400',
  CHAT: 'text-blue-400',
  BLINDPATH_NAV: 'text-green-400',
  SEEKING_CROSSWALK: 'text-yellow-400',
  WAIT_TRAFFIC_LIGHT: 'text-red-400',
  CROSSING: 'text-orange-400',
  TRAFFIC_LIGHT_DETECTION: 'text-purple-400',
  ITEM_SEARCH: 'text-cyan-400',
}

function DeviceCard({ deviceNum, status, isLoading }) {
  const isOnline = status !== null && !status.error
  const isOffline = status === null || status.error

  return (
    <div className={`rounded-2xl border-2 transition-all duration-300 ${
      isOnline
        ? 'border-green-500/30 bg-gradient-to-br from-slate-800 to-slate-900 shadow-lg shadow-green-900/10'
        : 'border-slate-700/50 bg-gradient-to-br from-slate-800/60 to-slate-900/60 opacity-60'
    }`}>
      {/* 卡片標題列 */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/50">
        <div className="flex items-center gap-3">
          {/* 狀態指示燈 */}
          <div className={`relative w-3 h-3 rounded-full ${isOnline ? 'bg-green-400' : 'bg-slate-600'}`}>
            {isOnline && (
              <span className="absolute inset-0 rounded-full bg-green-400 animate-ping opacity-40" />
            )}
          </div>
          <div>
            <h3 className="text-white font-bold text-base">
              裝置 {deviceNum}
            </h3>
            <p className="text-xs text-slate-500">
              {isOnline ? status.device_id || `glasses_0${deviceNum}` : '未連線'}
            </p>
          </div>
        </div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
          isOnline
            ? 'bg-green-500/20 text-green-400'
            : 'bg-slate-700 text-slate-500'
        }`}>
          {isLoading ? '查詢中...' : isOnline ? 'ONLINE' : 'OFFLINE'}
        </span>
      </div>

      {/* 卡片內容 */}
      {isOnline ? (
        <div className="px-5 py-4 space-y-4">
          {/* 導航狀態 */}
          <div>
            <label className="text-xs text-slate-500 uppercase tracking-wider font-semibold">導航狀態</label>
            <p className={`text-lg font-bold mt-0.5 ${STATE_COLORS[status.orchestrator_state] || 'text-slate-300'}`}>
              {STATE_LABELS[status.orchestrator_state] || status.orchestrator_state}
            </p>
          </div>

          {/* 連線狀態格子 */}
          <div className="grid grid-cols-2 gap-2">
            <StatusBadge
              label="相機"
              ok={status.esp32_camera_connected}
            />
            <StatusBadge
              label="音訊"
              ok={status.esp32_audio_connected}
            />
            <StatusBadge
              label="GPU"
              ok={status.gpu_available}
            />
            <StatusBadge
              label="YOLO"
              ok={status.yolo_seg_loaded}
            />
          </div>

          {/* 詳細數值 */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <InfoRow label="觀看者" value={status.camera_viewer_count} />
            <InfoRow label="UI 客戶端" value={status.ui_client_count} />
            <InfoRow label="運行時間" value={status.uptime} />
            <InfoRow label="Port" value={status.server_port} />
          </div>

          {/* 最後辨識 */}
          {status.last_final && (
            <div className="mt-2 px-3 py-2 bg-slate-700/40 rounded-lg">
              <label className="text-xs text-slate-500">最近辨識</label>
              <p className="text-sm text-slate-300 mt-0.5 truncate">{status.last_final}</p>
            </div>
          )}
        </div>
      ) : (
        <div className="px-5 py-8 text-center">
          <div className="text-3xl mb-2">📵</div>
          <p className="text-slate-500 text-sm">裝置未啟動或無法連線</p>
          <p className="text-slate-600 text-xs mt-1">Port {8080 + deviceNum}</p>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ label, ok }) {
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium ${
      ok
        ? 'bg-green-500/10 text-green-400'
        : 'bg-slate-700/50 text-slate-500'
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-green-400' : 'bg-slate-600'}`} />
      {label}
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-300 font-medium">{value ?? '-'}</span>
    </div>
  )
}

export default function DeviceMonitor() {
  const [devices, setDevices] = useState(() =>
    Array.from({ length: DEVICE_COUNT }, () => null)
  )
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState('all') // 'all' | 'online' | 'offline'
  const timerRef = useRef(null)

  const fetchAll = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true)
    const results = await Promise.allSettled(
      Array.from({ length: DEVICE_COUNT }, (_, i) =>
        fetch(`/api/devices/${i + 1}/status`, { signal: AbortSignal.timeout(4000) })
          .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.json()
          })
      )
    )

    setDevices(results.map(r =>
      r.status === 'fulfilled' ? r.value : { error: true }
    ))
    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    fetchAll()
    timerRef.current = setInterval(fetchAll, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [fetchAll])

  // 統計
  const onlineCount = devices.filter(d => d && !d.error).length
  const navigatingCount = devices.filter(d =>
    d && !d.error && !['IDLE', 'CHAT', '未初始化'].includes(d.orchestrator_state)
  ).length

  // 篩選裝置
  const filteredDevices = devices.map((status, i) => ({ status, index: i })).filter(({ status }) => {
    const isOnline = status !== null && !status.error
    if (filter === 'online') return isOnline
    if (filter === 'offline') return !isOnline
    return true
  })

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-gradient-to-br from-slate-900 to-slate-950">
      {/* 頂部標題 */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">裝置監控中心</h1>
            <p className="text-slate-400 text-sm mt-1">即時監控所有 AI 智慧眼鏡裝置運行狀態</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-green-400">{onlineCount}</div>
              <div className="text-xs text-slate-500">上線</div>
            </div>
            <div className="w-px h-8 bg-slate-700" />
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-400">{navigatingCount}</div>
              <div className="text-xs text-slate-500">導航中</div>
            </div>
            <div className="w-px h-8 bg-slate-700" />
            <div className="text-center">
              <div className="text-2xl font-bold text-slate-500">{DEVICE_COUNT - onlineCount}</div>
              <div className="text-xs text-slate-500">離線</div>
            </div>
            <div className="w-px h-8 bg-slate-700" />
            {/* 篩選按鈕 */}
            <div className="flex items-center gap-1 text-xs">
              {[
                { key: 'all', label: '全部' },
                { key: 'online', label: '上線' },
                { key: 'offline', label: '離線' },
              ].map(f => (
                <button key={f.key} onClick={() => setFilter(f.key)}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    filter === f.key ? 'bg-slate-600 text-white' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
                  }`}
                >{f.label}</button>
              ))}
            </div>
            {/* 手動刷新按鈕 */}
            <button
              onClick={() => fetchAll(true)}
              disabled={refreshing}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors disabled:opacity-50"
            >
              <svg className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {refreshing ? '更新中…' : '重新整理'}
            </button>
          </div>
        </div>
      </div>

      {/* 裝置卡片 2x2 格子 */}
      {filteredDevices.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-3">
            {filter === 'online' ? '📡' : filter === 'offline' ? '✅' : '📭'}
          </div>
          <p className="text-slate-400 text-sm">
            {filter === 'online' ? '沒有上線的裝置' : filter === 'offline' ? '所有裝置都在線上' : '沒有裝置'}
          </p>
          <p className="text-slate-600 text-xs mt-1">
            {filter === 'online' ? '請確認裝置已啟動並連接網路' : ''}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {filteredDevices.map(({ status, index }) => (
            <DeviceCard
              key={index}
              deviceNum={index + 1}
              status={status}
              isLoading={loading}
            />
          ))}
        </div>
      )}

      {/* 說明卡片 */}
      <div className="mt-6 p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
        <h3 className="text-sm font-semibold text-slate-400 mb-2">使用說明</h3>
        <ul className="text-xs text-slate-500 space-y-1">
          <li>• 啟動多台裝置：在伺服器執行 <code className="text-slate-400 bg-slate-700/50 px-1 rounded">uv run python start_multi_device.py --count 4</code></li>
          <li>• APP 連線設定：伺服器位址填入 <code className="text-slate-400 bg-slate-700/50 px-1 rounded">https://aiglasses.qzz.io/device/N/</code>（N = 裝置編號 1~4）</li>
          <li>• 每台裝置完全獨立，擁有各自的音訊、導航和 AI 對話管線</li>
          <li>• 面板每 {POLL_INTERVAL / 1000} 秒自動更新一次</li>
        </ul>
      </div>
    </div>
  )
}
