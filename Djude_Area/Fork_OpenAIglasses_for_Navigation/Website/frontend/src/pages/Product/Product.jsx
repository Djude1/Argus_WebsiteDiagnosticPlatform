import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchProducts, fetchProduct } from '../../api/client'
import ModelViewer from '../../components/ModelViewer/ModelViewer'
import { useContent } from '../../context/ContentContext'
import { useCart } from '../../context/CartContext'

// ── 產品列表頁（/product）────────────────────────────────────────
function ProductList({ c }) {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)

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
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-brand-400 transition-colors mb-10">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {c.back_link || '返回首頁'}
        </Link>

        <h1 className="text-4xl font-bold text-white mb-3">{c.list_title || '所有產品'}</h1>
        <p className="text-gray-400 mb-10">{c.list_subtitle || '點擊產品卡片查看詳細規格與 3D 預覽'}</p>

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="glass rounded-2xl p-6 animate-pulse">
                <div className="h-48 bg-white/5 rounded-xl mb-4" />
                <div className="h-5 bg-white/10 rounded w-2/3 mb-2" />
                <div className="h-3 bg-white/5 rounded w-full mb-4" />
                <div className="h-8 bg-white/10 rounded w-1/3" />
              </div>
            ))}
          </div>
        ) : products.length === 0 ? (
          <p className="text-gray-500 text-center py-20">目前尚無產品</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {products.map((p) => (
              <Link
                key={p.id}
                to={`/product/${p.id}`}
                className="glass rounded-2xl overflow-hidden hover:glow-border transition-all duration-300 group flex flex-col"
              >
                {/* 縮圖或佔位 */}
                {p.image ? (
                  <img src={p.image} alt={p.name} className="w-full h-48 object-cover" />
                ) : (
                  <div className="w-full h-48 flex items-center justify-center bg-white/5 text-6xl">
                    🥽
                  </div>
                )}
                <div className="p-6 flex flex-col flex-1">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-1.5 h-1.5 bg-green-400 rounded-full" />
                    <span className="text-xs text-brand-400">{c.availability || '現貨供應中'}</span>
                  </div>
                  <h2 className="text-lg font-bold text-white mb-2 group-hover:text-brand-400 transition-colors">
                    {p.name}
                  </h2>
                  <p className="text-gray-400 text-sm leading-relaxed flex-1">{p.short_description}</p>
                  <div className="mt-4 flex items-end gap-3">
                    <span className="text-2xl font-bold text-brand-400">
                      NT${Number(p.price).toLocaleString()}
                    </span>
                    {p.original_price && (
                      <span className="text-sm text-gray-500 line-through">
                        NT${Number(p.original_price).toLocaleString()}
                      </span>
                    )}
                  </div>
                  <span className="mt-4 btn-outline text-center text-sm">
                    {c.btn_detail || '查看詳情'}
                  </span>
                  {/* APP 下載連結（防止點擊冒泡觸發產品卡片跳轉）*/}
                  <Link
                    to="/download"
                    onClick={e => e.stopPropagation()}
                    className="mt-2 flex items-center justify-center gap-1.5 text-xs text-purple-400/70 hover:text-purple-400 transition-colors"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                    </svg>
                    下載配套 APP
                  </Link>
                </div>
              </Link>
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
  const [activeTab, setActiveTab] = useState('features')
  const [added, setAdded] = useState(false)   // 「已加入」提示動畫
  const { addItem } = useCart()

  useEffect(() => {
    setLoading(true)
    setProduct(null)
    setActiveTab('features')
    fetchProduct(id)
      .then(res => setProduct(res.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-12 h-12 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const displayProduct = product || {
    name: 'AI 導航智慧眼鏡',
    short_description: '結合 AI 語音助理與 AR 導航的次世代智慧眼鏡',
    description: 'OpenAI Glasses for Navigation 是一款革命性的 AI 智慧眼鏡。',
    price: '12900.00',
    original_price: '15900.00',
    model_3d: 'models/aiglass.glb',
    features: [],
    specs: [],
  }

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
    <div className="pt-16">
      {/* 麵包屑導航 */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        <Link to="/product" className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-brand-400 transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {c.back_to_list || '所有產品'}
        </Link>
      </div>

      {/* 產品展示區 */}
      <section className="py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-start">
            {/* 3D 模型檢視 */}
            <div className="lg:sticky lg:top-24">
              <div className="h-[300px] glass rounded-3xl overflow-hidden glow-border">
                <ModelViewer modelUrl={modelUrl} className="w-full h-full" />
              </div>
              <p className="text-center text-xs text-gray-500 mt-3">
                {c.model_hint || '可互動 3D 預覽 · 拖曳旋轉 · 滾輪縮放'}
              </p>
            </div>

            {/* 產品資訊 */}
            <div>
              <div className="inline-flex items-center gap-2 text-xs text-brand-400 glass rounded-full px-3 py-1 mb-4">
                <span className="w-1.5 h-1.5 bg-green-400 rounded-full" />
                {c.availability || '現貨供應中'}
              </div>
              <h1 className="text-4xl font-bold text-white mb-3">{displayProduct.name}</h1>
              <p className="text-gray-400 text-lg mb-6">{displayProduct.short_description}</p>

              {/* 價格 */}
              <div className="flex items-end gap-4 mb-8">
                <span className="text-4xl font-bold text-brand-400">
                  NT${Number(displayProduct.price).toLocaleString()}
                </span>
                {displayProduct.original_price && (
                  <span className="text-xl text-gray-500 line-through">
                    NT${Number(displayProduct.original_price).toLocaleString()}
                  </span>
                )}
                {displayProduct.original_price && (
                  <span className="bg-red-500/20 text-red-400 text-sm font-semibold px-2 py-1 rounded-lg">
                    省 NT${(Number(displayProduct.original_price) - Number(displayProduct.price)).toLocaleString()}
                  </span>
                )}
              </div>

              {/* 購買按鈕區 */}
              <div className="flex items-center gap-3 mb-8 flex-wrap">
                <Link to={product ? `/purchase?product=${product.id}` : '/purchase'} className="btn-primary inline-block">
                  {c.btn_buy || '立即購買'}
                </Link>
                <button
                  type="button"
                  onClick={() => {
                    if (product) {
                      addItem(product)
                      setAdded(true)
                      setTimeout(() => setAdded(false), 1500)
                    }
                  }}
                  className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border text-sm font-semibold transition-all duration-200 ${
                    added
                      ? 'border-green-500/50 bg-green-500/10 text-green-400'
                      : 'border-white/20 bg-white/5 text-white hover:border-brand-500/50 hover:bg-brand-500/10 hover:text-brand-400'
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
                </button>
                {/* APP 下載按鈕 */}
                <Link
                  to="/download"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-purple-500/30 bg-purple-500/5 text-purple-400 hover:border-purple-400/50 hover:bg-purple-500/10 text-sm font-semibold transition-all duration-200"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  下載配套 APP
                </Link>
              </div>

              {/* 標籤頁 */}
              <div className="border-b border-white/10 mb-6">
                <div className="flex gap-6">
                  {['features', 'specs', 'description'].map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`pb-3 text-sm font-medium transition-all border-b-2 -mb-px ${
                        activeTab === tab
                          ? 'text-brand-400 border-brand-400'
                          : 'text-gray-500 border-transparent hover:text-gray-300'
                      }`}
                    >
                      {tabLabels[tab]}
                    </button>
                  ))}
                </div>
              </div>

              {/* 功能特點 */}
              {activeTab === 'features' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {displayProduct.features.length > 0 ? (
                    displayProduct.features.map((feature) => (
                      <div key={feature.id} className="glass rounded-xl p-4 hover:border-brand-500/30 transition-all">
                        <div className="text-2xl mb-2">{feature.icon}</div>
                        <h3 className="font-semibold text-white text-sm mb-1">{feature.title}</h3>
                        <p className="text-gray-400 text-xs leading-relaxed">{feature.description}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-gray-500 col-span-2">{c.empty_features || '功能特點資料載入中...'}</p>
                  )}
                </div>
              )}

              {/* 技術規格 */}
              {activeTab === 'specs' && (
                <div className="space-y-2">
                  {displayProduct.specs.length > 0 ? (
                    displayProduct.specs.map((spec) => (
                      <div key={spec.id} className="flex items-center justify-between py-2 border-b border-white/5">
                        <span className="text-gray-400 text-sm">{spec.key}</span>
                        <span className="text-white text-sm font-medium">{spec.value}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-gray-500">{c.empty_specs || '技術規格資料載入中...'}</p>
                  )}
                </div>
              )}

              {/* 詳細說明 */}
              {activeTab === 'description' && (
                <p className="text-gray-400 leading-relaxed whitespace-pre-line">
                  {displayProduct.description}
                </p>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

// ── 路由分發 ─────────────────────────────────────────────────────
export default function Product() {
  const { id } = useParams()
  const { product: c } = useContent()

  return id ? <ProductDetail id={id} c={c} /> : <ProductList c={c} />
}
