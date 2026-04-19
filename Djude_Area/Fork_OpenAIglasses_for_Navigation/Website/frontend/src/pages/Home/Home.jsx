import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import ModelViewer from '../../components/ModelViewer/ModelViewer'
import { fetchProducts, fetchProduct } from '../../api/client'
import { useContent } from '../../context/ContentContext'
import { useCart } from '../../context/CartContext'
import { useToast } from '../../components/Toast'
import ScrollReveal from '../../components/ScrollReveal'
import CountUp from '../../components/CountUp'

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
  const { addItem } = useCart()
  const toast = useToast()

  const currentBase    = products[currentIdx] || null
  const currentProduct = currentBase ? (details[currentBase.id] || currentBase) : null
  const highlights     = (currentProduct?.features || []).slice(0, 4)
  const modelUrl       = getModelUrl(currentProduct) || '/media/models/aiglass.glb'
  const price          = currentProduct ? (Number(currentProduct.price) || 0).toLocaleString() : '12,900'
  const originalPrice  = currentProduct ? (Number(currentProduct.original_price) || 0).toLocaleString() : '15,900'

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
      <section aria-labelledby="hero-heading" className="relative">
        {/* 網狀漸層底層 */}
        <div className="absolute inset-0 pointer-events-none mesh-gradient" />

        {/* 動態漸層光球 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-[10%] w-[420px] h-[420px] bg-warm-400/5 dark:bg-brand-600/10 rounded-full blur-[100px] animate-float" />
          <div className="absolute bottom-[15%] right-[15%] w-80 h-80 bg-warm-500/4 dark:bg-brand-500/8 rounded-full blur-[80px] animate-float-delayed" />
          <div className="absolute top-[60%] left-[50%] w-64 h-64 bg-cyan-400/3 dark:bg-brand-400/5 rounded-full blur-[60px] animate-float" />
        </div>

        {/* 幾何裝飾元素 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="geo-diamond absolute top-[15%] right-[8%] opacity-60" />
          <div className="geo-ring absolute bottom-[20%] left-[5%] opacity-40" />
          <div className="geo-diamond absolute top-[50%] right-[30%] w-6 h-6 opacity-30" style={{ animationDelay: '-5s' }} />
        </div>

        {/* 中央放射漸層 */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-warm-500/5 via-transparent to-transparent dark:from-brand-950/20 dark:via-transparent dark:to-transparent" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-16 grid grid-cols-1 lg:grid-cols-2 gap-12 lg:items-center">
          {/* 左側文字 */}
          <div className="animate-fade-in-up">
            <div className="inline-flex items-center gap-2 glass rounded-full px-4 py-2 text-sm text-warm-600 dark:text-brand-400 mb-6">
              <span className="w-2 h-2 bg-warm-400 dark:bg-brand-400 rounded-full" />
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
                        ? 'bg-warm-500 border-warm-500 dark:bg-brand-500 dark:border-brand-500 text-white shadow-lg shadow-warm-500/30 dark:shadow-brand-500/30'
                        : 'border-warm-500/40 dark:border-brand-500/40 text-warm-600 dark:text-brand-400 hover:border-warm-600 dark:hover:border-brand-400 hover:text-warm-700 dark:hover:text-brand-300'
                    }`}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            )}

            <h1 id="hero-heading" className="text-5xl md:text-6xl font-bold leading-tight mb-6">
              {currentProduct ? (
                <>
                  <span className="text-gray-900 dark:text-white">
                    {currentProduct.name.split(/[\s　]/)[0]}
                  </span>
                  <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-warm-400 to-warm-600 dark:from-brand-400 dark:to-brand-600">
                    {currentProduct.name.split(/[\s　]/).slice(1).join(' ') ||
                      <>{c.hero_title_2 || '智慧眼鏡'}</>}
                  </span>
                </>
              ) : (
                <>
                  <span className="text-gray-900 dark:text-white">{c.hero_title_1 || 'AI 導航'}</span>
                  <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-warm-400 to-warm-600 dark:from-brand-400 dark:to-brand-600">
                    {c.hero_title_2 || '智慧眼鏡'}
                  </span>
                </>
              )}
            </h1>

            <p className="text-gray-700 dark:text-gray-400 text-lg leading-relaxed mb-8 max-w-xl">
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
              {/* 加入購物車按鈕 */}
              <button
                onClick={() => {
                  if (!currentProduct) return
                  addItem(currentProduct, 1)
                  toast.success('已加入購物車')
                }}
                className="btn-outline inline-flex items-center gap-2"
                aria-label="加入購物車"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
                加入購物車
              </button>
            </div>

            {/* 統計數字 */}
            <div className="flex gap-8 mt-12">
              {[
                { num: c.stat_1_value || '45g',  label: c.stat_1_label || '超輕鏡框' },
                { num: c.stat_2_value || '8h',   label: c.stat_2_label || '續航時間' },
                { num: c.stat_3_value || 'GPT',  label: c.stat_3_label || 'AI 核心' },
              ].map((stat) => {
                // 解析數字部分與後綴：純數字（含小數點）的 prefix 使用 CountUp，其餘直接顯示
                const parsed = String(stat.num).match(/^(\d+\.?\d*)(.*)$/)
                const isNumeric = parsed && parsed[1]
                return (
                  <div key={stat.label} className="text-center">
                    <div className="text-2xl font-bold text-warm-600 dark:text-brand-400">
                      {isNumeric ? (
                        <CountUp end={Number(parsed[1])} suffix={parsed[2]} duration={2} />
                      ) : (
                        stat.num
                      )}
                    </div>
                    <div className="text-sm text-gray-700 dark:text-gray-400">{stat.label}</div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 右側 3D 模型（固定高度避免重繪跳位） */}
          {/* 日間模式模糊圓圈背景裝飾：讓白色商品在灰底上更突出 */}
          <div className="h-[360px] lg:h-[460px] flex-shrink-0 relative">
            <div className="w-full h-full relative z-10">
              <ModelViewer modelUrl={modelUrl} cameraHeight={currentProduct?.camera_height} className="w-full h-full" />
            </div>
            <p className="text-center text-xs text-gray-600 dark:text-gray-400 mt-2">
              {c.model_hint || '拖曳旋轉 · 滾輪縮放'}
            </p>
          </div>
        </div>
      </section>

      {/* ── 特色亮點 ── */}
      <section aria-labelledby="features-heading" className="py-20 bg-white dark:bg-gray-900/50 relative">
        {/* 區段頂部漸層分隔線 */}
        <div className="section-divider absolute top-0 left-0 right-0" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <ScrollReveal>
            <h2 id="features-heading" className="section-title">
              {currentProduct
                ? `${currentProduct.name} · 功能亮點`
                : c.features_title || '為什麼選擇 AI 智慧眼鏡？'}
            </h2>
            <p className="section-subtitle">
              {c.features_subtitle || '整合最先進的 AI 技術，讓穿戴科技真正融入您的日常生活。'}
            </p>
          </ScrollReveal>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {highlights.length > 0 ? highlights.map((item, i) => (
              <ScrollReveal key={item.id || item.title} delay={i * 0.1}>
                <div className="glass gradient-top-border rounded-2xl p-6 hover:glow-border transition-all duration-300 group">
                  <div className="text-4xl mb-4">{item.icon}</div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-2 group-hover:text-warm-600 dark:group-hover:text-brand-400 transition-colors">
                    {item.title}
                  </h3>
                  <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed">{item.description}</p>
                </div>
              </ScrollReveal>
            )) : (
              /* 載入中佔位 */
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="glass rounded-2xl p-6 animate-pulse">
                  <div className="w-10 h-10 bg-gray-200/10 dark:bg-white/10 rounded-lg mb-4" />
                  <div className="h-4 bg-gray-200/10 dark:bg-white/10 rounded mb-2 w-3/4" />
                  <div className="h-3 bg-gray-100/5 dark:bg-white/5 rounded w-full" />
                </div>
              ))
            )}
          </div>

          {/* 產品列表預覽（多產品時顯示其他產品） */}
          {products.length > 1 && (
            <ScrollReveal delay={0.3}>
              <div className="mt-12 pt-10 border-t border-gray-100 dark:border-white/5">
                <h3 className="text-center text-sm text-gray-900 dark:text-gray-400 mb-6 uppercase tracking-widest">
                  其他產品
                </h3>
                <div className="flex flex-wrap justify-center gap-4">
                  {products.map((p, i) => i !== currentIdx && (
                    <div
                      key={p.id}
                      onClick={() => switchTo(i)}
                      className="glass rounded-xl px-6 py-4 text-left hover:glow-border transition-all group cursor-pointer"
                    >
                      <div className="text-sm font-semibold text-gray-900 dark:text-white group-hover:text-warm-600 dark:group-hover:text-brand-400 transition-colors">
                        {p.name}
                      </div>
                      <div className="text-xs text-gray-700 dark:text-gray-400 mt-1 max-w-[200px] truncate">
                        {p.short_description}
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <div className="text-warm-600 dark:text-brand-400 text-sm font-bold">
                          NT${(Number(p.price) || 0).toLocaleString()}
                        </div>
                        {/* 加入購物車按鈕 */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            addItem(p, 1)
                            toast.success(`${p.name} 已加入購物車`)
                          }}
                          className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-warm-400/50 dark:border-brand-500/50 text-warm-600 dark:text-brand-400 hover:bg-warm-50 dark:hover:bg-brand-500/10 transition-colors"
                          aria-label={`將 ${p.name} 加入購物車`}
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                          </svg>
                          加入
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </ScrollReveal>
          )}
        </div>
      </section>

      {/* ── 購買 CTA ── */}
      <section aria-labelledby="cta-heading" className="py-20 relative overflow-hidden">
        {/* CTA 背景裝飾光球 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-20 -left-20 w-80 h-80 bg-warm-400/4 dark:bg-brand-600/8 rounded-full blur-[100px] animate-float" />
          <div className="absolute -bottom-20 -right-20 w-96 h-96 bg-warm-500/3 dark:bg-brand-500/6 rounded-full blur-[80px] animate-float-delayed" />
        </div>

        <div className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <ScrollReveal direction="up" delay={0.2}>
            <div className="glass rounded-3xl p-12 glow-border relative overflow-hidden">
              {/* 內部漸層裝飾 */}
              <div className="absolute inset-0 pointer-events-none bg-gradient-to-br from-warm-500/5 via-transparent to-cyan-500/5 dark:from-brand-500/5 dark:via-transparent dark:to-cyan-500/5" />
              <h2 id="cta-heading" className="text-3xl md:text-4xl font-bold mb-4 relative z-10">
                {c.cta_title || '準備好體驗 AI 穿戴未來了嗎？'}
              </h2>
              <p className="text-gray-700 dark:text-gray-400 mb-8 text-lg relative z-10">
                {c.cta_description || '現在訂購享有早鳥優惠，限時特惠中。'}
                {currentProduct && ` 原價 NT$${originalPrice}，限時優惠 NT$${price}。`}
              </p>
              <div className="flex flex-wrap gap-4 justify-center relative z-10">
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
          </ScrollReveal>
        </div>
      </section>
    </div>
  )
}
