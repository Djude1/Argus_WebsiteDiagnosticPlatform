# 日/夜模式切換功能 — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為網站新增日/夜模式切換按鈕，讓使用者能在暗色與亮色（暖色調）視覺風格之間切換。

**Architecture:** 使用 Tailwind `darkMode: 'class'` 策略。新增 ThemeContext 管理主題狀態，透過切換 `<html>` 的 `dark` class 控制。所有元件的 Tailwind class 改為「預設亮色 + `dark:` 暗色」雙向模式。亮色模式使用暖色品牌色（橘/金色系）。

**Tech Stack:** React 18、Tailwind CSS 3、Vite、localStorage、matchMedia API

**Spec:** `docs/superpowers/specs/2026-03-30-theme-toggle-design.md`

---

## 檔案結構

| 操作 | 檔案路徑 | 職責 |
|------|---------|------|
| 新增 | `frontend/src/context/ThemeContext.jsx` | 主題狀態管理（isDark、toggleTheme、localStorage、prefers-color-scheme） |
| 修改 | `frontend/src/main.jsx` | 在最外層包裹 ThemeProvider |
| 修改 | `frontend/tailwind.config.js` | 加入 `darkMode: 'class'` + 暖色 `warm` 色板 |
| 修改 | `frontend/src/index.css` | body/glass/btn-*/glow-border 加 dark: 變體 |
| 修改 | `frontend/src/App.jsx` | 外層 div 的 bg/text 改為響應式 |
| 修改 | `frontend/src/components/Navbar/Navbar.jsx` | 新增切換按鈕 + 色彩響應式 |
| 修改 | `frontend/src/components/Footer/Footer.jsx` | 色彩響應式 |
| 修改 | `frontend/src/components/FloatingCart/FloatingCart.jsx` | 色彩響應式 |
| 修改 | `frontend/src/pages/Home/Home.jsx` | Hero + 特色 + CTA 區塊色彩響應式 |
| 修改 | `frontend/src/pages/Product/Product.jsx` | 列表 + 詳情色彩響應式 |
| 修改 | `frontend/src/pages/Purchase/Purchase.jsx` | 表單色彩響應式 |
| 修改 | `frontend/src/pages/Purchase/PurchaseResult.jsx` | 結果頁色彩響應式 |
| 修改 | `frontend/src/pages/Team/Team.jsx` | 團隊卡片色彩響應式 |
| 修改 | `frontend/src/pages/Download/Download.jsx` | 下載頁色彩響應式 |
| 修改 | `frontend/src/pages/Project/Project.jsx` | 專案介紹色彩響應式 |
| 修改 | `frontend/src/pages/Announcements/Announcements.jsx` | 公告列表色彩響應式 |

---

## 色彩對應速查表

實作時所有檔案都遵循此對應規則：

| 原始暗色 class | 改為 |
|---|---|
| `bg-gray-950` | `bg-white dark:bg-gray-950` |
| `bg-gray-900/50` | `bg-gray-50 dark:bg-gray-900/50` |
| `bg-gray-900` | `bg-gray-50 dark:bg-gray-900` |
| `bg-gray-800` | `bg-gray-100 dark:bg-gray-800` |
| `bg-white/5` | `bg-gray-900/5 dark:bg-white/5` |
| `bg-white/10` | `bg-gray-800/10 dark:bg-white/10` |
| `bg-white/[0.02]` | `bg-gray-800/[0.02] dark:bg-white/[0.02]` |
| `text-white` | `text-gray-900 dark:text-white` |
| `text-gray-300` | `text-gray-700 dark:text-gray-300` |
| `text-gray-400` | `text-gray-600 dark:text-gray-400` |
| `text-gray-500` | `text-gray-500`（不變） |
| `text-gray-600` | `text-gray-400 dark:text-gray-600` |
| `border-white/10` | `border-gray-200 dark:border-white/10` |
| `border-white/5` | `border-gray-100 dark:border-white/5` |
| `shadow-black/20` | `shadow-gray-300/20 dark:shadow-black/20` |
| `hover:text-white` | `hover:text-gray-900 dark:hover:text-white` |
| `hover:bg-white/5` | `hover:bg-gray-100 dark:hover:bg-white/5` |

---

### Task 1: 建立 ThemeContext

**Files:**
- Create: `frontend/src/context/ThemeContext.jsx`

- [ ] **Step 1: 建立 ThemeContext.jsx**

```jsx
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
```

- [ ] **Step 2: 驗證檔案無語法錯誤**

確認 `ThemeContext.jsx` 已建立，exports `ThemeProvider` 和 `useTheme`。

---

### Task 2: 修改 tailwind.config.js

**Files:**
- Modify: `frontend/tailwind.config.js`

- [ ] **Step 1: 加入 darkMode 和 warm 色板**

將 `tailwind.config.js` 修改為：

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Noto Sans TC', 'sans-serif'],
      },
      colors: {
        // 品牌色系：深色科技風格（暗色模式使用）
        brand: {
          50:  '#edfcff',
          100: '#d6f7ff',
          200: '#b5f2ff',
          300: '#83ecff',
          400: '#48ddff',
          500: '#1ec4f7',
          600: '#07a3d7',
          700: '#0882ae',
          800: '#0f698f',
          900: '#135778',
          950: '#0a3750',
        },
        // 暖色品牌色系：亮色模式使用
        warm: {
          50:  '#fef9ee',
          100: '#fef0cd',
          200: '#fde6b6',
          300: '#fbd07b',
          400: '#fbab6a',
          500: '#f59e0b',
          600: '#f97d16',
          700: '#ef8108',
          800: '#d97704',
          900: '#c26604',
          950: '#92400b',
        },
      },
      animation: {
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-20px)' },
        },
        fadeInUp: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/tailwind.config.js
git commit -m "feat(theme): add darkMode class + warm color palette to tailwind config"
```

---

### Task 3: 修改 index.css

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: 更新 index.css 加入 dark: 變體**

將 `index.css` 完整替換為：

```css
@tailwind base;
@tailwind components;
@layer base {
  html {
    scroll-behavior: smooth;
  }

  body {
    font-family: 'Noto Sans TC', sans-serif;
    @apply bg-white text-gray-900 dark:bg-[#030712] dark:text-[#f9fafb];
  }
}

@layer components {
  /* 玻璃擬態效果 */
  .glass {
    @apply bg-gray-100/50 backdrop-blur-md border border-gray-200
           dark:bg-white/5 dark:border-white/10;
  }

  /* 發光邊框 */
  .glow-border {
    box-shadow: 0 0 20px rgba(30, 196, 247, 0.3);
    @apply border border-warm-500/50 dark:border-brand-500/50;
  }

  /* 主要按鈕 */
  .btn-primary {
    @apply bg-gradient-to-r from-warm-600 to-warm-500 hover:from-warm-500 hover:to-warm-400
           dark:from-brand-600 dark:to-brand-500 dark:hover:from-brand-500 dark:hover:to-brand-400
           text-white font-semibold py-3 px-8 rounded-full transition-all duration-300
           hover:shadow-lg hover:shadow-warm-500/30 dark:hover:shadow-brand-500/30
           active:scale-95;
  }

  /* 次要按鈕（外框式）*/
  .btn-outline {
    @apply border border-warm-500/70 text-warm-700 hover:bg-warm-500/10
           dark:border-brand-500/70 dark:text-brand-400 dark:hover:bg-brand-500/10
           font-semibold py-3 px-8 rounded-full transition-all duration-300
           hover:border-warm-400 dark:hover:border-brand-400 active:scale-95;
  }

  /* 段落標題 */
  .section-title {
    @apply text-3xl md:text-4xl font-bold text-center mb-4
           text-gray-900 dark:text-white;
  }

  /* 段落副標題 */
  .section-subtitle {
    @apply text-gray-600 dark:text-gray-400 text-center max-w-2xl mx-auto mb-12 text-lg;
  }
}

/* 自訂滾動條 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  @apply bg-gray-100 dark:bg-[#111827];
}

::-webkit-scrollbar-thumb {
  @apply bg-warm-500 dark:bg-brand-600;
  border-radius: 3px;
}

/* 3D Canvas 容器 */
.model-canvas-container {
  width: 100%;
  height: 100%;
  cursor: grab;
}

.model-canvas-container:active {
  cursor: grabbing;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(theme): add dark: variants to global CSS classes"
```

---

### Task 4: 包裹 ThemeProvider 到 main.jsx

**Files:**
- Modify: `frontend/src/main.jsx`
- Create: `frontend/src/context/ThemeContext.jsx`（已在 Task 1 完成）

- [ ] **Step 1: 讀取當前 main.jsx 並包裹 ThemeProvider**

在 `main.jsx` 中，將 `<React.StrictMode>` 內的 `<App />` 用 `<ThemeProvider>` 包裹。`ThemeProvider` 必須在最外層（在 `<BrowserRouter>` 之前或之於 App 內部都可以，但要在 DOM render 之前初始化，避免 FOUC）。

修改後的 `main.jsx`：

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { ThemeProvider } from './context/ThemeContext'

// 在 DOM 渲染前立即初始化主題 class，避免 FOUC
;(function initTheme() {
  const stored = localStorage.getItem('theme')
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const isDark = stored ? stored === 'dark' : prefersDark
  if (isDark) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
})()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/main.jsx frontend/src/context/ThemeContext.jsx
git commit -m "feat(theme): create ThemeContext and wrap App with ThemeProvider"
```

---

### Task 5: 修改 Navbar — 新增切換按鈕

**Files:**
- Modify: `frontend/src/components/Navbar/Navbar.jsx`

- [ ] **Step 1: 在 Navbar 中加入切換按鈕**

修改 `Navbar.jsx`：
1. 新增 `import { useTheme } from '../../context/ThemeContext'`
2. 在元件內呼叫 `const { isDark, toggleTheme } = useTheme()`
3. 在桌面版選單的「後台管理」按鈕左側新增切換按鈕
4. 在手機版漢堡按鈕左側新增切換按鈕
5. 將所有硬編碼暗色 class 改為響應式（遵循色彩對應表）

**桌面版切換按鈕位置**（在 `</div>` 關閉桌面選單之前，後台管理按鈕之前）：

```jsx
{/* 主題切換按鈕 */}
<button
  onClick={toggleTheme}
  className="p-2 rounded-lg text-gray-600 dark:text-gray-400 hover:text-warm-500 dark:hover:text-brand-400 hover:bg-gray-100 dark:hover:bg-white/5 transition-all"
  aria-label={isDark ? '切換到日間模式' : '切換到夜間模式'}
  title={isDark ? '日間模式' : '夜間模式'}
>
  {isDark ? (
    /* 太陽圖示 */
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  ) : (
    /* 月亮圖示 */
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
    </svg>
  )}
</button>
```

**手機版切換按鈕**（在漢堡按鈕左側）：
同樣的按鈕放在 `<button className="md:hidden ..."` 漢堡按鈕的同一個 flex 容器中，在漢堡按鈕之前。

**Navbar 色彩響應式修改**：
- `text-white group-hover:text-brand-400` → `text-gray-900 dark:text-white group-hover:text-warm-500 dark:group-hover:text-brand-400`
- `text-gray-300 hover:text-white hover:bg-white/5` → `text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5`
- `text-gray-400 hover:text-white hover:bg-white/5` → `text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5`
- `glass shadow-lg shadow-black/20` → `glass shadow-lg shadow-gray-300/20 dark:shadow-black/20`
- `text-brand-400 bg-brand-500/10` → `text-warm-600 dark:text-brand-400 bg-warm-500/10 dark:bg-brand-500/10`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Navbar/Navbar.jsx
git commit -m "feat(theme): add theme toggle button to Navbar"
```

---

### Task 6: 修改 App.jsx

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: 更新 App.jsx 外層 div 的色彩 class**

將 `bg-gray-950 text-white` 改為響應式：

```
bg-white text-gray-900 dark:bg-gray-950 dark:text-white
```

找到：`className="min-h-screen flex flex-col bg-gray-950 text-white"`
改為：`className="min-h-screen flex flex-col bg-white text-gray-900 dark:bg-gray-950 dark:text-white"`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(theme): make App root div theme-responsive"
```

---

### Task 7: 修改 Footer

**Files:**
- Modify: `frontend/src/components/Footer/Footer.jsx`

- [ ] **Step 1: 更新 Footer 色彩 class**

修改點：
- `border-t border-white/10` → `border-t border-gray-200 dark:border-white/10`
- `text-gray-400` → `text-gray-600 dark:text-gray-400`
- `text-white` → `text-gray-900 dark:text-white`
- `text-gray-500` → `text-gray-500`（不變）
- `hover:text-brand-400` → `hover:text-warm-500 dark:hover:text-brand-400`
- `hover:bg-brand-500/10` 保持不變（暗色和亮色都能用）

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Footer/Footer.jsx
git commit -m "feat(theme): make Footer theme-responsive"
```

---

### Task 8: 修改 FloatingCart

**Files:**
- Modify: `frontend/src/components/FloatingCart/FloatingCart.jsx`

- [ ] **Step 1: 更新 FloatingCart 色彩 class**

修改點：
- `bg-gray-900 border border-white/10` → `bg-white border border-gray-200 dark:bg-gray-900 dark:border-white/10`
- `border-b border-white/10 bg-white/5` → `border-b border-gray-200 bg-gray-50 dark:border-white/10 dark:bg-white/5`
- `text-white` → `text-gray-900 dark:text-white`
- `text-gray-400` → `text-gray-600 dark:text-gray-400`
- `text-gray-500` → `text-gray-500`（不變）
- `text-gray-600` → `text-gray-400 dark:text-gray-600`
- `border-white/10` → `border-gray-200 dark:border-white/10`
- `divide-white/5` → `divide-gray-100 dark:divide-white/5`
- `bg-white/5` → `bg-gray-50 dark:bg-white/5`
- `bg-white/[0.02]` → `bg-gray-50 dark:bg-white/[0.02]`
- `bg-gray-800 border border-white/10 hover:bg-gray-700 hover:border-brand-500/30` → `bg-gray-200 border border-gray-300 hover:bg-gray-300 hover:border-warm-500/30 dark:bg-gray-800 dark:border-white/10 dark:hover:bg-gray-700 dark:hover:border-brand-500/30`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/FloatingCart/FloatingCart.jsx
git commit -m "feat(theme): make FloatingCart theme-responsive"
```

---

### Task 9: 修改 Home 頁面

**Files:**
- Modify: `frontend/src/pages/Home/Home.jsx`

- [ ] **Step 1: 更新 Home.jsx 所有色彩 class**

修改點（逐一替換）：
- `bg-gray-900/50` → `bg-gray-50 dark:bg-gray-900/50`
- `text-white` → `text-gray-900 dark:text-white`
- `text-gray-400` → `text-gray-600 dark:text-gray-400`
- `text-gray-500` → `text-gray-500`（不變）
- `text-gray-600` → `text-gray-400 dark:text-gray-600`
- `border-white/5` → `border-gray-100 dark:border-white/5`
- `border-white/10` → `border-gray-200 dark:border-white/10`
- `bg-white/10` → `bg-gray-200/10 dark:bg-white/10`
- `bg-white/5` → `bg-gray-100/5 dark:bg-white/5`
- `text-brand-400` → `text-warm-600 dark:text-brand-400`（統計數字和品牌色）
- `text-brand-500` → `text-warm-500 dark:text-brand-500`
- `bg-brand-500` → `bg-warm-500 dark:bg-brand-500`
- `border-brand-500/40` → `border-warm-500/40 dark:border-brand-500/40`
- `shadow-brand-500/30` → `shadow-warm-500/30 dark:shadow-brand-500/30`
- `bg-brand-500/10` → `bg-warm-500/10 dark:bg-brand-500/10`
- `from-brand-400 to-brand-600` → `from-warm-400 to-warm-600 dark:from-brand-400 dark:to-brand-600`（漸層文字）
- `hover:text-brand-400` → `hover:text-warm-500 dark:hover:text-brand-400`
- `hover:glow-border` 保持不變（glow-border 已在 index.css 處理）

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Home/Home.jsx
git commit -m "feat(theme): make Home page theme-responsive"
```

---

### Task 10: 修改 Product 頁面

**Files:**
- Modify: `frontend/src/pages/Product/Product.jsx`

- [ ] **Step 1: 更新 Product.jsx 所有色彩 class**

修改點（遵循色彩對應表 + 品牌色替換）：
- 與 Task 9 相同的通用替換規則
- `text-brand-400` → `text-warm-600 dark:text-brand-400`
- `text-brand-500` → `text-warm-500 dark:text-brand-500`
- `bg-brand-500/10` → `bg-warm-500/10 dark:bg-brand-500/10`
- `hover:text-brand-400` → `hover:text-warm-500 dark:hover:text-brand-400`
- `border-white/20 bg-white/5` → `border-gray-300 bg-gray-100 dark:border-white/20 dark:bg-white/5`
- `hover:border-brand-500/50 hover:bg-brand-500/10` → `hover:border-warm-500/50 hover:bg-warm-500/10 dark:hover:border-brand-500/50 dark:hover:bg-brand-500/10`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Product/Product.jsx
git commit -m "feat(theme): make Product page theme-responsive"
```

---

### Task 11: 修改 Purchase 頁面

**Files:**
- Modify: `frontend/src/pages/Purchase/Purchase.jsx`

- [ ] **Step 1: 更新 Purchase.jsx 所有色彩 class**

修改點：
- 與通用替換規則相同
- `bg-white/5 border border-white/10` (input) → `bg-gray-50 border border-gray-300 dark:bg-white/5 dark:border-white/10`
- `placeholder-gray-600` → `placeholder-gray-400 dark:placeholder-gray-600`
- `focus:border-brand-500` → `focus:border-warm-500 dark:focus:border-brand-500`
- `text-gray-300` → `text-gray-700 dark:text-gray-300`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Purchase/Purchase.jsx
git commit -m "feat(theme): make Purchase page theme-responsive"
```

---

### Task 12: 修改 PurchaseResult 頁面

**Files:**
- Modify: `frontend/src/pages/Purchase/PurchaseResult.jsx`

- [ ] **Step 1: 更新 PurchaseResult.jsx 所有色彩 class**

修改點：
- `text-gray-400` → `text-gray-600 dark:text-gray-400`
- `text-gray-500` → `text-gray-500`（不變）
- `text-white` → `text-gray-900 dark:text-white`
- `bg-white/5` → `bg-gray-50 dark:bg-white/5`
- `border-white/10` → `border-gray-200 dark:border-white/10`
- `text-brand-400` → `text-warm-600 dark:text-brand-400`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Purchase/PurchaseResult.jsx
git commit -m "feat(theme): make PurchaseResult page theme-responsive"
```

---

### Task 13: 修改 Team 頁面

**Files:**
- Modify: `frontend/src/pages/Team/Team.jsx`

- [ ] **Step 1: 更新 Team.jsx 所有色彩 class**

修改點：
- 通用替換規則
- `from-brand-700 to-brand-900` → `from-warm-600 to-warm-800 dark:from-brand-700 dark:to-brand-900`（頭像背景）
- `text-brand-300` → `text-warm-200 dark:text-brand-300`
- `text-gray-500 hover:text-white` → `text-gray-400 hover:text-gray-900 dark:text-gray-500 dark:hover:text-white`
- `via-white/20` → `via-gray-300 dark:via-white/20`（分隔線）

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Team/Team.jsx
git commit -m "feat(theme): make Team page theme-responsive"
```

---

### Task 14: 修改 Download 頁面

**Files:**
- Modify: `frontend/src/pages/Download/Download.jsx`

- [ ] **Step 1: 更新 Download.jsx 所有色彩 class**

修改點：
- 通用替換規則
- `bg-gray-900/50` → `bg-gray-50 dark:bg-gray-900/50`
- `shadow-lg shadow-brand-500/30` → `shadow-lg shadow-warm-500/30 dark:shadow-brand-500/30`
- `from-brand-500 to-brand-700` → `from-warm-500 to-warm-700 dark:from-brand-500 dark:to-brand-700`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Download/Download.jsx
git commit -m "feat(theme): make Download page theme-responsive"
```

---

### Task 15: 修改 Project 頁面

**Files:**
- Modify: `frontend/src/pages/Project/Project.jsx`

- [ ] **Step 1: 更新 Project.jsx 所有色彩 class**

修改點：
- 通用替換規則
- `from-brand-400 to-brand-600` → `from-warm-400 to-warm-600 dark:from-brand-400 dark:to-brand-600`（漸層文字）
- `from-amber-500/20 to-amber-600/5` → 保持不變（這是功能卡片的強調色，兩種模式都合適）
- `border-amber-500/20` → 保持不變
- `from-brand-500/20 to-brand-600/5` → `from-warm-500/20 to-warm-600/5 dark:from-brand-500/20 dark:to-brand-600/5`
- `border-brand-500/20` → `border-warm-500/20 dark:border-brand-500/20`
- `bg-white/5 border border-white/10` (tag) → `bg-gray-100 border border-gray-200 dark:bg-white/5 dark:border-white/10`
- `text-gray-300` → `text-gray-700 dark:text-gray-300`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Project/Project.jsx
git commit -m "feat(theme): make Project page theme-responsive"
```

---

### Task 16: 修改 Announcements 頁面

**Files:**
- Modify: `frontend/src/pages/Announcements/Announcements.jsx`

- [ ] **Step 1: 更新 Announcements.jsx 所有色彩 class**

修改點：
- `from-gray-950 via-gray-900 to-gray-950` → `from-white via-gray-50 to-white dark:from-gray-950 dark:via-gray-900 dark:to-gray-950`
- `bg-gray-900/50 backdrop-blur-sm border border-gray-800` → `bg-gray-50 backdrop-blur-sm border border-gray-200 dark:bg-gray-900/50 dark:border-gray-800`
- `hover:border-gray-700` → `hover:border-gray-300 dark:hover:border-gray-700`
- `border-gray-800` → `border-gray-200 dark:border-gray-800`
- `text-gray-300` → `text-gray-700 dark:text-gray-300`
- `bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white` → `bg-gray-200 text-gray-600 hover:bg-gray-300 hover:text-gray-900 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-white`
- `text-gray-700` → `text-gray-400 dark:text-gray-700`
- 通用替換規則適用於其餘 class

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Announcements/Announcements.jsx
git commit -m "feat(theme): make Announcements page theme-responsive"
```

---

### Task 17: 更新 idea.md

**Files:**
- Modify: `idea.md`（專案根目錄）

- [ ] **Step 1: 在 idea.md 中記錄主題切換功能的重點**

新增以下內容到 idea.md：

```markdown
## 日/夜模式切換功能（2026-03-30）

### 重點決策
- 使用 Tailwind `darkMode: 'class'` 策略
- 預設跟隨系統 `prefers-color-scheme`
- 使用者手動切換後存入 localStorage，不再跟隨系統
- 亮色模式使用暖色品牌色（橘/金色 warm 色板），暗色模式維持原有品牌藍
- 切換按鈕在 Navbar 右側（太陽/月亮圖示）
- FOUC 防護：main.jsx 渲染前立即初始化 `<html>` class

### 涉及檔案
- ThemeContext.jsx（新增）
- main.jsx、App.jsx、tailwind.config.js、index.css（基礎建設）
- Navbar、Footer、FloatingCart（元件）
- Home、Product、Purchase、PurchaseResult、Team、Download、Project、Announcements（頁面）
```

- [ ] **Step 2: Commit**

```bash
git add idea.md
git commit -m "docs: record theme toggle feature decisions in idea.md"
```

---

## 自我審查

### 覆蓋率檢查

| Spec 需求 | 對應 Task |
|-----------|----------|
| ThemeContext 管理 dark/light 狀態 | Task 1 |
| localStorage 持久化 | Task 1 |
| prefers-color-scheme 偵測 | Task 1 |
| FOUC 防護 | Task 4 |
| Navbar 切換按鈕（太陽/月亮） | Task 5 |
| darkMode: 'class' | Task 2 |
| warm 暖色色板 | Task 2 |
| glass/btn-*/glow-border dark: 變體 | Task 3 |
| App.jsx 外層響應式 | Task 6 |
| Footer 色彩 | Task 7 |
| FloatingCart 色彩 | Task 8 |
| Home 色彩 | Task 9 |
| Product 色彩 | Task 10 |
| Purchase 色彩 | Task 11 |
| PurchaseResult 色彩 | Task 12 |
| Team 色彩 | Task 13 |
| Download 色彩 | Task 14 |
| Project 色彩 | Task 15 |
| Announcements 色彩 | Task 16 |
| idea.md 記錄 | Task 17 |

無遺漏。

### Placeholder 掃描
無 TBD、TODO、或空白步驟。

### 一致性檢查
- `useTheme()` 在 Task 1 定義，Task 5 使用 — 一致
- `warm` 色板在 Task 2 定義，Tasks 9-16 使用 — 一致
- `glass`、`btn-*`、`glow-border` 在 Task 3 定義 — 一致
- `darkMode: 'class'` 在 Task 2 設定，所有 `dark:` class 依賴此設定 — 一致
