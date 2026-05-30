/**
 * 全域購物車狀態管理
 * 提供：items（購物車內容）、addItem、setQty、removeItem、clearCart
 */
import { createContext, useContext, useState, useCallback, useEffect } from 'react'

const CartContext = createContext({})

export function CartProvider({ children }) {
  // items 結構：{ [productId]: { product: {...}, qty: number } }
  // 初始化時從 localStorage 讀取已儲存的購物車資料
  const [items, setItems] = useState(() => {
    try {
      const saved = localStorage.getItem('aiglass_cart')
      return saved ? JSON.parse(saved) : {}
    } catch {
      return {}
    }
  })

  // 每次購物車變更時同步到 localStorage
  useEffect(() => {
    try {
      localStorage.setItem('aiglass_cart', JSON.stringify(items))
    } catch {}
  }, [items])

  /** 加入商品（已存在則累加數量）*/
  const addItem = useCallback((product, qty = 1) => {
    setItems(prev => {
      const existing = prev[product.id]
      return {
        ...prev,
        [product.id]: {
          product,
          qty: Math.min((existing?.qty ?? 0) + qty, 99),
        },
      }
    })
  }, [])

  /** 直接設定某商品數量（qty <= 0 時自動移除）
   *  注意：商品必須已透過 addItem 加入購物車，否則 setQty 會忽略（沒有 product 資料無法計價）
   */
  const setQty = useCallback((productId, qty) => {
    if (qty <= 0) {
      setItems(prev => {
        const next = { ...prev }
        delete next[productId]
        return next
      })
    } else {
      setItems(prev => {
        const existing = prev[productId]
        // 商品不在購物車中 → 忽略，需先透過 addItem 加入
        if (!existing) return prev
        return {
          ...prev,
          [productId]: { ...existing, qty: Math.min(qty, 99) },
        }
      })
    }
  }, [])

  /** 移除商品 */
  const removeItem = useCallback((productId) => {
    setItems(prev => {
      const next = { ...prev }
      delete next[productId]
      return next
    })
  }, [])

  /** 清空購物車 */
  const clearCart = useCallback(() => setItems({}), [])

  /** 購物車商品總件數（防禦性檢查） */
  const totalItems = Object.values(items).reduce(
    (sum, entry) => sum + (entry?.qty || 0), 0
  )

  /** 購物車總金額（防禦性檢查） */
  const totalPrice = Object.values(items).reduce(
    (sum, entry) => sum + ((Number(entry?.product?.price) || 0) * (entry?.qty || 0)),
    0
  )

  return (
    <CartContext.Provider value={{
      items, addItem, setQty, removeItem, clearCart,
      totalItems, totalPrice,
    }}>
      {children}
    </CartContext.Provider>
  )
}

export const useCart = () => useContext(CartContext)
