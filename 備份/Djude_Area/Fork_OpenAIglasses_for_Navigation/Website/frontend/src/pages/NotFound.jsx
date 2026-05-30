/**
 * 404 找不到頁面
 */
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4 dark:bg-gray-950">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.4, 0.25, 1] }}
        className="text-center max-w-md"
      >
        {/* 404 數字 */}
        <div className="text-8xl md:text-9xl font-black text-transparent bg-clip-text bg-gradient-to-r from-warm-400 to-warm-600 dark:from-brand-400 dark:to-brand-600 mb-6">
          404
        </div>

        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-4">
          找不到頁面
        </h1>
        <p className="text-gray-700 dark:text-gray-400 mb-8 leading-relaxed">
          您造訪的頁面可能已被移除、名稱變更，或暫時無法使用。
        </p>

        <div className="flex flex-wrap gap-4 justify-center">
          <Link to="/" className="btn-primary">
            返回首頁
          </Link>
          <Link to="/product" className="btn-outline">
            瀏覽產品
          </Link>
        </div>

        {/* 裝飾性圖案 */}
        <div className="mt-12 text-6xl opacity-20">
          🥽
        </div>
      </motion.div>
    </div>
  )
}
