import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import ModelViewer from '../../components/ModelViewer/ModelViewer'
import { fetchProducts, fetchProduct } from '../../api/client'
import { useContent } from '../../context/ContentContext'

function getModelUrl(product) {
  if (!product?.model_3d) return null
  const m = String(product.model_3d)
  if (m.startsWith('http')) return new URL(m).pathname
  if (m.startsWith('/')) return m
  return `/media/${m}`
}

export default function Home() {
  const [products, setProducts]   = useState([])
  const [details, setDetails]     = useState({})  // id → 含 features/specs 的完整資料
  const [currentIdx, setCurrentIdx] = useState(0)
  const { home: c } = useContent()

  const currentBase    = products[currentIdx] || null
  const currentProduct = currentBase ? (details[currentBase.id] || currentBase) : null
  const highlights     = (currentProduct?.features || []).slice(0, 4)
  const modelUrl       = getModelUrl(currentProduct) || '/media/models/aiglass.glb'
  const price          = currentProduct ? Number(currentProduct.price).toLocaleString() : '12,900'
  const originalPrice  = currentProduct ? Number(currentProduct.original_price).toLocaleString() : '15,900'

  // 切換到指定索引的產品，必要時懶載入完整資料
  const switchTo = useCallback(async (idx, list = products, cache = details) => {
    setCurrentIdx(idx)
    const p = list[idx]
    if (p && !cache[p.id]) {
      const res = await fetchProduct(p.id)
      setDetails(prev => ({ ...prev, [res.data.id]: res.data }))
    }
  }, [products, details])

  useEffect(() => {
    fetchProducts()
      .then(res => {
        const list = res.data.results || res.data
        setProducts(list)
        if (list.length === 0) return
        // 預先載入第一個產品的完整資料
        return fetchProduct(list[0].id).then(r => {
          setDetails({ [r.data.id]: r.data })
        })
      })
      .catch(console.error)
  }, [])

  return (
    <div>
      {/* ── Hero 區塊 ── */}
      <section className="relative overflow-hidden">
        {/* 背景裝飾 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-600/10 rounded-full blur-3xl" />
          <div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-brand-950/20 via-transparent to-transparent" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-16 grid grid-cols-1 lg:grid-cols-2 gap-12 lg:items-center">
          {/* 左側文字 */}
          <div className="animate-fade-in-up">
            <div className="inline-flex items-center gap-2 glass rounded-full px-4 py-2 text-sm text-brand-400 mb-6">
              <span className="w-2 h-2 bg-brand-400 rounded-full animate-pulse-slow" />
              {c.hero_badge || '基於 OpenAIglasses_for_Navigation 開源專案'}
            </div>

            {/* 多產品切換器 */}
            {products.length > 1 && (
              <div className="flex flex-wrap gap-2 mb-5">
                {products.map((p, i) => (
                  <button
                    key={p.id}
                    onClick={() => switchTo(i)}
                    className={`text-xs px-3.5 py-1.5 rounded-full border font-medium transition-all duration-200 ${
                      currentIdx === i
                        ? 'bg-brand-500 border-brand-500 text-white shadow-lg shadow-brand-500/30'
                        : 'border-brand-500/40 text-brand-400 hover:border-brand-400 hover:text-brand-300'
                    }`}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            )}

            <h1 className="text-5xl md:text-6xl font-bold leading-tight mb-6">
              {currentProduct ? (
                <>
                  <span className="text-white">
                    {currentProduct.name.split(/[\s　]/)[0]}
                  </span>
                  <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-400 to-brand-600">
                    {currentProduct.name.split(/[\s　]/).slice(1).join(' ') ||
                      <>{c.hero_title_2 || '智慧眼鏡'}</>}
                  </span>
                </>
              ) : (
                <>
                  <span className="text-white">{c.hero_title_1 || 'AI 導航'}</span>
                  <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-400 to-brand-600">
                    {c.hero_title_2 || '智慧眼鏡'}
                  </span>
                </>
              )}
            </h1>

            <p className="text-gray-400 text-lg leading-relaxed mb-8 max-w-xl">
              {currentProduct?.short_description ||
                c.hero_description ||
                '將 OpenAI GPT 語音助理與 AR 擴增實境導航融合於一副輕巧眼鏡之中，讓您在行走間輕鬆獲取路線指引、AI 問答、環境資訊，開啟次世代穿戴體驗。'}
            </p>

            <div className="flex flex-wrap gap-4">
              <Link to={currentBase ? `/purchase?product=${currentBase.id}` : '/purchase'} className="btn-primary">
                {c.hero_btn_buy || '立即購買'} NT${price}
              </Link>
              <Link
                to={currentBase ? `/product/${currentBase.id}` : '/product'}
                className="btn-outline"
              >
                {c.hero_btn_detail || '查看產品詳情'}
              </Link>
            </div>

            {/* 統計數字 */}
            <div className="flex gap-8 mt-12">
              {[
                { num: c.stat_1_value || '45g',  label: c.stat_1_label || '超輕鏡框' },
                { num: c.stat_2_value || '8h',   label: c.stat_2_label || '續航時間' },
                { num: c.stat_3_value || 'GPT',  label: c.stat_3_label || 'AI 核心' },
              ].map((stat) => (
                <div key={stat.label}>
                  <div className="text-2xl font-bold text-brand-400">{stat.num}</div>
                  <div className="text-sm text-gray-500">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 右側 3D 模型（固定高度避免重繪跳位） */}
          <div className="h-[360px] lg:h-[460px] flex-shrink-0">
            <div className="w-full h-full">
              <ModelViewer modelUrl={modelUrl} className="w-full h-full" />
            </div>
            <p className="text-center text-xs text-gray-600 mt-2">
              {c.model_hint || '拖曳旋轉 · 滾輪縮放'}
            </p>
          </div>
        </div>
      </section>

      {/* ── 特色亮點 ── */}
      <section className="py-20 bg-gray-900/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="section-title">
            {currentProduct
              ? `${currentProduct.name} · 功能亮點`
              : c.features_title || '為什麼選擇 AI 智慧眼鏡？'}
          </h2>
          <p className="section-subtitle">
            {c.features_subtitle || '整合最先進的 AI 技術，讓穿戴科技真正融入您的日常生活。'}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {highlights.length > 0 ? highlights.map((item) => (
              <div
                key={item.id || item.title}
                className="glass rounded-2xl p-6 hover:glow-border transition-all duration-300 group"
              >
                <div className="text-4xl mb-4">{item.icon}</div>
                <h3 className="font-semibold text-white mb-2 group-hover:text-brand-400 transition-colors">
                  {item.title}
                </h3>
                <p className="text-gray-400 text-sm leading-relaxed">{item.description}</p>
              </div>
            )) : (
              /* 載入中佔位 */
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="glass rounded-2xl p-6 animate-pulse">
                  <div className="w-10 h-10 bg-white/10 rounded-lg mb-4" />
                  <div className="h-4 bg-white/10 rounded mb-2 w-3/4" />
                  <div className="h-3 bg-white/5 rounded w-full" />
                </div>
              ))
            )}
          </div>

          {/* 產品列表預覽（多產品時顯示其他產品） */}
          {products.length > 1 && (
            <div className="mt-12 pt-10 border-t border-white/5">
              <h3 className="text-center text-sm text-gray-500 mb-6 uppercase tracking-widest">
                其他產品
              </h3>
              <div className="flex flex-wrap justify-center gap-4">
                {products.map((p, i) => i !== currentIdx && (
                  <button
                    key={p.id}
                    onClick={() => switchTo(i)}
                    className="glass rounded-xl px-6 py-4 text-left hover:glow-border transition-all group"
                  >
                    <div className="text-sm font-semibold text-white group-hover:text-brand-400 transition-colors">
                      {p.name}
                    </div>
                    <div className="text-xs text-gray-500 mt-1 max-w-[200px] truncate">
                      {p.short_description}
                    </div>
                    <div className="text-brand-400 text-sm font-bold mt-2">
                      NT${Number(p.price).toLocaleString()}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── 購買 CTA ── */}
      <section className="py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="glass rounded-3xl p-12 glow-border">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">
              {c.cta_title || '準備好體驗 AI 穿戴未來了嗎？'}
            </h2>
            <p className="text-gray-400 mb-8 text-lg">
              {c.cta_description || '現在訂購享有早鳥優惠，限時特惠中。'}
              {currentProduct && ` 原價 NT$${originalPrice}，限時優惠 NT$${price}。`}
            </p>
            <div className="flex flex-wrap gap-4 justify-center">
              <Link to={currentBase ? `/purchase?product=${currentBase.id}` : '/purchase'} className="btn-primary text-lg py-4 px-10">
                {c.cta_btn_buy || '立即訂購'}
              </Link>
              <Link
                to={currentBase ? `/product/${currentBase.id}` : '/product'}
                className="btn-outline text-lg py-4 px-10"
              >
                {c.cta_btn_more || '了解更多'}
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
