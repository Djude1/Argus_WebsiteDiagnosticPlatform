import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { getTraffic } from '../api'

// ── 常數 ──────────────────────────────────────────────────────────
const PAGE_LABELS = {
  '/': '首頁',
  '/product': '產品介紹',
  '/purchase': '購買頁',
  '/team': '團隊',
  '/download': 'APP 下載',
}
const PALETTE = [
  '#6366f1', '#22d3ee', '#a78bfa', '#34d399',
  '#f59e0b', '#f472b6', '#60a5fa', '#fb923c',
  '#a3e635', '#94a3b8',
]
function pLabel(path) { return PAGE_LABELS[path] || path }

// ── 摘要卡片 ─────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, from, to, change }) {
  const up = change > 0, neutral = change == null
  return (
    <div className={`rounded-2xl p-5 text-white relative overflow-hidden bg-gradient-to-br ${from} ${to}`}>
      <div className="absolute -right-3 -top-3 w-20 h-20 rounded-full bg-white/10" />
      <div className="absolute -right-1 -bottom-5 w-28 h-28 rounded-full bg-white/5" />
      <div className="relative">
        <div className="text-2xl mb-1">{icon}</div>
        <div className="text-3xl font-extrabold tracking-tight">{value.toLocaleString()}</div>
        <div className="text-sm font-medium opacity-80 mt-0.5">{label}</div>
        <div className="flex items-center gap-1.5 mt-2 text-xs opacity-70">
          <span>{sub}</span>
          {!neutral && (
            <span className={`font-bold ${up ? 'text-green-200' : 'text-red-200'}`}>
              {up ? '↑' : '↓'} {Math.abs(change)}%
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 面積折線圖 ────────────────────────────────────────────────────
function AreaChart({ data }) {
  const [hovered, setHovered] = useState(null)
  if (!data.length) return <p className="text-gray-400 text-sm text-center py-10">尚無資料</p>

  const W = 580, H = 180, PL = 44, PR = 12, PT = 12, PB = 30
  const cW = W - PL - PR, cH = H - PT - PB
  const max = Math.max(...data.map(d => d.count), 1)

  const pts = data.map((d, i) => ({
    x: PL + (i / Math.max(data.length - 1, 1)) * cW,
    y: PT + cH - (d.count / max) * cH,
    count: d.count,
    date: d.date,
  }))

  // 平滑三次貝茲曲線
  function smoothPath(ps) {
    if (ps.length < 2) return `M${ps[0].x},${ps[0].y}`
    let d = `M${ps[0].x},${ps[0].y}`
    for (let i = 1; i < ps.length; i++) {
      const mx = (ps[i - 1].x + ps[i].x) / 2
      d += ` C${mx},${ps[i - 1].y} ${mx},${ps[i].y} ${ps[i].x},${ps[i].y}`
    }
    return d
  }
  const line = smoothPath(pts)
  const area = `${line} L${pts.at(-1).x},${PT + cH} L${pts[0].x},${PT + cH}Z`

  const gridVals = [0, 0.25, 0.5, 0.75, 1]

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 210 }}>
      <defs>
        <linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* 格線 + Y 軸標籤 */}
      {gridVals.map(r => {
        const gy = PT + cH - r * cH
        return (
          <g key={r}>
            <line x1={PL} y1={gy} x2={W - PR} y2={gy}
              stroke="#e2e8f0" strokeWidth={1} strokeDasharray="4,3" />
            <text x={PL - 5} y={gy + 4} textAnchor="end" fontSize={9} fill="#94a3b8">
              {Math.round(max * r)}
            </text>
          </g>
        )
      })}

      {/* 面積 + 折線 */}
      <path d={area} fill="url(#ag)" />
      <path d={line} fill="none" stroke="#6366f1" strokeWidth={2.5}
        strokeLinecap="round" strokeLinejoin="round" />

      {/* 數據點 */}
      {pts.map((pt, i) => (
        <g key={pt.date}
          onMouseEnter={() => setHovered(i)}
          onMouseLeave={() => setHovered(null)}
          style={{ cursor: 'crosshair' }}>
          {/* 觸控區 */}
          <rect x={pt.x - 12} y={PT} width={24} height={cH + PB}
            fill="transparent" />
          <circle cx={pt.x} cy={pt.y} r={hovered === i ? 5.5 : 3.5}
            fill={hovered === i ? '#6366f1' : '#fff'}
            stroke="#6366f1" strokeWidth={2} />
          {/* tooltip */}
          {hovered === i && (
            <g>
              <rect x={pt.x - 32} y={pt.y - 36} width={64} height={24}
                rx={6} fill="#1e293b" />
              <text x={pt.x} y={pt.y - 20} textAnchor="middle"
                fontSize={11} fill="#fff" fontWeight="bold">
                {pt.count.toLocaleString()} 次
              </text>
              <text x={pt.x} y={pt.y - 8} textAnchor="middle"
                fontSize={9} fill="#94a3b8">
                {pt.date.slice(5)}
              </text>
            </g>
          )}
          {/* X 軸日期 */}
          {i % 2 === 0 && (
            <text x={pt.x} y={H - 3} textAnchor="middle" fontSize={9} fill="#94a3b8">
              {pt.date.slice(5)}
            </text>
          )}
        </g>
      ))}
    </svg>
  )
}

// ── 甜甜圈圖 ─────────────────────────────────────────────────────
function DonutChart({ data }) {
  const [hov, setHov] = useState(null)
  if (!data.length) return <p className="text-gray-400 text-sm text-center py-6">尚無資料</p>

  const total = data.reduce((s, d) => s + d.count, 0) || 1
  const slices = data.slice(0, 7)
  const R = 72, ri = 44, CX = 90, CY = 90

  let angle = -Math.PI / 2
  const arcs = slices.map((d, i) => {
    const sweep = (d.count / total) * 2 * Math.PI
    const end = angle + sweep
    const large = sweep > Math.PI ? 1 : 0
    const cos1 = Math.cos(angle), sin1 = Math.sin(angle)
    const cos2 = Math.cos(end), sin2 = Math.sin(end)
    const path = [
      `M${CX + R * cos1},${CY + R * sin1}`,
      `A${R},${R} 0 ${large} 1 ${CX + R * cos2},${CY + R * sin2}`,
      `L${CX + ri * cos2},${CY + ri * sin2}`,
      `A${ri},${ri} 0 ${large} 0 ${CX + ri * cos1},${CY + ri * sin1}Z`,
    ].join(' ')
    const mid = angle + sweep / 2
    angle = end
    return { path, color: PALETTE[i], pct: Math.round(d.count / total * 100), pathName: d.path, mid }
  })

  return (
    <div className="flex gap-4 items-center">
      <svg viewBox={`0 0 180 180`} style={{ width: 160, flexShrink: 0 }}>
        {arcs.map((a, i) => (
          <path key={a.pathName} d={a.path} fill={a.color}
            stroke="white" strokeWidth={2}
            opacity={hov == null || hov === i ? 1 : 0.4}
            onMouseEnter={() => setHov(i)}
            onMouseLeave={() => setHov(null)}
            style={{ cursor: 'pointer', transition: 'opacity .2s' }}
          />
        ))}
        {/* 中央 */}
        <circle cx={CX} cy={CY} r={ri - 2} fill="white" />
        <text x={CX} y={CY - 6} textAnchor="middle" fontSize={18}
          fontWeight="bold" fill="#1e293b">
          {hov != null ? arcs[hov]?.pct + '%' : total.toLocaleString()}
        </text>
        <text x={CX} y={CY + 10} textAnchor="middle" fontSize={9} fill="#94a3b8">
          {hov != null ? pLabel(arcs[hov]?.pathName) : '總瀏覽'}
        </text>
      </svg>

      {/* 圖例 */}
      <div className="space-y-1.5 flex-1 min-w-0">
        {arcs.map((a, i) => (
          <div key={a.pathName}
            className="flex items-center gap-2 text-xs cursor-default"
            onMouseEnter={() => setHov(i)}
            onMouseLeave={() => setHov(null)}>
            <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
              style={{ background: a.color }} />
            <span className="text-gray-600 truncate flex-1">{pLabel(a.pathName)}</span>
            <span className="font-semibold text-gray-700">{a.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── 熱門頁面橫條 ─────────────────────────────────────────────────
function TopPagesBar({ data }) {
  const max = data[0]?.count || 1
  return (
    <div className="space-y-3">
      {data.map((p, i) => {
        const pct = Math.round((p.count / max) * 100)
        const color = PALETTE[i % PALETTE.length]
        return (
          <div key={p.path}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-5 h-5 rounded flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                  style={{ background: color }}>
                  {i + 1}
                </span>
                <span className="text-sm text-gray-700 truncate">{pLabel(p.path)}</span>
              </div>
              <span className="text-sm font-semibold text-gray-500 ml-2 flex-shrink-0">
                {p.count.toLocaleString()}
              </span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all duration-700"
                style={{ width: `${pct}%`, background: color }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── 每周比較小圖（Sparkline 長條） ────────────────────────────────
function WeekSparkline({ daily }) {
  if (!daily.length) return null
  const last7 = daily.slice(-7)
  const maxV = Math.max(...last7.map(d => d.count), 1)
  const H = 28
  return (
    <svg viewBox={`0 0 56 ${H}`} className="w-14 h-7 opacity-60">
      {last7.map((d, i) => {
        const bh = Math.max((d.count / maxV) * H, 1)
        return (
          <rect key={d.date} x={i * 8 + 1} y={H - bh} width={6} height={bh}
            rx={2} fill="white" />
        )
      })}
    </svg>
  )
}

// ── 主元件 ───────────────────────────────────────────────────────
export default function Dashboard() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    getTraffic()
      .then(r => { setData(r.data); setLastUpdated(new Date()) })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <div className="w-8 h-8 border-3 border-indigo-300 border-t-indigo-600 rounded-full animate-spin" />
          <span className="text-sm">載入資料中…</span>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50">
        <div className="text-center text-gray-400">
          <div className="text-4xl mb-2">📡</div>
          <p className="text-sm font-medium">無法載入流量資料</p>
          <p className="text-xs mt-1 text-gray-300">請檢查網路連線後再試一次</p>
          <button onClick={load} className="mt-3 text-xs text-indigo-500 hover:underline">重試</button>
        </div>
      </div>
    )
  }

  const { summary, daily, top_pages, product_sales = [] } = data

  // 計算近 7 天 vs 前 7 天的變化率（從 14 天數據推算）
  const curr7 = daily.slice(-7).reduce((s, d) => s + d.count, 0)
  const prev7 = daily.slice(0, daily.length - 7).reduce((s, d) => s + d.count, 0)
  const weekChange = prev7 > 0 ? Math.round(((curr7 - prev7) / prev7) * 100) : null

  // 每日最高
  const peakDay = daily.reduce((best, d) => d.count > (best?.count || 0) ? d : best, null)

  const cards = [
    { icon: '👁️', label: '今日瀏覽', value: summary.today, sub: '自午夜起', from: 'from-blue-500', to: 'to-blue-700', change: null },
    { icon: '📅', label: '近 7 天', value: summary.week, sub: '較前 7 天', from: 'from-indigo-500', to: 'to-violet-600', change: weekChange },
    { icon: '📆', label: '近 30 天', value: summary.month, sub: '最近 30 日', from: 'from-violet-500', to: 'to-purple-700', change: null },
    { icon: '🌐', label: '累計瀏覽', value: summary.total, sub: '自上線以來', from: 'from-emerald-500', to: 'to-teal-600', change: null },
  ]

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50">
      {/* 頂部標題列 */}
      <div className="bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div>
          <h2 className="text-base font-bold text-gray-800">流量追蹤</h2>
          {lastUpdated && (
            <p className="text-xs text-gray-400 mt-0.5">
              最後更新：{lastUpdated.toLocaleTimeString('zh-TW')}
            </p>
          )}
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-xs text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition-colors"
        >
          <motion.svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"
            animate={{ rotate: loading ? 360 : 0 }}
            transition={{ duration: 1, repeat: loading ? Infinity : 0, ease: 'linear' }}
          >
            <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" />
          </motion.svg>
          重新整理
        </button>
      </div>

      <div className="p-6 space-y-6">
        {/* 摘要卡片 */}
        <motion.div
          className="grid grid-cols-2 xl:grid-cols-4 gap-4"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ staggerChildren: 0.1 }}
        >
          {cards.map(card => (
            <motion.div key={card.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
            >
              <StatCard {...card} />
            </motion.div>
          ))}
        </motion.div>

        {/* 趨勢圖 */}
        <div className="bg-white rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-bold text-gray-700">近 14 天瀏覽趨勢</h3>
            {peakDay && (
              <span className="text-xs text-gray-400">
                峰值：<span className="font-semibold text-indigo-500">{peakDay.count}</span> 次（{peakDay.date.slice(5)}）
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mb-4">將滑鼠移至節點可查看當日詳細數值</p>
          <AreaChart data={daily} />
        </div>

        {/* 頁面分布 + 熱門頁面 */}
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
          {/* 甜甜圈 */}
          <div className="xl:col-span-2 bg-white rounded-2xl p-6 shadow-sm">
            <h3 className="text-sm font-bold text-gray-700 mb-4">頁面流量分布</h3>
            <DonutChart data={top_pages} />
          </div>

          {/* 熱門頁面排行 */}
          <div className="xl:col-span-3 bg-white rounded-2xl p-6 shadow-sm">
            <h3 className="text-sm font-bold text-gray-700 mb-4">熱門頁面 Top {top_pages.length}</h3>
            {top_pages.length === 0
              ? <div className="text-center py-10"><div className="text-2xl mb-2">📊</div><p className="text-gray-400 text-sm">尚無頁面瀏覽資料</p></div>
              : <TopPagesBar data={top_pages} />
            }
          </div>
        </div>

        {/* 週次小統計 */}
        {daily.length >= 7 && (
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            {[
              { label: '今日', count: summary.today, color: 'bg-blue-500' },
              { label: '昨日', count: daily.at(-2)?.count ?? 0, color: 'bg-indigo-400' },
              { label: '近7天日均', count: Math.round(curr7 / 7), color: 'bg-violet-400' },
              { label: '近14天最高', count: peakDay?.count ?? 0, color: 'bg-emerald-400' },
            ].map(item => (
              <div key={item.label} className="bg-white rounded-xl p-4 shadow-sm flex items-center gap-4">
                <div className={`w-2 self-stretch rounded-full ${item.color}`} />
                <div>
                  <div className="text-xl font-bold text-gray-800">{item.count.toLocaleString()}</div>
                  <div className="text-xs text-gray-400">{item.label}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 商品銷售統計 */}
        <div className="bg-white rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-bold text-gray-700 mb-4">各商品購買次數</h3>
          {product_sales.length === 0 ? (
            <div className="text-center py-10"><div className="text-2xl mb-2">🛒</div><p className="text-gray-400 text-sm">尚無訂單資料</p></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500">#</th>
                    <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500">商品名稱</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500">訂單筆數</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500">購買總件數</th>
                    <th className="py-2 px-3 text-xs font-semibold text-gray-500">佔比</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const maxQty = product_sales[0]?.total_qty || 1
                    return product_sales.map((p, i) => {
                      const pct = Math.round((p.total_qty / maxQty) * 100)
                      const color = PALETTE[i % PALETTE.length]
                      return (
                        <tr key={p.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                          <td className="py-3 px-3">
                            <span className="w-5 h-5 rounded flex items-center justify-center text-white text-xs font-bold inline-flex"
                              style={{ background: color }}>
                              {i + 1}
                            </span>
                          </td>
                          <td className="py-3 px-3 font-medium text-gray-700">{p.name}</td>
                          <td className="py-3 px-3 text-right text-gray-500">{p.order_count.toLocaleString()}</td>
                          <td className="py-3 px-3 text-right font-bold text-gray-800">{p.total_qty.toLocaleString()}</td>
                          <td className="py-3 px-3">
                            <div className="flex items-center gap-2 min-w-[100px]">
                              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full rounded-full transition-all duration-700"
                                  style={{ width: `${pct}%`, background: color }} />
                              </div>
                              <span className="text-xs text-gray-400 w-7 text-right">{pct}%</span>
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  })()}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
