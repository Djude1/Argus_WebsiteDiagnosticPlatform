/**
 * Axios 實例設定：統一管理 API 請求
 */
import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 取得所有商品
export const fetchProducts = () => apiClient.get('/products/')

// 取得單一商品詳細（含 3D 模型路徑、功能、規格）
export const fetchProduct = (id) => apiClient.get(`/products/${id}/`)

// 建立訂單
export const createOrder = (orderData) => apiClient.post('/orders/', orderData)

// 查詢訂單詳情
export const getOrder = (orderId) => apiClient.get(`/orders/${orderId}/`)

// 取得所有團隊成員
export const fetchTeamMembers = (type) => {
  const params = type ? { type } : {}
  return apiClient.get('/team/', { params })
}

// 取得網站可編輯內容（按頁面分組）
export const fetchContent = () => apiClient.get('/content/')

export default apiClient
