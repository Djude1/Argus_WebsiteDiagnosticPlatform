import { createContext, useContext, useState, useEffect } from 'react'
import { fetchContent } from '../api/client'

// Fallback 資料：當後端未部署時使用
const fallbackContent = {
  site: {
    title: 'AI 智慧眼鏡',
    description: '專為視障人士設計的 AI 輔助系統',
  },
  home: {
    hero_title: 'AI 智慧盲人導航眼鏡',
    hero_subtitle: '結合 YOLO 影像辨識與語音助理，提供即時盲道導航、斑馬線輔助、障礙物偵測與物品尋找功能',
    cta_text: '了解更多',
  },
}

const fallbackProducts = [
  {
    id: 1,
    name: 'AI 智慧眼鏡 標準版',
    price: 12900,
    original_price: 15900,
    description: '專為視障人士設計的 AI 輔助系統，包含盲道導航、斑馬線輔助、障礙物偵測、物品尋找等功能。',
    image: '/media/models/aiglass.png',
    model_3d: 'aiglass.glb',
    features: [
      { icon: '🛤️', title: '盲道導航', description: '即時識別盲道並語音引導方向' },
      { icon: '🚦', title: '斑馬線輔助', description: '紅綠燈狀態識別與安全過馬路指引' },
      { icon: '🚧', title: '障礙物偵測', description: '即時偵測前方障礙物並發出警告' },
      { icon: '🔍', title: '物品尋找', description: '語音指令尋找特定物品' },
    ],
    specs: [
      { label: '鏡框重量', value: '約 45g' },
      { label: '電池續航', value: '約 8 小時' },
      { label: '充電方式', value: 'USB-C 快充' },
      { label: '支援系統', value: 'iOS / Android' },
    ],
  },
]

const ContentContext = createContext({})

export function ContentProvider({ children }) {
  const [content, setContent] = useState(fallbackContent)
  const [products, setProducts] = useState(fallbackProducts)

  useEffect(() => {
    fetchContent()
      .then((res) => setContent({ ...fallbackContent, ...res.data }))
      .catch(() => {
        // 使用 fallback，不做任何事
      })

    // 同時嘗試獲取產品列表
    fetch('/api/products/')
      .then(res => res.ok ? res.json() : Promise.reject())
      .then(data => {
        const list = data.results || data
        if (list.length > 0) setProducts(list)
      })
      .catch(() => {
        // 使用 fallbackProducts
      })
  }, [])

  const contextValue = { ...content, products }

  return (
    <ContentContext.Provider value={contextValue}>
      {children}
    </ContentContext.Provider>
  )
}

export const useContent = () => useContext(ContentContext)

// 匯出 products 供其他元件使用
export const useProducts = () => {
  const context = useContext(ContentContext)
  return context.products || fallbackProducts
}