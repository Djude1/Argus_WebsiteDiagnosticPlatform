import { useState, useEffect, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { fetchProducts, createOrder } from '../../api/client'
import { useContent } from '../../context/ContentContext'
import { useCart } from '../../context/CartContext'
import { useToast } from '../../components/Toast'

const STEPS = [
  { num: 1, label: '選擇商品' },
  { num: 2, label: '填寫資料' },
  { num: 3, label: '確認訂購' },
]

/** 步驟指示器：圓形數字 + 連接線 + 完成打勾，可點擊已完成的步驟跳回 */
function StepIndicator({ currentStep, onStepClick }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-10">
      {STEPS.map((step, i) => (
        <div key={step.num} className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onStepClick(step.num)}
            disabled={step.num > currentStep}
            className={`flex items-center gap-2 transition-colors ${
              currentStep >= step.num
                ? 'text-warm-600 dark:text-brand-400'
                : 'text-gray-400'
            } ${step.num <= currentStep ? 'cursor-pointer' : 'cursor-not-allowed'}`}
          >
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-300 ${
                currentStep >= step.num
                  ? 'bg-warm-500 dark:bg-brand-500 text-white shadow-lg shadow-warm-500/30 dark:shadow-brand-500/30'
                  : 'bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
              }`}
            >
              {currentStep > step.num ? '✓' : step.num}
            </div>
            <span className="text-sm font-medium hidden sm:inline">{step.label}</span>
          </button>
          {i < STEPS.length - 1 && (
            <div
              className={`w-12 sm:w-20 h-0.5 rounded-full transition-all duration-300 ${
                currentStep > step.num
                  ? 'bg-warm-500 dark:bg-brand-500'
                  : 'bg-gray-200 dark:bg-gray-800'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  )
}

const initialContact = {
  customer_name: '',
  customer_email: '',
  customer_phone: '',
  shipping_address: '',
  notes: '',
}

/** 步驟切換動畫設定 */
const stepVariants = {
  enter: (direction) => ({
    x: direction > 0 ? 80 : -80,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction) => ({
    x: direction > 0 ? -80 : 80,
    opacity: 0,
  }),
}

export default function Purchase() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [products, setProducts] = useState([])      // 所有商品
  const [productsError, setProductsError] = useState('')  // 商品載入錯誤
  const [quantities, setQuantities] = useState({})  // { productId: qty }
  const [contact, setContact] = useState(initialContact)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [step, setStep] = useState(1)               // 真正的步驟狀態：1→2→3
  const [direction, setDirection] = useState(1)     // 動畫方向：1=前進, -1=後退
  const { purchase: c } = useContent()
  const { items: cartItems, addItem, setQty: setCartQty, clearCart } = useCart()
  const toast = useToast()
  const urlProductAdded = useRef(false) // 防止 React StrictMode 重複呼叫 addItem

  // 載入商品，並合併購物車與 URL 預選
  useEffect(() => {
    let stale = false // 防止 React StrictMode 重複呼叫 addItem
    const pid = searchParams.get('product')
    fetchProducts()
      .then((res) => {
        if (stale) return // 元件已卸載，忽略過期的 fetch 結果
        const list = res.data.results || res.data
        setProducts(list)
        // 以購物車為基礎，再疊加 URL 預選的產品
        setQuantities(prev => {
          // 先將購物車內容同步進來（保留頁面上已調整的數量）
          const fromCart = {}
          Object.entries(cartItems).forEach(([id, { qty }]) => {
            fromCart[id] = prev[id] ?? qty
          })
          // URL 帶入的產品：若尚未在購物車中，用 addItem 加入確保 product 資料完整
          if (pid && !urlProductAdded.current) {
            const urlProduct = list.find(p => String(p.id) === String(pid))
            if (urlProduct) {
              addItem(urlProduct, 1)
              urlProductAdded.current = true
            }
            fromCart[pid] = fromCart[pid] || 1
          } else if (pid) {
            fromCart[pid] = fromCart[pid] || 1
          }
          return fromCart
        })
      })
      .catch((err) => {
        if (stale) return
        console.error(err)
        setProductsError('商品資料載入失敗，請重新整理頁面再試。')
      })
    return () => { stale = true }
  }, [searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  // 即時同步購物車變更到本地數量（如從其他分頁或返回時購物車已變動）
  useEffect(() => {
    if (Object.keys(cartItems).length === 0 && Object.keys(quantities).some(k => (quantities[k] || 0) > 0)) {
      // 購物車被清空但本地仍有商品 → 全部歸零
      setQuantities({})
      return
    }
    if (Object.keys(cartItems).length === 0) return
    setQuantities(prev => {
      const updated = { ...prev }
      let changed = false
      Object.entries(cartItems).forEach(([id, { qty }]) => {
        if (updated[id] !== qty) {
          updated[id] = qty
          changed = true
        }
      })
      return changed ? updated : prev
    })
  }, [cartItems]) // eslint-disable-line react-hooks/exhaustive-deps

  // 目前有數量 > 0 的商品列表
  const selectedItems = products
    .filter((p) => (quantities[p.id] || 0) > 0)
    .map((p) => ({ product: p, qty: quantities[p.id] }))

  const totalPrice = selectedItems.reduce(
    (sum, { product, qty }) => sum + (Number(product.price) || 0) * qty, 0
  )

  function setQty(productId, delta) {
    const currentQty = quantities[productId] || 0
    const nextQty = Math.max(0, currentQty + delta)
    // 更新本地數量狀態
    setQuantities((prev) => ({ ...prev, [productId]: nextQty }))
    // 同步回購物車（在 updater 外呼叫，避免渲染期間狀態更新）
    const productObj = products.find(p => String(p.id) === String(productId))
    if (productObj) {
      if (nextQty > 0 && !cartItems[productId]) {
        // 新商品：用 addItem 確保 product 資料完整
        addItem(productObj, nextQty)
      } else if (cartItems[productId]) {
        // 已存在商品：用 setCartQty 更新數量
        setCartQty(productId, nextQty)
      }
    }
  }

  function handleContact(e) {
    const { name, value } = e.target
    setContact((prev) => ({ ...prev, [name]: value }))
    // 開始輸入時清除該欄位錯誤
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: '' }))
  }

  // 即時驗證單一欄位（onBlur 觸發）
  function validateField(name, value) {
    let msg = ''
    const v = (value || '').trim()
    switch (name) {
      case 'customer_name':
        if (!v) msg = '請填寫姓名'
        else if (v.length < 2) msg = '姓名至少需要 2 個字元'
        break
      case 'customer_email':
        if (!v) msg = '請填寫 Email'
        else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) msg = 'Email 格式不正確'
        break
      case 'customer_phone':
        if (!v) msg = '請填寫電話'
        else if (!/^09\d{8}$/.test(v)) msg = '請輸入正確的台灣手機號碼（09 開頭，共 10 位數字）'
        break
      case 'shipping_address':
        if (!v) msg = '請填寫收件地址'
        else if (v.length < 5) msg = '地址至少需要 5 個字元'
        break
      default:
        break
    }
    setErrors((prev) => ({ ...prev, [name]: msg }))
    return msg
  }

  function validate() {
    const e = {}
    // 姓名驗證
    if (!contact.customer_name.trim()) e.customer_name = '請填寫姓名'
    else if (contact.customer_name.trim().length < 2) e.customer_name = '姓名至少需要 2 個字元'
    // Email 驗證
    if (!contact.customer_email.trim()) e.customer_email = '請填寫 Email'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact.customer_email)) e.customer_email = 'Email 格式不正確'
    // 電話驗證
    if (!contact.customer_phone.trim()) e.customer_phone = '請填寫電話'
    else if (!/^09\d{8}$/.test(contact.customer_phone.trim())) e.customer_phone = '請輸入正確的台灣手機號碼（09 開頭，共 10 位數字）'
    // 地址驗證
    if (!contact.shipping_address.trim()) e.shipping_address = '請填寫收件地址'
    else if (contact.shipping_address.trim().length < 5) e.shipping_address = '地址至少需要 5 個字元'
    // 商品驗證
    if (selectedItems.length === 0) e.items = '請至少選擇一項商品'
    return e
  }

  /** 步驟導航：帶方向動畫 */
  function goToStep(target) {
    if (target < 1 || target > 3) return
    setDirection(target > step ? 1 : -1)
    setStep(target)
    // 滾動至頁面頂部
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  /** Step 1 → Step 2：需至少選一項商品 */
  function handleNextFromStep1() {
    if (selectedItems.length === 0) {
      setErrors({ items: '請至少選擇一項商品' })
      return
    }
    setErrors({})
    goToStep(2)
  }

  /** Step 2 → Step 3：需表單驗證通過 */
  function handleNextFromStep2() {
    const errs = validate()
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }
    goToStep(3)
  }

  /** StepIndicator 點擊已完成的步驟跳回 */
  function handleStepClick(targetStep) {
    if (targetStep >= step) return
    goToStep(targetStep)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length > 0) { setErrors(errs); return }

    setSubmitting(true)
    try {
      // 建立訂單
      const orderRes = await createOrder({
        ...contact,
        items: selectedItems.map(({ product, qty }) => ({
          product_id: product.id,
          quantity: qty,
        })),
      })
      const orderNumber = orderRes.data.order.order_number
      clearCart()
      // 直接跳轉到訂單成功頁面（使用 order_number 而非 PK，防止列舉攻擊）
      navigate(`/purchase/result?order_number=${orderNumber}`)
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
      toast.error('訂單送出失敗，請稍後再試')
      setSubmitting(false)
    }
  }

  const contactFields = [
    { name: 'customer_name', label: c.label_name || '姓名', type: 'text', placeholder: c.placeholder_name || '請輸入您的姓名' },
    { name: 'customer_email', label: c.label_email || 'Email', type: 'email', placeholder: c.placeholder_email || 'example@mail.com' },
    { name: 'customer_phone', label: c.label_phone || '電話', type: 'tel', placeholder: c.placeholder_phone || '09XX-XXX-XXX' },
  ]

  // ── submitting 覆蓋畫面 ──
  if (submitting) {
    return (
      <div className="pt-24 pb-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <h1 className="section-title">{c.page_title || '立即購買'}</h1>
          <StepIndicator currentStep={3} onStepClick={() => {}} />
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-12 h-12 border-4 border-warm-500 dark:border-brand-500 border-t-transparent rounded-full animate-spin mb-6" />
            <p className="text-lg font-medium text-gray-700 dark:text-gray-300">正在送出訂單…</p>
            <p className="text-sm text-gray-700 dark:text-gray-400 mt-2">請稍候，即將前往訂單確認頁面</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="pt-24 pb-20">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="section-title">{c.page_title || '立即購買'}</h1>
        <p className="section-subtitle">
          {c.subtitle || '填寫以下資訊完成訂購，我們將在 1-2 個工作天內聯繫您確認出貨細節。'}
        </p>

        <StepIndicator currentStep={step} onStepClick={handleStepClick} />

        <AnimatePresence mode="wait" custom={direction}>
          {/* ══════════ Step 1：選擇商品 ══════════ */}
          {step === 1 && (
            <motion.div
              key="step1"
              custom={direction}
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.3, ease: 'easeInOut' }}
            >
              {errors.items && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm mb-6">
                  {errors.items}
                </div>
              )}

              {productsError ? (
                <div className="glass rounded-2xl p-12 text-center">
                  <div className="text-4xl mb-4">⚠️</div>
                  <p className="text-gray-600 dark:text-gray-400 mb-4">{productsError}</p>
                  <button
                    type="button"
                    onClick={() => window.location.reload()}
                    className="btn-primary text-sm"
                  >
                    重新整理
                  </button>
                </div>
              ) : products.length === 0 ? (
                <div className="glass rounded-2xl p-12 text-center text-gray-700 dark:text-gray-400">
                  商品資料載入中...
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {products.map((p) => {
                    const qty = quantities[p.id] || 0
                    return (
                      <div
                        key={p.id}
                        className={`glass rounded-2xl p-5 transition-all duration-300 ${
                          qty > 0
                            ? 'border-2 border-warm-500/50 dark:border-brand-500/50 shadow-lg shadow-warm-500/10 dark:shadow-brand-500/10'
                            : 'border border-gray-200 dark:border-white/10'
                        }`}
                      >
                        <div className="flex flex-col gap-3">
                          <div>
                            <p className="text-base font-semibold text-gray-900 dark:text-white">{p.name}</p>
                            <p className="text-xs text-gray-700 mt-1 line-clamp-2">{p.short_description}</p>
                            <p className="text-warm-600 dark:text-brand-400 text-lg font-bold mt-2">
                              NT${(Number(p.price) || 0).toLocaleString()}
                            </p>
                          </div>
                          {/* 數量控制 */}
                          <div className="flex items-center gap-3">
                            <button
                              type="button"
                              onClick={() => setQty(p.id, -1)}
                              disabled={qty === 0}
                              className="w-8 h-8 rounded-lg border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-400 hover:border-warm-600/50 hover:text-warm-600 dark:hover:border-brand-500/50 dark:hover:text-brand-400 disabled:opacity-30 transition-all flex items-center justify-center text-lg leading-none"
                            >
                              −
                            </button>
                            <span className={`w-6 text-center text-sm font-semibold tabular-nums ${qty > 0 ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400'}`}>
                              {qty}
                            </span>
                            <button
                              type="button"
                              onClick={() => setQty(p.id, 1)}
                              disabled={qty >= 99}
                              className="w-8 h-8 rounded-lg border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-400 hover:border-warm-600/50 hover:text-warm-600 dark:hover:border-brand-500/50 dark:hover:text-brand-400 disabled:opacity-30 transition-all flex items-center justify-center text-lg leading-none"
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

              {/* 右下角浮動訂單摘要面板 */}
              {selectedItems.length > 0 && (
                <div className="fixed bottom-6 right-6 z-30 glass rounded-2xl p-4 shadow-xl border border-warm-500/20 dark:border-brand-500/20 max-w-xs">
                  <p className="text-xs font-medium text-gray-700 mb-2">已選 {selectedItems.length} 項商品</p>
                  <div className="space-y-1 max-h-24 overflow-y-auto">
                    {selectedItems.map(({ product, qty }) => (
                      <div key={product.id} className="flex justify-between text-xs">
                        <span className="text-gray-700 dark:text-gray-300 truncate max-w-[65%]">
                          {product.name} × {qty}
                        </span>
                        <span className="text-gray-900 dark:text-white font-medium">
                          NT${((Number(product.price) || 0) * qty).toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="flex justify-between text-sm font-bold pt-2 mt-2 border-t border-gray-200 dark:border-white/10">
                    <span className="text-gray-900 dark:text-white">小計</span>
                    <span className="text-warm-600 dark:text-brand-400">NT${totalPrice.toLocaleString()}</span>
                  </div>
                </div>
              )}

              {/* 下一步按鈕 */}
              <div className="flex justify-end mt-8">
                <motion.button
                  type="button"
                  onClick={handleNextFromStep1}
                  disabled={selectedItems.length === 0}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed px-8"
                >
                  下一步：填寫資料
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* ══════════ Step 2：填寫資料 ══════════ */}
          {step === 2 && (
            <motion.div
              key="step2"
              custom={direction}
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.3, ease: 'easeInOut' }}
            >
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
                {/* 左側：訂單摘要（sticky） */}
                <div className="lg:col-span-2">
                  <div className="glass rounded-2xl p-6 lg:sticky lg:top-24">
                    <h2 className="font-semibold text-gray-900 dark:text-white mb-4">{c.order_summary_title || '訂單摘要'}</h2>
                    {selectedItems.length === 0 ? (
                      <p className="text-gray-700 dark:text-gray-400 text-sm text-center py-4">尚未選擇任何商品</p>
                    ) : (
                      <div className="space-y-2">
                        {selectedItems.map(({ product, qty }) => (
                          <div key={product.id} className="flex justify-between text-sm">
                            <span className="text-gray-700 dark:text-gray-300 truncate max-w-[60%]">
                              {product.name}
                              <span className="text-gray-700 ml-1">× {qty}</span>
                            </span>
                            <span className="text-gray-900 dark:text-white font-medium">
                              NT${((Number(product.price) || 0) * qty).toLocaleString()}
                            </span>
                          </div>
                        ))}
                        <div className="flex justify-between text-base font-semibold pt-3 border-t border-gray-200 dark:border-white/10">
                          <span className="text-gray-900 dark:text-white">{c.label_total || '總計'}</span>
                          <span className="text-warm-600 dark:text-brand-400">NT${totalPrice.toLocaleString()}</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* 右側：聯絡資訊表單 */}
                <div className="lg:col-span-3">
                  <form onSubmit={(e) => { e.preventDefault(); handleNextFromStep2() }} className="space-y-5">
                    {errors.general && (
                      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">
                        {errors.general}
                      </div>
                    )}

                    {contactFields.map((field) => (
                      <div key={field.name} className="relative">
                        <label htmlFor={field.name} className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          {field.label} <span className="text-red-400">*</span>
                        </label>
                        <input
                          id={field.name}
                          type={field.type}
                          name={field.name}
                          value={contact[field.name]}
                          onChange={handleContact}
                          onBlur={() => validateField(field.name, contact[field.name])}
                          placeholder={field.placeholder}
                          aria-invalid={!!errors[field.name]}
                          aria-describedby={errors[field.name] ? `${field.name}-error` : undefined}
                          className={`w-full bg-white dark:bg-white/5 border rounded-xl px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:border-warm-500 dark:focus:border-brand-500 transition-colors ${
                            errors[field.name] ? 'border-red-500 focus:border-red-500' : 'border-gray-200 dark:border-white/10'
                          }`}
                        />
                        {errors[field.name] && (
                          <p id={`${field.name}-error`} role="alert" className="text-red-500 text-xs mt-1">{errors[field.name]}</p>
                        )}
                      </div>
                    ))}

                    <div className="relative">
                      <label htmlFor="shipping_address" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {c.label_address || '收件地址'} <span className="text-red-400">*</span>
                      </label>
                      <textarea
                        id="shipping_address"
                        name="shipping_address"
                        value={contact.shipping_address}
                        onChange={handleContact}
                        onBlur={() => validateField('shipping_address', contact.shipping_address)}
                        placeholder={c.placeholder_address || '請輸入完整收件地址（含縣市、鄉鎮、路名、門牌號碼）'}
                        rows={3}
                        aria-invalid={!!errors.shipping_address}
                        aria-describedby={errors.shipping_address ? 'shipping_address-error' : undefined}
                        className={`w-full bg-white dark:bg-white/5 border rounded-xl px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:border-warm-500 dark:focus:border-brand-500 transition-colors resize-none ${
                          errors.shipping_address ? 'border-red-500 focus:border-red-500' : 'border-gray-200 dark:border-white/10'
                        }`}
                      />
                      {errors.shipping_address && (
                        <p id="shipping_address-error" role="alert" className="text-red-500 text-xs mt-1">{errors.shipping_address}</p>
                      )}
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{c.label_notes || '備註（選填）'}</label>
                      <textarea
                        name="notes"
                        value={contact.notes}
                        onChange={handleContact}
                        placeholder={c.placeholder_notes || '有任何特殊需求請填寫於此'}
                        rows={2}
                        className="w-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:border-warm-500 dark:focus:border-brand-500 transition-colors resize-none"
                      />
                    </div>

                    {/* 導航按鈕 */}
                    <div className="flex flex-col sm:flex-row gap-3 pt-2">
                      <motion.button
                        type="button"
                        onClick={() => goToStep(1)}
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.99 }}
                        className="btn-outline flex-1"
                      >
                        ← 上一步
                      </motion.button>
                      <motion.button
                        type="submit"
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.99 }}
                        className="btn-primary flex-1"
                      >
                        前往確認
                      </motion.button>
                    </div>
                  </form>
                </div>
              </div>
            </motion.div>
          )}

          {/* ══════════ Step 3：確認預覽 + 送出 ══════════ */}
          {step === 3 && (
            <motion.div
              key="step3"
              custom={direction}
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.3, ease: 'easeInOut' }}
            >
              <form onSubmit={handleSubmit}>
                {errors.general && (
                  <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm mb-6">
                    {errors.general}
                  </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  {/* 左側：訂單明細 */}
                  <div className="glass rounded-2xl p-6">
                    <h2 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      📦 商品明細
                    </h2>
                    <div className="space-y-3">
                      {selectedItems.map(({ product, qty }) => (
                        <div key={product.id} className="flex justify-between items-start text-sm border-b border-gray-100 dark:border-white/5 pb-3">
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-gray-900 dark:text-white">{product.name}</p>
                            <p className="text-xs text-gray-700 mt-0.5">
                              NT${(Number(product.price) || 0).toLocaleString()} × {qty}
                            </p>
                          </div>
                          <span className="text-gray-900 dark:text-white font-semibold ml-4">
                            NT${((Number(product.price) || 0) * qty).toLocaleString()}
                          </span>
                        </div>
                      ))}
                    </div>
                    <div className="flex justify-between items-center text-lg font-bold pt-4 mt-4 border-t-2 border-warm-500/30 dark:border-brand-500/30">
                      <span className="text-gray-900 dark:text-white">總計</span>
                      <span className="text-warm-600 dark:text-brand-400">NT${totalPrice.toLocaleString()}</span>
                    </div>
                  </div>

                  {/* 右側：聯絡資訊 */}
                  <div className="glass rounded-2xl p-6">
                    <h2 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      👤 聯絡資訊
                    </h2>
                    <div className="space-y-3 text-sm">
                      <div className="flex gap-2">
                        <span className="text-gray-700 w-16 flex-shrink-0">姓名</span>
                        <span className="text-gray-900 dark:text-white font-medium">{contact.customer_name}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="text-gray-700 w-16 flex-shrink-0">Email</span>
                        <span className="text-gray-900 dark:text-white font-medium">{contact.customer_email}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="text-gray-700 w-16 flex-shrink-0">電話</span>
                        <span className="text-gray-900 dark:text-white font-medium">{contact.customer_phone}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="text-gray-700 w-16 flex-shrink-0">地址</span>
                        <span className="text-gray-900 dark:text-white font-medium">{contact.shipping_address}</span>
                      </div>
                      {contact.notes && (
                        <div className="flex gap-2">
                          <span className="text-gray-700 w-16 flex-shrink-0">備註</span>
                          <span className="text-gray-900 dark:text-white font-medium">{contact.notes}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* 導航按鈕 */}
                <div className="flex flex-col sm:flex-row gap-4 mt-8">
                  <motion.button
                    type="button"
                    onClick={() => goToStep(2)}
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    className="btn-outline flex-1"
                  >
                    ← 上一步：修改資料
                  </motion.button>
                  <motion.button
                    type="submit"
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    disabled={submitting}
                    className="flex-1 py-4 px-6 rounded-2xl text-white font-bold text-lg transition-all duration-300 bg-gradient-to-r from-warm-500 to-warm-600 hover:from-warm-400 hover:to-warm-500 dark:from-brand-500 dark:to-brand-600 dark:hover:from-brand-400 dark:hover:to-brand-500 shadow-lg shadow-warm-500/25 hover:shadow-warm-500/40 dark:shadow-brand-500/25 dark:hover:shadow-brand-500/40 flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9 11l3 3L22 4" />
                      <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                    </svg>
                    確認訂購 NT${totalPrice.toLocaleString()}
                  </motion.button>
                </div>
              </form>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
