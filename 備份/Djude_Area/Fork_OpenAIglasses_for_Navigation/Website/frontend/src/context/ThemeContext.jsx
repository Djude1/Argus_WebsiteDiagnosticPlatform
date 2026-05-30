import { createContext, useContext, useState, useEffect } from 'react'

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(() => {
    // 優先讀取 localStorage
    const stored = localStorage.getItem('theme')
    if (stored === 'dark' || stored === 'light') {
      return stored === 'dark'
    }
    // 否則跟隨系統偏好
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  // 同步 <html> class 和 localStorage
  useEffect(() => {
    const root = document.documentElement
    if (isDark) {
      root.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      root.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [isDark])

  // 監聽系統偏好變化（僅在無 localStorage 值時跟隨）
  useEffect(() => {
    const stored = localStorage.getItem('theme')
    if (stored) return // 使用者已手動選過，不跟隨系統
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => setIsDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const toggleTheme = () => setIsDark(prev => !prev)

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
