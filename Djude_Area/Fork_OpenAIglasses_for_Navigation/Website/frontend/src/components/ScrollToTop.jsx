import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/** 換頁時自動捲回最頂端 */
export default function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}
