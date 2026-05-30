import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'

/** 換頁時自動捲回最頂端，並顯示回到頂部按鈕 */
export default function ScrollToTop() {
  const { pathname } = useLocation()
  const [showButton, setShowButton] = useState(false)

  // 換頁時捲回頂端
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  // 監聽滾動位置，超過 400px 顯示按鈕
  useEffect(() => {
    const handleScroll = () => setShowButton(window.scrollY > 400)
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <AnimatePresence>
      {showButton && (
        <motion.button
          key="scroll-to-top"
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.8 }}
          transition={{ duration: 0.2 }}
          onClick={scrollToTop}
          className="fixed bottom-24 right-6 z-40 w-10 h-10 rounded-full bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm border border-gray-200 dark:border-white/10 shadow-lg flex items-center justify-center text-gray-700 dark:text-gray-400 hover:text-warm-600 dark:hover:text-brand-400 hover:border-warm-600/30 dark:hover:border-brand-500/30 transition-colors"
          aria-label="回到頂部"
          title="回到頂部"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
          </svg>
        </motion.button>
      )}
    </AnimatePresence>
  )
}
