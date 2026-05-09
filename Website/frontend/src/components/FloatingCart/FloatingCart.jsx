/**
 * 浮動購物車元件
 * - 右下角固定按鈕，顯示購物車商品數量徽章
 * - 點擊展開迷你購物車面板
 * - 可調整數量、移除商品、前往結帳
 */
import { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useCart } from '../../context/CartContext'

export default function FloatingCart() {
  const { items, setQty, removeItem, totalItems, totalPrice } = useCart()
  const [open, setOpen] = useState(false)
  const [bouncing, setBouncing] = useState(false)
  const panelRef = useRef(null)
  const prevItems = useRef(totalItems)
  const navigate = useNavigate()
  const location = useLocation()

  // 在結帳頁面隱藏浮動購物車（Purchase 已有自己的商品面板）
  const hideOnRoute = location.pathname === '/purchase'

  const itemList = Object.values(items)
  const isEmpty = totalItems === 0

  // totalItems 增加時觸發彈跳動畫
  useEffect(() => {
    if (totalItems > prevItems.current) {
      setBouncing(true)
      const timer = setTimeout(() => setBouncing(false), 400)
      prevItems.current = totalItems
      return () => clearTimeout(timer)
    }
    prevItems.current = totalItems
  }, [totalItems])

  // 點擊面板外側時關閉
  useEffect(() => {
    function handleClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  // 前往結帳
  function handleCheckout() {
    setOpen(false)
    navigate('/purchase')
  }

  // 在結帳頁面不顯示浮動購物車
  if (hideOnRoute) return null

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3" ref={panelRef}>

      {/* ── 迷你購物車面板 ── */}
      {open && (
        <div className="w-80 bg-white border border-gray-200 rounded-2xl shadow-2xl overflow-hidden animate-fade-in dark:bg-gray-900 dark:border-white/10">
          {/* 標題列 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white dark:border-white/10 dark:bg-white/5">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-warm-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">購物車</span>
              <span className="text-xs text-gray-700 dark:text-gray-400">（{totalItems} 件）</span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* 商品清單 */}
          <div className="max-h-72 overflow-y-auto">
            {itemList.length === 0 ? (
              <div className="py-10 text-center text-gray-700 dark:text-gray-400 text-sm">
                <div className="text-3xl mb-2">🛒</div>
                購物車是空的
              </div>
            ) : (
              <ul className="divide-y divide-gray-100 dark:divide-white/5">
                {itemList.map(({ product, qty }) => (
                  <li key={product.id} className="flex items-center gap-3 px-4 py-3">
                    {/* 商品縮圖或佔位 */}
                    <div className="w-10 h-10 rounded-lg bg-white dark:bg-white/5 flex items-center justify-center text-xl flex-shrink-0 overflow-hidden">
                      {product.image
                        ? <img src={product.image} alt={product.name} className="w-full h-full object-cover" />
                        : '🥽'}
                    </div>

                    {/* 商品名稱與價格 */}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{product.name}</p>
                      <p className="text-xs text-warm-600 dark:text-brand-400 mt-0.5">
                        NT${((Number(product.price) || 0) * qty).toLocaleString()}
                      </p>
                    </div>

                    {/* 數量控制 */}
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => setQty(product.id, qty - 1)}
                        disabled={qty <= 1}
                        className="w-6 h-6 rounded-md border border-gray-200 text-gray-700 dark:text-gray-400 dark:border-white/10 hover:border-warm-600/50 hover:text-warm-600 dark:hover:border-brand-500/50 dark:hover:text-brand-400 disabled:opacity-30 transition-all flex items-center justify-center text-sm"
                      >
                        −
                      </button>
                      <span className="w-5 text-center text-xs font-medium text-gray-900 dark:text-white">{qty}</span>
                      <button
                        onClick={() => setQty(product.id, qty + 1)}
                        disabled={qty >= 99}
                        className="w-6 h-6 rounded-md border border-gray-200 text-gray-700 dark:text-gray-400 dark:border-white/10 hover:border-warm-600/50 hover:text-warm-600 dark:hover:border-brand-500/50 dark:hover:text-brand-400 disabled:opacity-30 transition-all flex items-center justify-center text-sm"
                      >
                        ＋
                      </button>
                    </div>

                    {/* 移除按鈕 */}
                    <button
                      onClick={() => removeItem(product.id)}
                      className="text-gray-500 dark:text-gray-400 hover:text-red-400 transition-colors flex-shrink-0"
                      title="移除"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 底部：總計 + 結帳按鈕 */}
          {itemList.length > 0 && (
            <div className="px-4 py-3 border-t border-gray-200 bg-white dark:border-white/10 dark:bg-white/[0.02]">
              <div className="flex justify-between items-center mb-3">
                <span className="text-xs text-gray-700 dark:text-gray-400">總計</span>
                <span className="text-base font-bold text-warm-600 dark:text-brand-400">
                  NT${totalPrice.toLocaleString()}
                </span>
              </div>
              <button
                onClick={handleCheckout}
                className="w-full btn-primary text-sm py-2.5 text-center"
              >
                前往結帳
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── 浮動購物車按鈕 ── */}
      <button
        onClick={() => setOpen(prev => !prev)}
        aria-label="購物車"
        className={`relative w-14 h-14 rounded-full flex items-center justify-center transition-all duration-300 active:scale-95 ${
          bouncing ? 'scale-110' : 'scale-100'
        } ${isEmpty ? 'opacity-60' : 'opacity-100'} ${
          open
            ? 'bg-brand-600 ring-2 ring-brand-400/50 shadow-2xl'
            : isEmpty
              ? 'bg-gray-200 border border-gray-300 shadow-none dark:bg-gray-800 dark:border-white/10'
              : 'shadow-2xl bg-gray-200 border border-gray-300 hover:bg-gray-300 hover:border-warm-500/30 dark:bg-gray-800 dark:border-white/10 dark:hover:bg-gray-700 dark:hover:border-brand-500/30'
        }`}
        title="購物車"
      >
        {/* 購物車圖示 */}
        <svg className={`w-6 h-6 ${open ? 'text-white' : 'text-gray-700 dark:text-gray-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>

        {/* 數量徽章 */}
        {totalItems > 0 && (
          <span className={`absolute -top-1.5 -right-1.5 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-bold flex items-center justify-center shadow-lg transition-transform duration-200 ${bouncing ? 'scale-125' : 'scale-100'}`}>
            {totalItems > 99 ? '99+' : totalItems}
          </span>
        )}
      </button>
    </div>
  )
}
