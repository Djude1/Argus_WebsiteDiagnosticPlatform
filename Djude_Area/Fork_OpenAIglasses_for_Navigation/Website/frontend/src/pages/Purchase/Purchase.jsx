import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchProducts, createOrder } from '../../api/client'
import { useContent } from '../../context/ContentContext'
import { useCart } from '../../context/CartContext'

const initialContact = {
  customer_name: '',
  customer_email: '',
  customer_phone: '',
  shipping_address: '',
  notes: '',
}

export default function Purchase() {
  const [searchParams] = useSearchParams()
  const [products, setProducts] = useState([])      // 所有商品
  const [quantities, setQuantities] = useState({})  // { productId: qty }
  const [contact, setContact] = useState(initialContact)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [orderResult, setOrderResult] = useState(null)
  const { purchase: c } = useContent()
  const { items: cartItems, setQty: setCartQty, clearCart } = useCart()

  // 載入商品，並合併購物車與 URL 預選
  useEffect(() => {
    const pid = searchParams.get('product')
    fetchProducts()
      .then((res) => {
        const list = res.data.results || res.data
        setProducts(list)
        // 以購物車為基礎，再疊加 URL 帶入的產品
        setQuantities(prev => {
          // 先將購物車內容同步進來（保留頁面上已調整的數量）
          const fromCart = {}
          Object.entries(cartItems).forEach(([id, { qty }]) => {
            fromCart[id] = prev[id] ?? qty
          })
          // URL 帶入的產品：若尚未加入才設為 1
          if (pid) {
            fromCart[pid] = fromCart[pid] || 1
          }
          return fromCart
        })
      })
      .catch(console.error)
  }, [searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  // 目前有數量 > 0 的商品列表
  const selectedItems = products
    .filter((p) => (quantities[p.id] || 0) > 0)
    .map((p) => ({ product: p, qty: quantities[p.id] }))

  const totalPrice = selectedItems.reduce(
    (sum, { product, qty }) => sum + Number(product.price) * qty, 0
  )

  function setQty(productId, delta) {
    setQuantities((prev) => {
      const next = Math.max(0, (prev[productId] || 0) + delta)
      // 同步回購物車（確保浮動購物車數量一致）
      const productObj = products.find(p => String(p.id) === String(productId))
      if (productObj) {
        setCartQty(productId, next)
      }
      return { ...prev, [productId]: next }
    })
  }

  function handleContact(e) {
    const { name, value } = e.target
    setContact((prev) => ({ ...prev, [name]: value }))
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: '' }))
  }

  function validate() {
    const e = {}
    if (!contact.customer_name.trim()) e.customer_name = '請填寫姓名'
    if (!contact.customer_email.trim()) e.customer_email = '請填寫 Email'
    else if (!/\S+@\S+\.\S+/.test(contact.customer_email)) e.customer_email = 'Email 格式不正確'
    if (!contact.customer_phone.trim()) e.customer_phone = '請填寫電話'
    if (!contact.shipping_address.trim()) e.shipping_address = '請填寫收件地址'
    if (selectedItems.length === 0) e.items = '請至少選擇一項商品'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length > 0) { setErrors(errs); return }

    setSubmitting(true)
    try {
      const res = await createOrder({
        ...contact,
        items: selectedItems.map(({ product, qty }) => ({
          product_id: product.id,
          quantity: qty,
        })),
      })
      setOrderResult(res.data)
      clearCart()  // 訂單成功後清空購物車
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const serverErrors = {}
        Object.entries(data).forEach(([key, val]) => {
          serverErrors[key] = Array.isArray(val) ? val[0] : String(val)
        })
        setErrors(serverErrors)
      } else {
        setErrors({ general: '訂單送出失敗，請稍後再試。' })
      }
    } finally {
      setSubmitting(false)
    }
  }

  // ── 訂單成功頁面 ────────────────────────────────────────────────
  if (orderResult) {
    const emailHint = (c.success_email_hint || '確認信將寄至 {email}，我們將儘快與您聯繫。')
      .replace('{email}', orderResult.order.customer_email)

    return (
      <div className="min-h-screen pt-24 flex items-center justify-center px-4">
        <div className="max-w-lg w-full glass rounded-3xl p-10 text-center glow-border">
          <div className="text-6xl mb-6">{c.success_icon || '✅'}</div>
          <h2 className="text-2xl font-bold text-white mb-2">{c.success_title || '訂單建立成功！'}</h2>
          <p className="text-gray-400 mb-6">{orderResult.message}</p>
          <div className="bg-white/5 rounded-2xl p-6 text-left mb-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{c.success_label_order || '訂單編號'}</span>
              <span className="text-brand-400 font-mono">{orderResult.order.order_number}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{c.success_label_buyer || '購買人'}</span>
              <span className="text-white">{orderResult.order.customer_name}</span>
            </div>
            {/* 訂購明細 */}
            {orderResult.order.items?.length > 0 && (
              <div className="pt-2 border-t border-white/10 space-y-1">
                {orderResult.order.items.map((item) => (
                  <div key={item.id} className="flex justify-between text-sm">
                    <span className="text-gray-400">{item.product_name} × {item.quantity}</span>
                    <span className="text-white">NT${(Number(item.price) * item.quantity).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-between text-base font-semibold pt-2 border-t border-white/10">
              <span className="text-white">{c.success_label_amount || '總金額'}</span>
              <span className="text-brand-400">NT${Number(orderResult.order.total_price).toLocaleString()}</span>
            </div>
          </div>
          <p className="text-gray-500 text-sm mb-6">{emailHint}</p>
          <button
            onClick={() => { setOrderResult(null); setContact(initialContact); setQuantities({}); clearCart() }}
            className="btn-outline w-full"
          >
            {c.btn_reorder || '再次訂購'}
          </button>
        </div>
      </div>
    )
  }

  const contactFields = [
    { name: 'customer_name', label: c.label_name || '姓名', type: 'text', placeholder: c.placeholder_name || '請輸入您的姓名' },
    { name: 'customer_email', label: c.label_email || 'Email', type: 'email', placeholder: c.placeholder_email || 'example@mail.com' },
    { name: 'customer_phone', label: c.label_phone || '電話', type: 'tel', placeholder: c.placeholder_phone || '09XX-XXX-XXX' },
  ]

  return (
    <div className="pt-24 pb-20">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="section-title">{c.page_title || '立即購買'}</h1>
        <p className="section-subtitle">
          {c.subtitle || '填寫以下資訊完成訂購，我們將在 1-2 個工作天內聯繫您確認出貨細節。'}
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">

          {/* ── 左側：商品選擇 + 訂單摘要 ── */}
          <div className="lg:col-span-2 space-y-4">

            {/* 商品選擇 */}
            <div className="glass rounded-2xl p-6">
              <h2 className="font-semibold text-white mb-4">{c.select_products_title || '選擇商品'}</h2>
              {errors.items && (
                <p className="text-red-400 text-xs mb-3">{errors.items}</p>
              )}
              {products.length === 0 ? (
                <div className="text-center text-gray-500 py-6">商品資料載入中...</div>
              ) : (
                <div className="space-y-3">
                  {products.map((p) => {
                    const qty = quantities[p.id] || 0
                    return (
                      <div
                        key={p.id}
                        className={`rounded-xl border p-4 transition-all ${
                          qty > 0
                            ? 'border-brand-500/50 bg-brand-500/5'
                            : 'border-white/10 bg-white/[0.02]'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-white truncate">{p.name}</p>
                            <p className="text-xs text-gray-500 mt-0.5 truncate">{p.short_description}</p>
                            <p className="text-brand-400 text-sm font-semibold mt-1">
                              NT${Number(p.price).toLocaleString()}
                            </p>
                          </div>
                          {/* 數量控制 */}
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <button
                              type="button"
                              onClick={() => setQty(p.id, -1)}
                              disabled={qty === 0}
                              className="w-7 h-7 rounded-lg border border-white/10 text-gray-400 hover:border-brand-500/50 hover:text-brand-400 disabled:opacity-30 transition-all flex items-center justify-center text-lg leading-none"
                            >
                              −
                            </button>
                            <span className={`w-5 text-center text-sm font-medium ${qty > 0 ? 'text-white' : 'text-gray-500'}`}>
                              {qty}
                            </span>
                            <button
                              type="button"
                              onClick={() => setQty(p.id, 1)}
                              disabled={qty >= 99}
                              className="w-7 h-7 rounded-lg border border-white/10 text-gray-400 hover:border-brand-500/50 hover:text-brand-400 disabled:opacity-30 transition-all flex items-center justify-center text-lg leading-none"
                            >
                              ＋
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* 訂單摘要 */}
            <div className="glass rounded-2xl p-6 lg:sticky lg:top-24">
              <h2 className="font-semibold text-white mb-4">{c.order_summary_title || '訂單摘要'}</h2>
              {selectedItems.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-4">尚未選擇任何商品</p>
              ) : (
                <div className="space-y-2">
                  {selectedItems.map(({ product, qty }) => (
                    <div key={product.id} className="flex justify-between text-sm">
                      <span className="text-gray-300 truncate max-w-[60%]">
                        {product.name}
                        <span className="text-gray-500 ml-1">× {qty}</span>
                      </span>
                      <span className="text-white font-medium">
                        NT${(Number(product.price) * qty).toLocaleString()}
                      </span>
                    </div>
                  ))}
                  <div className="flex justify-between text-base font-semibold pt-3 border-t border-white/10">
                    <span className="text-white">{c.label_total || '總計'}</span>
                    <span className="text-brand-400">NT${totalPrice.toLocaleString()}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── 右側：聯絡資訊表單 ── */}
          <div className="lg:col-span-3">
            <form onSubmit={handleSubmit} className="space-y-5">
              {errors.general && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">
                  {errors.general}
                </div>
              )}

              {contactFields.map((field) => (
                <div key={field.name}>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    {field.label} <span className="text-red-400">*</span>
                  </label>
                  <input
                    type={field.type}
                    name={field.name}
                    value={contact[field.name]}
                    onChange={handleContact}
                    placeholder={field.placeholder}
                    className={`w-full bg-white/5 border rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-brand-500 transition-colors ${
                      errors[field.name] ? 'border-red-500/50' : 'border-white/10'
                    }`}
                  />
                  {errors[field.name] && (
                    <p className="mt-1 text-xs text-red-400">{errors[field.name]}</p>
                  )}
                </div>
              ))}

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {c.label_address || '收件地址'} <span className="text-red-400">*</span>
                </label>
                <textarea
                  name="shipping_address"
                  value={contact.shipping_address}
                  onChange={handleContact}
                  placeholder={c.placeholder_address || '請輸入完整收件地址（含縣市、鄉鎮、路名、門牌號碼）'}
                  rows={3}
                  className={`w-full bg-white/5 border rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-brand-500 transition-colors resize-none ${
                    errors.shipping_address ? 'border-red-500/50' : 'border-white/10'
                  }`}
                />
                {errors.shipping_address && (
                  <p className="mt-1 text-xs text-red-400">{errors.shipping_address}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">{c.label_notes || '備註（選填）'}</label>
                <textarea
                  name="notes"
                  value={contact.notes}
                  onChange={handleContact}
                  placeholder={c.placeholder_notes || '有任何特殊需求請填寫於此'}
                  rows={2}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-brand-500 transition-colors resize-none"
                />
              </div>

              <button
                type="submit"
                disabled={submitting || selectedItems.length === 0}
                className="btn-primary w-full text-center disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    {c.btn_submitting || '處理中...'}
                  </span>
                ) : (
                  selectedItems.length > 0
                    ? `${c.btn_submit || '確認訂購'} NT$${totalPrice.toLocaleString()}`
                    : c.btn_submit || '確認訂購'
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
