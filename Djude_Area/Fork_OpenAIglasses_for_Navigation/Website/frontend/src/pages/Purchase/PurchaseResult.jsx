/**
 * /purchase/result?order_id=xxx
 * 綠界付款後的跳轉頁面（或手動查詢付款狀態）
 */
import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { getPaymentStatus } from '../../api/client'

export default function PurchaseResult() {
  const [searchParams] = useSearchParams()
  const orderId = searchParams.get('order_id')

  const [result, setResult]   = useState(null)  // { payment_status, order }
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  useEffect(() => {
    if (!orderId) {
      setError('無效的訂單連結')
      setLoading(false)
      return
    }

    // 最多輪詢 12 次（約 60 秒），等待綠界 webhook 更新付款狀態
    let attempts = 0
    const poll = async () => {
      try {
        const res = await getPaymentStatus(orderId)
        const data = res.data
        // 付款結果已確認（paid 或 failed）則停止輪詢
        if (data.payment_status !== 'unpaid' || attempts >= 12) {
          setResult(data)
          setLoading(false)
        } else {
          attempts++
          setTimeout(poll, 5000)
        }
      } catch {
        setError('無法查詢訂單狀態，請聯繫客服。')
        setLoading(false)
      }
    }
    poll()
  }, [orderId])

  if (loading) {
    return (
      <div className="min-h-screen pt-24 flex items-center justify-center px-4">
        <div className="text-center text-gray-400">
          <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-lg">正在確認付款結果…</p>
          <p className="text-sm mt-2 text-gray-500">請稍候，這可能需要幾秒鐘</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen pt-24 flex items-center justify-center px-4">
        <div className="max-w-md w-full glass rounded-3xl p-10 text-center">
          <div className="text-6xl mb-6">⚠️</div>
          <h2 className="text-2xl font-bold text-white mb-4">發生錯誤</h2>
          <p className="text-gray-400 mb-6">{error}</p>
          <Link to="/purchase" className="btn-outline w-full block text-center">返回購買頁</Link>
        </div>
      </div>
    )
  }

  const { payment_status, order } = result
  const isPaid = payment_status === 'paid'
  const isFailed = payment_status === 'failed'

  return (
    <div className="min-h-screen pt-24 flex items-center justify-center px-4">
      <div className="max-w-lg w-full glass rounded-3xl p-10 text-center glow-border">

        {/* 付款成功 */}
        {isPaid && (
          <>
            <div className="text-6xl mb-6">✅</div>
            <h2 className="text-2xl font-bold text-white mb-2">付款成功！</h2>
            <p className="text-gray-400 mb-6">訂單已確認，我們將儘快出貨。</p>
          </>
        )}

        {/* 付款失敗 */}
        {isFailed && (
          <>
            <div className="text-6xl mb-6">❌</div>
            <h2 className="text-2xl font-bold text-white mb-2">付款失敗</h2>
            <p className="text-gray-400 mb-6">交易未完成，請重新嘗試。</p>
          </>
        )}

        {/* 待確認（超時仍未收到 webhook）*/}
        {!isPaid && !isFailed && (
          <>
            <div className="text-6xl mb-6">⏳</div>
            <h2 className="text-2xl font-bold text-white mb-2">付款確認中</h2>
            <p className="text-gray-400 mb-6">
              訂單已收到，付款狀態更新可能需要幾分鐘，請稍後再查詢。
            </p>
          </>
        )}

        {/* 訂單資訊 */}
        {order && (
          <div className="bg-white/5 rounded-2xl p-6 text-left mb-6 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">訂單編號</span>
              <span className="text-brand-400 font-mono">{order.order_number}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">購買人</span>
              <span className="text-white">{order.customer_name}</span>
            </div>
            {order.items?.length > 0 && (
              <div className="pt-2 border-t border-white/10 space-y-1">
                {order.items.map((item) => (
                  <div key={item.id} className="flex justify-between text-sm">
                    <span className="text-gray-400">{item.product_name} × {item.quantity}</span>
                    <span className="text-white">NT${(Number(item.price) * item.quantity).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-between text-base font-semibold pt-2 border-t border-white/10">
              <span className="text-white">總金額</span>
              <span className="text-brand-400">NT${Number(order.total_price).toLocaleString()}</span>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-3">
          {isFailed && (
            <Link to={`/purchase`} className="btn-primary w-full block text-center">
              重新付款
            </Link>
          )}
          <Link to="/" className="btn-outline w-full block text-center">
            返回首頁
          </Link>
        </div>
      </div>
    </div>
  )
}
