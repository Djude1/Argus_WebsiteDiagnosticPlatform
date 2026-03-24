/**
 * 後台管理 API — 所有需要 JWT 認證的請求
 */
import axios from 'axios'

const adminClient = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// 自動帶入 Authorization header
adminClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_access')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Token 過期時自動登出
adminClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('admin_access')
      localStorage.removeItem('admin_refresh')
      window.location.href = '/admin/login'
    }
    return Promise.reject(err)
  }
)

// ── 認證 ────────────────────────────────────────────────────────
export const login = (username, password) =>
  axios.post('/api/token/', { username, password })

export const getMe = () => adminClient.get('/accounts/me/')

// ── 帳號管理 ─────────────────────────────────────────────────────
export const getUsers    = ()        => adminClient.get('/admin/accounts/')
export const createUser  = (data)    => adminClient.post('/admin/accounts/', data)
export const updateUser  = (id, data)=> adminClient.patch(`/admin/accounts/${id}/`, data)
export const deleteUser  = (id)      => adminClient.delete(`/admin/accounts/${id}/`)

// ── 商品管理 ─────────────────────────────────────────────────────
export const getProducts    = ()        => adminClient.get('/admin/products/')
export const createProduct  = (data)    => adminClient.post('/admin/products/', data)
export const updateProduct  = (id, data)=> adminClient.patch(`/admin/products/${id}/`, data)
export const deleteProduct  = (id)      => adminClient.delete(`/admin/products/${id}/`)

export const uploadProductFile = (id, formData) =>
  adminClient.patch(`/admin/products/${id}/upload/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const getFeatures   = (pid)      => adminClient.get(`/admin/products/${pid}/features/`)
export const createFeature = (pid, data)=> adminClient.post(`/admin/products/${pid}/features/`, data)
export const updateFeature = (id, data) => adminClient.patch(`/admin/features/${id}/`, data)
export const deleteFeature = (id)       => adminClient.delete(`/admin/features/${id}/`)

export const getSpecs   = (pid)      => adminClient.get(`/admin/products/${pid}/specs/`)
export const createSpec = (pid, data)=> adminClient.post(`/admin/products/${pid}/specs/`, data)
export const updateSpec = (id, data) => adminClient.patch(`/admin/specs/${id}/`, data)
export const deleteSpec = (id)       => adminClient.delete(`/admin/specs/${id}/`)

// ── 訂單管理 ─────────────────────────────────────────────────────
export const getOrders      = (status) => adminClient.get('/admin/orders/', { params: status ? { status } : {} })
export const updateOrder    = (id, data)=> adminClient.patch(`/admin/orders/${id}/`, data)

// ── 成員管理 ─────────────────────────────────────────────────────
export const getTeamMembers  = ()        => adminClient.get('/admin/team/')
export const createTeamMember= (data)    => adminClient.post('/admin/team/', data)
export const updateTeamMember= (id, data)=> adminClient.patch(`/admin/team/${id}/`, data)
export const deleteTeamMember= (id)      => adminClient.delete(`/admin/team/${id}/`)

// ── 頁面內容管理 ─────────────────────────────────────────────────
export const getContentSection    = (section)      => adminClient.get(`/admin/content/${section}/`)
export const updateContentSection = (section, data)=> adminClient.patch(`/admin/content/${section}/`, data)

export const getDlFeatures   = ()        => adminClient.get('/admin/content-features/')
export const createDlFeature = (data)    => adminClient.post('/admin/content-features/', data)
export const updateDlFeature = (id, data)=> adminClient.patch(`/admin/content-features/${id}/`, data)
export const deleteDlFeature = (id)      => adminClient.delete(`/admin/content-features/${id}/`)

export const getDlSteps   = ()        => adminClient.get('/admin/content-steps/')
export const createDlStep = (data)    => adminClient.post('/admin/content-steps/', data)
export const updateDlStep = (id, data)=> adminClient.patch(`/admin/content-steps/${id}/`, data)
export const deleteDlStep = (id)      => adminClient.delete(`/admin/content-steps/${id}/`)

// ── 儀表板與日誌 ─────────────────────────────────────────────────
export const getTraffic      = ()       => adminClient.get('/admin/analytics/traffic/')
export const getActivityLogs = (action) => adminClient.get('/admin/analytics/logs/', {
  params: action ? { action } : {},
})

// ── FastAPI 裝置後台（/device-api proxy → FastAPI port 8081）────────────────

const deviceClient = axios.create({
  baseURL: '/device-api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})
deviceClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('device_access')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 認證
export const deviceLogin = (username, password) =>
  axios.post('/device-api/api/login', { username, password })

// APP 使用者管理（Admin）
export const deviceGetUsers   = ()         => deviceClient.get('/api/users')
export const deviceCreateUser = (data)     => deviceClient.post('/api/users', data)
export const deviceUpdateUser = (id, data) => deviceClient.put(`/api/users/${id}`, data)
export const deviceDeleteUser = (id)       => deviceClient.delete(`/api/users/${id}`)

// APP 裝置設定（Admin）
export const deviceGetSettings    = (uid)        => deviceClient.get(`/api/admin/users/${uid}/settings`)
export const deviceUpdateSettings = (uid, data)  => deviceClient.put(`/api/admin/users/${uid}/settings`, data)

// APP 撞擊記錄（Admin）
export const deviceGetImpacts = (userId) =>
  deviceClient.get('/api/impact_events', userId ? { params: { user_id: userId } } : {})

// APP 連絡人管理（Admin，可操作任意用戶）
export const deviceGetContacts   = (uid)        => deviceClient.get(`/api/admin/users/${uid}/contacts`)
export const deviceAddContact    = (uid, data)  => deviceClient.post(`/api/admin/users/${uid}/contacts`, data)
export const deviceUpdateContact = (cid, uid, data) =>
  deviceClient.put(`/api/admin/contacts/${cid}`, data, { params: { user_id: uid } })
export const deviceDeleteContact = (cid, uid)   =>
  deviceClient.delete(`/api/admin/contacts/${cid}`, { params: { user_id: uid } })


// APP 公告管理
export const getAnnouncements   = ()         => adminClient.get('/admin/announcements/')
export const createAnnouncement = (data)     => adminClient.post('/admin/announcements/', data)
export const updateAnnouncement = (id, data) => adminClient.patch(`/admin/announcements/${id}/`, data)
export const deleteAnnouncement = (id)       => adminClient.delete(`/admin/announcements/${id}/`)
