import { useState, useEffect } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { fetchProducts, fetchProduct } from '../../api/client'
import ModelViewer from '../../components/ModelViewer/ModelViewer'
import { useContent } from '../../context/ContentContext'
import { useCart } from '../../context/CartContext'
import { useToast } from '../../components/Toast'
import ScrollReveal from '../../components/ScrollReveal'
import { motion } from 'framer-motion'
import { ProductCardSkeleton, ProductDetailSkeleton } from '../../components/Skeleton'

// ── 產品列表頁（/product）────────────────────────────────────────
function ProductList({ c }) {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const { addItem } = useCart()
  const toast = useToast()

  useEffect(() => {
    fetchProducts()
      .then(res => setProducts(res.data.results || res.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="pt-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-20">
        {/* 麵包屑 */}
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 transition-colors mb-10">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {c.back_link || '返回首頁'}
        </Link>

        <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-3">{c.list_title || '所有產品'}</h1>
        <p className="text-gray-700 dark:text-gray-400 mb-10">{c.list_subtitle || '點擊產品卡片查看詳細規格與 3D 預覽'}</p>

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 3 }).map((_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        ) : products.length === 0 ? (
          <p className="text-gray-700 dark:text-gray-400 text-center py-20">目前尚無產品</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {products.map((p, i) => (
              <ScrollReveal key={p.id} delay={i * 0.1}>
              <div
                onClick={() => navigate(`/product/${p.id}`)}
                className="glass rounded-2xl overflow-hidden hover:glow-border transition-all duration-300 group flex flex-col cursor-pointer"
              >
                {/* 縮圖或佔位 */}
                {p.image ? (
                  <img src={p.image} alt={p.name} className="w-full h-48 object-cover" />
                ) : (
                  <div className="w-full h-48 flex items-center justify-center bg-gray-100/5 dark:bg-white/5 text-6xl">
                    🥽
                  </div>
                )}
                <div className="p-6 flex flex-col flex-1">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-1.5 h-1.5 bg-green-400 rounded-full" />
                    <span className="text-xs text-warm-600 dark:text-brand-400">{c.availability || '現貨供應中'}</span>
                  </div>
                  <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-2 group-hover:text-warm-600 dark:group-hover:text-brand-400 transition-colors">
                    {p.name}
                  </h2>
                  <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed flex-1">{p.short_description}</p>
                  <div className="mt-4 flex items-end gap-3">
                    <span className="text-2xl font-bold text-warm-600 dark:text-brand-400">
                      NT${(Number(p.price) || 0).toLocaleString()}
                    </span>
                    {p.original_price && (
                      <span className="text-sm text-gray-500 line-through">
                        NT${Number(p.original_price).toLocaleString()}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 flex gap-2">
                    <span className="flex-1 btn-outline text-center text-sm">
                      {c.btn_detail || '查看詳情'}
                    </span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        addItem(p)
                        toast.success(`已加入「${p.name}」至購物車`)
                      }}
                      className="flex-shrink-0 w-10 h-10 rounded-xl border border-warm-500/30 dark:border-brand-500/30 text-warm-600 dark:text-brand-400 hover:bg-warm-500/10 dark:hover:bg-brand-500/10 transition-all flex items-center justify-center"
                      title="加入購物車"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                      </svg>
                    </button>
                  </div>
                  {/* APP 下載連結（使用 a 標籤避免嵌套在 Link 內）*/}
                  <a
                    href="/download"
                    onClick={e => e.stopPropagation()}
                    className="mt-2 flex items-center justify-center gap-1.5 text-xs text-purple-600 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-300 transition-colors"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                    </svg>
                    下載配套 APP
                  </a>
                </div>
              </div>
              </ScrollReveal>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── 單一產品詳情頁（/product/:id）────────────────────────────────
function ProductDetail({ id, c }) {
  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [activeTab, setActiveTab] = useState('features')
  const [added, setAdded] = useState(false)   // 「已加入」提示動畫
  const { addItem } = useCart()
  const toast = useToast()
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    setProduct(null)
    setNotFound(false)
    setActiveTab('features')
    fetchProduct(id)
      .then(res => setProduct(res.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [id])

  // 產品不存在 → 重定向到產品列表
  if (!loading && notFound) {
    return (
      <div className="pt-24 pb-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="py-20">
            <p className="text-6xl mb-4">🔍</p>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">找不到該產品</h2>
            <p className="text-gray-700 dark:text-gray-400 mb-6">您查看的產品可能已下架或不存在。</p>
            <button onClick={() => navigate('/product')} className="btn-primary">
              返回產品列表
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="pt-24 pb-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <ProductDetailSkeleton />
        </div>
      </div>
    )
  }

  // product 此時一定有值（notFound 已在上方處理）
  const displayProduct = product

  const modelUrl = displayProduct.model_3d
    ? (displayProduct.model_3d.startsWith('http')
       ? new URL(displayProduct.model_3d).pathname
       : displayProduct.model_3d.startsWith('/')
         ? displayProduct.model_3d
         : `/media/${displayProduct.model_3d}`)
    : '/media/models/aiglass.glb'

  const tabLabels = {
    features: c.tab_features || '功能特點',
    specs: c.tab_specs || '技術規格',
    description: c.tab_description || '詳細說明',
  }

  return (
    <div className="pt-24 pb-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* 麵包屑導航 */}
        <Link to="/product" className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 transition-colors mb-8">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {c.back_to_list || '所有產品'}
        </Link>

        {/* ═══ 雙欄佈局：左 3D 模型 + 右產品資訊 ═══ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-start">
          {/* 左欄：3D 模型檢視器（sticky — 滾動時保持在視窗頂部）*/}
          <div className="lg:sticky lg:top-24">
            <div className="h-[300px] glass rounded-3xl overflow-hidden glow-border relative">
              {/* 日間模式模糊圓圈背景：讓白色商品突出 */}
              <div className="absolute inset-0 m-auto w-48 h-64 bg-gray-200/30 dark:bg-transparent rounded-full blur-3xl pointer-events-none" />
              <ModelViewer modelUrl={modelUrl} cameraHeight={product?.camera_height} className="w-full h-full" />
            </div>
            <p className="text-center text-xs text-gray-500 mt-3">
              {c.model_hint || '可互動 3D 預覽 · 拖曳旋轉 · 滾輪縮放'}
            </p>
          </div>

          {/* 右欄：產品資訊 */}
          <ScrollReveal delay={0.2} direction="up">
            <div className="flex flex-col justify-center">
              {/* 現貨標籤 */}
              <div className="inline-flex items-center gap-2 text-xs text-warm-600 dark:text-brand-400 glass rounded-full px-3 py-1 mb-4 w-fit">
                <span className="w-1.5 h-1.5 bg-green-400 rounded-full" />
                {c.availability || '現貨供應中'}
              </div>

              {/* 產品名稱 */}
              <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white mb-3">
                {displayProduct.name}
              </h1>
              <p className="text-gray-700 dark:text-gray-400 text-base lg:text-lg mb-6 leading-relaxed">
                {displayProduct.short_description}
              </p>

              {/* 價格 */}
              <div className="flex items-end gap-4 mb-6 flex-wrap">
                <span className="text-3xl lg:text-4xl font-bold text-warm-600 dark:text-brand-400">
                  NT${(Number(displayProduct.price) || 0).toLocaleString()}
                </span>
                {displayProduct.original_price && (
                  <span className="text-lg text-gray-500 line-through">
                    NT${Number(displayProduct.original_price).toLocaleString()}
                  </span>
                )}
                {displayProduct.original_price && (
                  <span className="bg-red-500/20 text-red-600 dark:text-red-400 text-sm font-semibold px-2 py-1 rounded-lg">
                    省 NT${((Number(displayProduct.original_price) || 0) - (Number(displayProduct.price) || 0)).toLocaleString()}
                  </span>
                )}
              </div>

              {/* CTA 按鈕 */}
              <div className="flex items-center gap-3 flex-wrap mb-8">
                <Link to={product ? `/purchase?product=${product.id}` : '/purchase'} className="btn-primary inline-block">
                  {c.btn_buy || '立即購買'}
                </Link>
                <motion.button
                  type="button"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    if (product) {
                      addItem(product)
                      setAdded(true)
                      toast.success(`已加入「${product.name}」至購物車`)
                      setTimeout(() => setAdded(false), 1500)
                    }
                  }}
                  className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border text-sm font-semibold transition-all duration-200 ${
                    added
                      ? 'border-green-500/50 bg-green-500/10 text-green-400'
                      : 'border-gray-300 bg-gray-100 dark:border-white/20 dark:bg-white/5 text-gray-900 dark:text-white hover:border-warm-600/50 dark:hover:border-brand-500/50 hover:bg-warm-600/10 dark:hover:bg-brand-500/10 hover:text-warm-600 dark:hover:text-brand-400'
                  }`}
                >
                  {added ? (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      已加入購物車
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                      </svg>
                      加入購物車
                    </>
                  )}
                </motion.button>
                {/* APP 下載按鈕 */}
                <Link
                  to="/download"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-purple-500/30 bg-purple-500/5 text-purple-600 dark:text-purple-400 hover:border-purple-500/50 hover:bg-purple-500/10 hover:text-purple-700 dark:hover:text-purple-300 text-sm font-semibold transition-all duration-200"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  下載配套 APP
                </Link>
              </div>

              {/* 標籤頁切換：功能特點 / 技術規格 / 詳細說明 */}
              <div className="border-b border-gray-200 dark:border-white/10 mb-6">
                <div className="flex gap-6">
                  {['features', 'specs', 'description'].map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`pb-3 text-sm font-medium transition-all border-b-2 -mb-px ${
                        activeTab === tab
                          ? 'text-warm-600 dark:text-brand-400 border-warm-500 dark:border-brand-400'
                          : 'text-gray-600 dark:text-gray-400 border-transparent hover:text-gray-900 dark:hover:text-gray-200'
                      }`}
                    >
                      {tabLabels[tab]}
                    </button>
                  ))}
                </div>
              </div>

              {/* 功能特點 — grid 卡片佈局 */}
              {activeTab === 'features' && (
                <motion.div
                  key="features"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  {displayProduct.features.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {displayProduct.features.map((feature) => (
                        <div key={feature.id} className="glass rounded-xl p-4 hover:border-warm-500/30 dark:hover:border-brand-500/30 transition-all">
                          <div className="text-2xl mb-2">{feature.icon}</div>
                          <h3 className="font-semibold text-gray-900 dark:text-white text-sm mb-1">{feature.title}</h3>
                          <p className="text-gray-700 dark:text-gray-400 text-xs leading-relaxed">{feature.description}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-700 col-span-2">{c.empty_features || '功能特點資料載入中...'}</p>
                  )}
                </motion.div>
              )}

              {/* 技術規格 */}
              {activeTab === 'specs' && (
                <motion.div
                  key="specs"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  {displayProduct.specs.length > 0 ? (
                    <div className="space-y-2">
                      {displayProduct.specs.map((spec) => (
                        <div key={spec.id} className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-white/5">
                          <span className="text-gray-700 dark:text-gray-400 text-sm">{spec.key}</span>
                          <span className="text-gray-900 dark:text-white text-sm font-medium">{spec.value}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-700">{c.empty_specs || '技術規格資料載入中...'}</p>
                  )}
                </motion.div>
              )}

              {/* 詳細說明 */}
              {activeTab === 'description' && (
                <motion.div
                  key="description"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <p className="text-gray-700 dark:text-gray-400 leading-relaxed whitespace-pre-line">
                    {displayProduct.description}
                  </p>
                </motion.div>
              )}
            </div>
          </ScrollReveal>
        </div>
      </div>

      {/* 手機版 Sticky 底部購買列 */}
      <div className="fixed bottom-0 left-0 right-0 md:hidden z-40 bg-white/90 dark:bg-gray-900/90 backdrop-blur-lg border-t border-gray-200 dark:border-white/10 px-4 py-3" style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}>
        <div className="flex items-center justify-between gap-3 max-w-lg mx-auto">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{displayProduct.name}</p>
            <p className="text-warm-600 dark:text-brand-400 text-sm font-bold">NT${(Number(displayProduct.price) || 0).toLocaleString()}</p>
          </div>
          <div className="flex gap-2">
            <motion.button
              type="button"
              whileTap={{ scale: 0.95 }}
              onClick={() => {
                if (product) {
                  addItem(displayProduct)
                  toast.success(`已加入「${displayProduct.name}」至購物車`)
                }
              }}
              className="px-4 py-2.5 rounded-xl border border-warm-500/50 dark:border-brand-500/50 text-warm-600 dark:text-brand-400 text-sm font-semibold hover:bg-warm-500/10 dark:hover:bg-brand-500/10 transition-colors whitespace-nowrap"
            >
              加入購物車
            </motion.button>
            <Link
              to={product ? `/purchase?product=${product.id}` : '/purchase'}
              className="btn-primary text-sm py-2.5 px-4 whitespace-nowrap"
            >
              立即購買
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── 路由分發 ─────────────────────────────────────────────────────
export default function Product() {
  const { id } = useParams()
  const { product: c } = useContent()

  return id ? <ProductDetail id={id} c={c} /> : <ProductList c={c} />
}
