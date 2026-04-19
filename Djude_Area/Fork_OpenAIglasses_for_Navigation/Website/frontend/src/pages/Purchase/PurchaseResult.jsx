/**
 * /purchase/result?order_number=ORD-XXXXXXXX
 * 訂單成功頁面 — 顯示訂單詳情
 */
import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { getOrder } from '../../api/client'

export default function PurchaseResult() {
  const [searchParams] = useSearchParams()
  const orderNumber = searchParams.get('order_number')

  const [order, setOrder]       = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')

  useEffect(() => {
    if (!orderNumber) {
      setError('無效的訂單連結')
      setLoading(false)
      return
    }

    getOrder(orderNumber)
      .then(res => {
        setOrder(res.data)
        setLoading(false)
      })
      .catch(() => {
        setError('無法查詢訂單，請聯繫客服。')
        setLoading(false)
      })
  }, [orderNumber])

  if (loading) {
    return (
      <div className="min-h-screen pt-24 flex items-center justify-center px-4">
        <div className="text-center text-gray-600 dark:text-gray-400">
          <div className="w-12 h-12 border-4 border-warm-500 dark:border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-lg">正在載入訂單資料…</p>
          <p className="text-sm mt-2 text-gray-700 dark:text-gray-400">請稍候</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen pt-24 flex items-center justify-center px-4">
        <div className="max-w-md w-full glass rounded-3xl p-10 text-center">
          <div className="text-6xl mb-6">⚠️</div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">發生錯誤</h2>
          <p className="text-gray-700 dark:text-gray-400 mb-6">{error}</p>
          <Link to="/purchase" className="btn-outline w-full block text-center">返回購買頁</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen pt-24 flex items-center justify-center px-4">
      <div className="max-w-lg w-full glass rounded-3xl p-10 text-center glow-border">
        <div className="text-6xl mb-6">✅</div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">訂單已送出！</h2>
        <p className="text-gray-700 dark:text-gray-400 mb-6">我們已收到您的訂單，將在 1-2 個工作天內聯繫您確認出貨細節。</p>

        {/* 訂單資訊 */}
        {order && (
          <div className="bg-white dark:bg-white/5 rounded-2xl p-6 text-left mb-6 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-700 dark:text-gray-400">訂單編號</span>
              <span className="text-warm-600 dark:text-brand-400 font-mono">{order.order_number}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-700">購買人</span>
              <span className="text-gray-900 dark:text-white">{order.customer_name}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-700">訂單狀態</span>
              <span className="text-gray-900 dark:text-white">{order.status_display || order.status}</span>
            </div>
            {order.items?.length > 0 && (
              <div className="pt-2 border-t border-gray-200 dark:border-white/10 space-y-1">
                {order.items.map((item) => (
                  <div key={item.id} className="flex justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-400">{item.product_name} × {item.quantity}</span>
                    <span className="text-gray-900 dark:text-white">NT${((Number(item.price) || 0) * item.quantity).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-between text-base font-semibold pt-2 border-t border-gray-200 dark:border-white/10">
              <span className="text-gray-900 dark:text-white">總金額</span>
              <span className="text-warm-600 dark:text-brand-400">NT${(Number(order.total_price) || 0).toLocaleString()}</span>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <Link to="/" className="btn-primary w-full block text-center">
            返回首頁
          </Link>
          <Link to="/purchase" className="btn-outline w-full block text-center">
            繼續購買
          </Link>
        </div>
      </div>
    </div>
  )
}
