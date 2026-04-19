/**
 * 語音偵測中控台
 * 透過 SSE (/device-api/api/speaker_events) 即時接收：
 *   rms          - 音量值（每 150ms）
 *   asr_partial  - ASR 辨識中（片段）
 *   asr_final    - ASR 最終結果
 *   verify       - 聲紋驗證結果
 *   verify_skip  - 音量太低，跳過驗證
 *   silence      - 靜音偵測
 *   enroll_done  - 聲紋錄製完成
 */
import { useState, useEffect, useRef, useCallback } from 'react'

// ── 常數 ─────────────────────────────────────────────────────────────────────
const RMS_MAX        = 4000    // 音量正規化上限
const WAVE_SAMPLES   = 60      // 波形歷史樣本數
const MAX_LOG        = 150     // 事件日誌最大筆數
const MAX_CMD_HIST   = 30      // 指令歷史最大筆數
const MAX_VERIFY_HIST= 10      // 聲紋歷史最大筆數

// SSE 端點（經由 Vite / Nginx proxy 轉發到 FastAPI port 8081）
const SSE_URL = '/device-api/api/speaker_events'

// ── 工具函式 ──────────────────────────────────────────────────────────────────
function tsLabel(ts) {
  if (!ts) return '--'
  return new Date(ts * 1000).toLocaleTimeString('zh-TW', { hour12: false })
}

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)) }

// ── 頂部摘要卡片 ──────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, gradient }) {
  return (
    <div className={`rounded-2xl p-5 text-white relative overflow-hidden bg-gradient-to-br ${gradient}`}>
      <div className="absolute -right-3 -top-3 w-20 h-20 rounded-full bg-white/10" />
      <div className="absolute -right-1 -bottom-5 w-28 h-28 rounded-full bg-white/5" />
      <div className="relative">
        <div className="text-2xl mb-1">{icon}</div>
        <div className="text-3xl font-extrabold tracking-tight">{value}</div>
        <div className="text-sm font-medium opacity-80 mt-0.5">{label}</div>
        {sub && <div className="text-xs opacity-60 mt-1">{sub}</div>}
      </div>
    </div>
  )
}

// ── 音量波形（SVG）───────────────────────────────────────────────────────────
function Waveform({ samples }) {
  const W = 560, H = 70
  if (!samples.length) return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full">
      <line x1={0} y1={H / 2} x2={W} y2={H / 2} stroke="#334155" strokeWidth={1} strokeDasharray="4 4" />
      <text x={W / 2} y={H / 2 + 5} textAnchor="middle" fill="#475569" fontSize={12}>等待音訊…</text>
    </svg>
  )

  const pts = samples.map((v, i) => {
    const x = (i / (WAVE_SAMPLES - 1)) * W
    const norm = clamp(v / RMS_MAX, 0, 1)
    const y = H / 2 - norm * (H / 2 - 4)
    return `${x},${y}`
  })
  const ptsFlip = [...samples].reverse().map((v, i) => {
    const x = ((WAVE_SAMPLES - 1 - i) / (WAVE_SAMPLES - 1)) * W
    const norm = clamp(v / RMS_MAX, 0, 1)
    const y = H / 2 + norm * (H / 2 - 4)
    return `${x},${y}`
  })
  const poly = [...pts, ...ptsFlip].join(' ')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="waveGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.2" />
        </linearGradient>
      </defs>
      <polygon points={poly} fill="url(#waveGrad)" />
      <polyline points={pts.join(' ')} fill="none" stroke="#38bdf8" strokeWidth={1.5} />
    </svg>
  )
}

// ── VU 音量條 ─────────────────────────────────────────────────────────────────
function VuMeter({ rms, peak }) {
  const pct    = clamp(rms  / RMS_MAX, 0, 1) * 100
  const pkPct  = clamp(peak / RMS_MAX, 0, 1) * 100
  const color  = pct > 75 ? '#ef4444' : pct > 45 ? '#f59e0b' : '#22c55e'

  return (
    <div className="relative h-4 bg-slate-700 rounded-full overflow-hidden">
      {/* 分段刻度 */}
      {[25, 50, 75].map(p => (
        <div key={p} className="absolute top-0 bottom-0 w-px bg-slate-600/80 z-10" style={{ left: `${p}%` }} />
      ))}
      {/* 填充 */}
      <div
        className="absolute top-0 left-0 h-full rounded-full transition-all duration-75"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
      {/* 峰值指針 */}
      <div
        className="absolute top-0 h-full w-0.5 bg-white/80 rounded-full transition-all duration-300"
        style={{ left: `${pkPct}%` }}
      />
    </div>
  )
}

// ── 聲紋相似度量表 ────────────────────────────────────────────────────────────
function SimilarityGauge({ similarity, threshold, match }) {
  const pct   = clamp(similarity, 0, 1) * 100
  const thPct = clamp(threshold, 0, 1) * 100
  const color = match ? '#22c55e' : '#ef4444'

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-gray-500">
        <span>相似度</span>
        <span className="font-mono">{(similarity * 100).toFixed(1)}%</span>
      </div>
      <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden">
        {/* 門檻線 */}
        <div
          className="absolute top-0 h-full w-0.5 bg-amber-400 z-10"
          style={{ left: `${thPct}%` }}
        />
        <div
          className="absolute top-0 left-0 h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-400">
        <span>0%</span>
        <span className="text-amber-500">門檻 {(threshold * 100).toFixed(0)}%</span>
        <span>100%</span>
      </div>
    </div>
  )
}

// ── 事件日誌列 ────────────────────────────────────────────────────────────────
function LogRow({ entry }) {
  const { type, text, time } = entry
  const styles = {
    asr_final:   { badge: 'bg-green-100 text-green-700', dot: 'bg-green-500', text: 'text-gray-800 font-medium' },
    asr_partial: { badge: 'bg-gray-100 text-gray-500',   dot: 'bg-gray-400',  text: 'text-gray-500 italic' },
    verify:      { badge: 'bg-blue-100 text-blue-700',   dot: 'bg-blue-500',  text: 'text-gray-700' },
    verify_skip: { badge: 'bg-slate-100 text-slate-500', dot: 'bg-slate-400', text: 'text-gray-400' },
    silence:     { badge: 'bg-slate-100 text-slate-500', dot: 'bg-slate-300', text: 'text-gray-400' },
    enroll_done: { badge: 'bg-indigo-100 text-indigo-700',dot:'bg-indigo-500',text: 'text-gray-700' },
  }
  const labels = {
    asr_final:   'ASR 結果',
    asr_partial: 'ASR 辨識中',
    verify:      '聲紋驗證',
    verify_skip: '跳過驗證',
    silence:     '靜音',
    enroll_done: '錄製完成',
  }
  const s = styles[type] || { badge: 'bg-gray-100 text-gray-500', dot: 'bg-gray-400', text: 'text-gray-500' }

  return (
    <div className="flex items-start gap-2.5 py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-xs text-gray-400 font-mono flex-shrink-0 w-16 pt-0.5">{time}</span>
      <span className={`text-xs px-1.5 py-0.5 rounded-md font-medium flex-shrink-0 ${s.badge}`}>
        {labels[type] || type}
      </span>
      <span className={`text-sm leading-snug flex-1 min-w-0 break-words ${s.text}`}>{text}</span>
    </div>
  )
}

// ── Toggle 開關 ───────────────────────────────────────────────────────────────
function Toggle({ label, enabled, onChange, accent = 'bg-blue-500' }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer group">
      <div
        onClick={onChange}
        className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${enabled ? accent : 'bg-gray-300'}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${enabled ? 'translate-x-5' : ''}`} />
      </div>
      <span className="text-sm text-gray-600 group-hover:text-gray-900 select-none">{label}</span>
    </label>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// 主元件
// ════════════════════════════════════════════════════════════════════════════
export default function VoiceDetection() {
  // 連線狀態
  const [sseConnected,  setSseConnected]  = useState(false)
  const [serverOnline,  setServerOnline]  = useState(null)   // null=檢查中

  // 即時音量
  const [rms,           setRms]           = useState(0)
  const [rmsPeak,       setRmsPeak]       = useState(0)
  const [waveHistory,   setWaveHistory]   = useState([])
  const waveRef = useRef([])

  // ASR
  const [asrPartial,    setAsrPartial]    = useState('')
  const [asrFinal,      setAsrFinal]      = useState('')
  const [cmdHistory,    setCmdHistory]    = useState([])   // [{text, time}]

  // 聲紋
  const [lastVerify,    setLastVerify]    = useState(null) // {match,similarity,threshold,time}
  const [verifyHistory, setVerifyHistory] = useState([])   // [{match,similarity,time}]

  // 事件日誌
  const [eventLog,      setEventLog]      = useState([])

  // 統計
  const [stats, setStats] = useState({ cmds: 0, verifyTotal: 0, verifyMatch: 0 })

  // 控制項
  const [speakerVerify, setSpeakerVerify] = useState(false)
  const [bypassWake,    setBypassWake]    = useState(false)
  const [recording,     setRecording]     = useState(false)
  const [ctrlBusy,      setCtrlBusy]      = useState(false)

  const sseRef    = useRef(null)
  const logEndRef = useRef(null)

  // ── 事件處理 ────────────────────────────────────────────────────────────
  const handleEvent = useCallback((data) => {
    const { type, ts } = data
    const time = tsLabel(ts)

    if (type === 'rms') {
      const v = clamp(data.rms, 0, RMS_MAX * 1.5)
      setRms(v)
      setRmsPeak(prev => v > prev ? v : prev * 0.96)
      waveRef.current = [...waveRef.current.slice(-(WAVE_SAMPLES - 1)), v]
      setWaveHistory([...waveRef.current])
      return
    }

    if (type === 'asr_partial') {
      setAsrPartial(data.text || '')
      return
    }

    if (type === 'asr_final') {
      const text = data.text || ''
      setAsrPartial('')
      setAsrFinal(text)
      setCmdHistory(prev => [{ text, time }, ...prev].slice(0, MAX_CMD_HIST))
      setStats(s => ({ ...s, cmds: s.cmds + 1 }))
      setEventLog(prev => [{ type, text, time }, ...prev].slice(0, MAX_LOG))
      return
    }

    if (type === 'verify') {
      const entry = { match: data.match, similarity: data.similarity ?? 0, threshold: data.threshold ?? 0.75, time }
      setLastVerify(entry)
      setVerifyHistory(prev => [entry, ...prev].slice(0, MAX_VERIFY_HIST))
      setStats(s => ({ ...s, verifyTotal: s.verifyTotal + 1, verifyMatch: s.verifyMatch + (data.match ? 1 : 0) }))
      const text = `相似度 ${(entry.similarity * 100).toFixed(1)}%　${data.match ? '✓ 通過' : '✗ 不符'}`
      setEventLog(prev => [{ type, text, time }, ...prev].slice(0, MAX_LOG))
      return
    }

    // 其他事件 → 加入日誌
    const textMap = {
      verify_skip: '音量過低，跳過聲紋驗證',
      silence:     '偵測到靜音',
      enroll_done: '聲紋錄製完成',
    }
    const text = textMap[type] || type
    setEventLog(prev => [{ type, text, time }, ...prev].slice(0, MAX_LOG))
  }, [])

  // ── SSE 連線 ────────────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (sseRef.current) sseRef.current.close()

    const es = new EventSource(SSE_URL)
    sseRef.current = es

    es.onopen  = () => setSseConnected(true)
    es.onerror = () => { setSseConnected(false) }
    es.onmessage = (e) => {
      try { handleEvent(JSON.parse(e.data)) } catch {}
    }
  }, [handleEvent])

  useEffect(() => {
    // 檢查 FastAPI 伺服器健康狀態
    fetch('/device-api/api/health')
      .then(r => setServerOnline(r.ok))
      .catch(() => setServerOnline(false))

    connect()
    return () => { if (sseRef.current) sseRef.current.close() }
  }, [connect])

  // 自動捲動日誌
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [eventLog.length])

  // ── 控制 API ────────────────────────────────────────────────────────────
  async function devicePost(path) {
    try {
      const token = localStorage.getItem('device_access') || ''
      await fetch(`/device-api${path}`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
    } catch {}
  }

  async function toggleSpeakerVerify() {
    if (ctrlBusy) return
    setCtrlBusy(true)
    await devicePost(`/api/speaker_verify_toggle?enabled=${!speakerVerify}`)
    setSpeakerVerify(v => !v)
    setCtrlBusy(false)
  }

  async function toggleBypassWake() {
    if (ctrlBusy) return
    setCtrlBusy(true)
    await devicePost(`/api/bypass_wake?enabled=${!bypassWake}`)
    setBypassWake(v => !v)
    setCtrlBusy(false)
  }

  async function toggleRecording() {
    if (ctrlBusy) return
    setCtrlBusy(true)
    if (!recording) {
      await devicePost('/api/debug_record/start')
      setRecording(true)
    } else {
      await devicePost('/api/debug_record/stop')
      setRecording(false)
    }
    setCtrlBusy(false)
  }

  // ── 衍生統計值 ─────────────────────────────────────────────────────────
  const verifyRate = stats.verifyTotal > 0
    ? Math.round((stats.verifyMatch / stats.verifyTotal) * 100)
    : null
  const rmsNorm   = Math.round(clamp(rms / RMS_MAX, 0, 1) * 100)

  // ════════════════════════════════════════════════════════════════════════
  // Render
  // ════════════════════════════════════════════════════════════════════════
  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-slate-50">

      {/* ── 頂部標題列 ──────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">🎙 語音偵測中控台</h1>
          <p className="text-xs text-gray-400 mt-0.5">即時監控 ASR 辨識、音量、聲紋驗證事件</p>
        </div>
          {/* 連線狀態 */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs">
              {serverOnline === null ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-gray-400 animate-pulse" />
                  <span className="text-gray-400">伺服器檢查中…</span>
                </>
              ) : (
                <>
                  <span className={`w-2 h-2 rounded-full ${serverOnline ? 'bg-green-500' : 'bg-red-400'}`} />
                  <span className={serverOnline ? 'text-green-600' : 'text-red-500'}>
                    {serverOnline ? 'FastAPI 正常' : 'FastAPI 離線'}
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className={`w-2 h-2 rounded-full ${sseConnected ? 'bg-green-500 animate-pulse' : 'bg-red-400'}`} />
              <span className={sseConnected ? 'text-green-600 font-medium' : 'text-red-500'}>
                {sseConnected ? 'SSE 已連線' : 'SSE 未連線'}
              </span>
            </div>
            {!sseConnected && serverOnline !== null && (
              <button
                onClick={connect}
                className="text-xs bg-blue-50 hover:bg-blue-100 text-blue-600 px-3 py-1.5 rounded-lg font-medium transition-colors"
              >
                重新連線
              </button>
            )}
          </div>
      </div>

      {/* ── 可捲動主體 ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6 space-y-5">

        {/* ── 摘要卡片 ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon="🗣️"
            label="今日辨識指令"
            value={stats.cmds}
            gradient="from-blue-500 to-blue-700"
          />
          <StatCard
            icon="🔊"
            label="即時音量"
            value={`${rmsNorm}%`}
            sub={`RMS ${Math.round(rms)}`}
            gradient={rmsNorm > 75 ? 'from-red-500 to-red-700' : rmsNorm > 40 ? 'from-amber-500 to-orange-600' : 'from-emerald-500 to-green-700'}
          />
          <StatCard
            icon="🔐"
            label="聲紋驗證次數"
            value={stats.verifyTotal}
            gradient="from-violet-500 to-purple-700"
          />
          <StatCard
            icon="✅"
            label="聲紋通過率"
            value={verifyRate !== null ? `${verifyRate}%` : '—'}
            sub={verifyRate !== null ? `${stats.verifyMatch} / ${stats.verifyTotal} 筆通過` : '尚無驗證資料'}
            gradient={verifyRate === null ? 'from-slate-400 to-slate-600' : verifyRate >= 70 ? 'from-teal-500 to-cyan-700' : 'from-orange-500 to-red-600'}
          />
        </div>

        {/* ── 中間兩欄 ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">

          {/* 左欄：音訊視覺化 + ASR（佔 2/3） */}
          <div className="xl:col-span-2 space-y-4">

            {/* 音量波形 */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-gray-700">即時音量波形</h2>
                <span className="text-xs text-gray-400 font-mono">最近 {WAVE_SAMPLES} 個取樣（每 150ms）</span>
              </div>
              <div className="h-[70px] bg-slate-900 rounded-xl overflow-hidden mb-3">
                <Waveform samples={waveHistory} />
              </div>
              <VuMeter rms={rms} peak={rmsPeak} />
              <div className="flex justify-between text-xs text-gray-400 mt-1.5 px-0.5">
                <span>靜音</span>
                <span className="text-amber-500">門檻</span>
                <span className="text-red-500">最大</span>
              </div>
            </div>

            {/* 即時 ASR 辨識 */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-gray-700">即時語音辨識（ASR）</h2>
                {!sseConnected && (
                  <span className="text-xs text-amber-500 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                    SSE 未連線
                  </span>
                )}
              </div>

              {/* 即時顯示區 */}
              <div className="bg-slate-900 rounded-xl p-4 min-h-[80px] flex flex-col gap-2">
                {asrPartial && (
                  <p className="text-sm text-slate-400 italic">
                    <span className="text-slate-600 text-xs mr-2">辨識中…</span>
                    {asrPartial}
                  </p>
                )}
                {asrFinal && (
                  <p className="text-base text-white font-medium">
                    <span className="text-green-400 text-xs mr-2 font-normal">最終結果</span>
                    「{asrFinal}」
                  </p>
                )}
                {!asrPartial && !asrFinal && (
                  <div className="text-center pt-4">
                    <div className="text-2xl mb-1">🎤</div>
                    <p className="text-slate-600 text-sm italic">等待語音輸入…</p>
                    <p className="text-slate-700 text-xs mt-1">請對著裝置說話或啟用「跳過喚醒詞」</p>
                  </div>
                )}
              </div>

              {/* 指令歷史 */}
              {cmdHistory.length > 0 ? (
                <div className="mt-4">
                  <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">近期指令</h3>
                  <div className="space-y-1 max-h-[140px] overflow-y-auto">
                    {cmdHistory.map((c, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm py-1 border-b border-gray-50 last:border-0">
                        <span className="text-xs text-gray-400 font-mono flex-shrink-0">{c.time}</span>
                        <span className="text-gray-700">「{c.text}」</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-4 text-center text-gray-300 text-xs py-4">
                  <div className="text-lg mb-1">💬</div>
                  <p>尚無辨識指令</p>
                </div>
              )}
            </div>
          </div>

          {/* 右欄：聲紋驗證（佔 1/3） */}
          <div className="space-y-4">

            {/* 最新驗證結果 */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">最新聲紋驗證</h2>
              {lastVerify ? (
                <div className="space-y-4">
                  {/* 結果徽章 */}
                  <div className={`flex items-center gap-3 rounded-xl p-3 ${lastVerify.match ? 'bg-green-50 border border-green-100' : 'bg-red-50 border border-red-100'}`}>
                    <span className={`text-3xl ${lastVerify.match ? 'text-green-500' : 'text-red-500'}`}>
                      {lastVerify.match ? '✓' : '✗'}
                    </span>
                    <div>
                      <div className={`font-bold text-lg ${lastVerify.match ? 'text-green-700' : 'text-red-700'}`}>
                        {lastVerify.match ? '聲紋吻合' : '聲紋不符'}
                      </div>
                      <div className="text-xs text-gray-400">{lastVerify.time}</div>
                    </div>
                  </div>
                  {/* 相似度量表 */}
                  <SimilarityGauge
                    similarity={lastVerify.similarity}
                    threshold={lastVerify.threshold}
                    match={lastVerify.match}
                  />
                </div>
              ) : (
                <div className="text-center py-8 text-gray-400">
                  <div className="text-4xl mb-2">🎤</div>
                  <p className="text-sm">尚無驗證資料</p>
                  <p className="text-xs text-gray-300 mt-1">請啟用聲紋驗證並說話</p>
                </div>
              )}
            </div>

            {/* 驗證歷史 */}
            {verifyHistory.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
                <h2 className="text-sm font-semibold text-gray-700 mb-3">驗證歷史</h2>
                <div className="space-y-2">
                  {verifyHistory.map((v, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs py-1 border-b border-gray-50 last:border-0">
                      <span className={`font-bold ${v.match ? 'text-green-500' : 'text-red-400'}`}>
                        {v.match ? '✓' : '✗'}
                      </span>
                      <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${v.match ? 'bg-green-400' : 'bg-red-400'}`}
                          style={{ width: `${v.similarity * 100}%` }}
                        />
                      </div>
                      <span className="font-mono text-gray-500 w-10 text-right">
                        {(v.similarity * 100).toFixed(0)}%
                      </span>
                      <span className="text-gray-400 flex-shrink-0">{v.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── 事件日誌 ──────────────────────────────────────────────────── */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700">事件日誌</h2>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400">{eventLog.length} / {MAX_LOG} 筆</span>
              <button
                onClick={() => setEventLog([])}
                className="text-xs text-gray-400 hover:text-red-500 transition-colors px-2 py-1 rounded hover:bg-red-50"
              >
                清除
              </button>
            </div>
          </div>
          <div className="max-h-[220px] overflow-y-auto">
            {eventLog.length === 0 ? (
              <div className="text-center text-gray-400 py-8">
                <div className="text-2xl mb-2">📋</div>
                <p className="text-sm">尚無事件</p>
                <p className="text-xs text-gray-300 mt-1">SSE 事件將即時顯示於此</p>
              </div>
            ) : (
              <>
                {eventLog.map((entry, i) => <LogRow key={i} entry={entry} />)}
                <div ref={logEndRef} />
              </>
            )}
          </div>
        </div>

        {/* ── 控制面板 ──────────────────────────────────────────────────── */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">控制面板</h2>
          <div className="flex flex-wrap gap-6 items-center">
            <Toggle
              label="聲紋驗證"
              enabled={speakerVerify}
              onChange={toggleSpeakerVerify}
              accent="bg-violet-500"
            />
            <Toggle
              label="跳過喚醒詞"
              enabled={bypassWake}
              onChange={toggleBypassWake}
              accent="bg-amber-500"
            />

            {/* 分隔線 */}
            <div className="w-px h-8 bg-gray-200" />

            {/* Debug 錄音 */}
            <button
              onClick={toggleRecording}
              disabled={ctrlBusy}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                recording
                  ? 'bg-red-500 hover:bg-red-600 text-white shadow-md shadow-red-200 animate-pulse'
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${recording ? 'bg-white' : 'bg-gray-400'}`} />
              {recording ? '停止錄音' : '開始錄音測試'}
            </button>

            <div className="text-xs text-gray-400 ml-auto">
              💡 錄音測試會將 PCM 音訊存至伺服器 <code className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-500">錄音測試/</code> 目錄
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
