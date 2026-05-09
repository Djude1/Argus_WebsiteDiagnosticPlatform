/**
 * 骨架畫面元件 — 取代 Spinner，提供更友善的載入體驗
 */

// 通用骨架
export function Skeleton({ className = '' }) {
  return <div className={`animate-pulse bg-gray-200 dark:bg-gray-700 rounded ${className}`} />
}

// 產品卡片骨架（列表頁使用）
export function ProductCardSkeleton() {
  return (
    <div className="glass rounded-2xl p-6 space-y-4">
      <Skeleton className="h-48 w-full rounded-xl" />
      <Skeleton className="h-6 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-10 w-full rounded-full" />
    </div>
  )
}

// 團隊成員卡片骨架
export function MemberCardSkeleton() {
  return (
    <div className="glass rounded-2xl p-6 text-center space-y-3">
      <Skeleton className="w-20 h-20 rounded-2xl mx-auto" />
      <Skeleton className="h-5 w-24 mx-auto" />
      <Skeleton className="h-3 w-16 mx-auto" />
    </div>
  )
}

// 產品詳情頁骨架
export function ProductDetailSkeleton() {
  return (
    <div className="grid md:grid-cols-2 gap-8">
      <Skeleton className="aspect-square rounded-2xl" />
      <div className="space-y-4">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-6 w-1/4" />
        <Skeleton className="h-12 w-full rounded-xl" />
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-4/6" />
        </div>
      </div>
    </div>
  )
}

// 首頁特色亮點骨架
export function FeatureCardSkeleton() {
  return (
    <div className="glass rounded-2xl p-6 animate-pulse">
      <div className="w-10 h-10 bg-gray-200 dark:bg-gray-700 rounded-lg mb-4" />
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded mb-2 w-3/4" />
      <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
    </div>
  )
}
