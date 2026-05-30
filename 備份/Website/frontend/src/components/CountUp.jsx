/**
 * CountUp 元件 — 數字滾動計數動畫
 * 當元素進入視窗時，從 0 開始計數到目標值
 */
import { useEffect, useRef, useState } from 'react'
import { useInView } from 'framer-motion'

/**
 * 判斷值是否為可計數的數字
 */
function isNumeric(val) {
  return typeof val === 'number' || (typeof val === 'string' && !isNaN(Number(val)) && val.trim() !== '')
}

export default function CountUp({ end, duration = 2, suffix = '', className = '' }) {
  // 若 end 不是數字，直接顯示原始值，避免從 0 閃爍
  const [count, setCount] = useState(() => isNumeric(end) ? 0 : end)
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, amount: 0.5 })

  useEffect(() => {
    if (!isInView) return

    const target = Number(end)
    if (isNaN(target)) {
      setCount(end)
      return
    }

    let startTime = null
    const step = (timestamp) => {
      if (!startTime) startTime = timestamp
      const progress = Math.min((timestamp - startTime) / (duration * 1000), 1)
      // 使用 easeOutExpo 曲線讓動畫更有彈性
      const eased = 1 - Math.pow(1 - progress, 4)
      setCount(Math.floor(eased * target))
      if (progress < 1) {
        requestAnimationFrame(step)
      } else {
        setCount(end)
      }
    }
    requestAnimationFrame(step)
  }, [isInView, end, duration])

  return (
    <span ref={ref} className={className}>
      {count}{suffix}
    </span>
  )
}
