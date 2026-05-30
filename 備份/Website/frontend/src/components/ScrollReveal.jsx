/**
 * ScrollReveal 元件 — 滾動進入視窗時觸發動畫
 * 使用 framer-motion 的 useInView + motion
 */
import { useRef } from 'react'
import { motion, useInView, useReducedMotion } from 'framer-motion'

export default function ScrollReveal({
  children,
  className = '',
  delay = 0,
  direction = 'up', // 'up' | 'down' | 'left' | 'right'
  duration = 0.5,
  once = true,
  amount = 0.2,
}) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once, amount })
  const shouldReduceMotion = useReducedMotion()

  const directionOffset = {
    up: { y: 40, x: 0 },
    down: { y: -40, x: 0 },
    left: { x: 40, y: 0 },
    right: { x: -40, y: 0 },
  }

  const offset = directionOffset[direction] || directionOffset.up

  return (
    <motion.div
      ref={ref}
      className={className}
      initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, ...offset }}
      animate={isInView ? (shouldReduceMotion ? { opacity: 1 } : { opacity: 1, x: 0, y: 0 }) : (shouldReduceMotion ? { opacity: 0 } : { opacity: 0, ...offset })}
      transition={{
        duration: shouldReduceMotion ? 0.1 : duration,
        delay: shouldReduceMotion ? 0 : delay,
        ease: [0.25, 0.4, 0.25, 1],
      }}
    >
      {children}
    </motion.div>
  )
}
