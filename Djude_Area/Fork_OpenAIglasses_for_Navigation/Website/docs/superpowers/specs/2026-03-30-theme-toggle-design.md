# 設計文件：日/夜間暗色模式切換功能

**日期**： 2026-03-30
**狀態**： Draft
**作者**： AI 導航智慧眼鏡團隊

## 馂述

為網站新增日/夜模式切換按鈕，讓使用者能在兩種視覺風格之間切換。

### 部件

- **切換按鈕**： 導航欄右上角，太陽/月亮圖示）
- **預設模式**： 萷後系統 `prefers-color-scheme` 媒體好
  - **持久化**=`localStorage`
- **切換策略** = Tailwind `dark:` class（方案 A）
- **亮色色彩** = 暖色調品牌色系

## 部件

### ThemeContext

新增 `frontend/src/context/ThemeContext.jsx`：

**職責**：
- 管理 `dark/light` 瀏覽狀態
- 颐設值：偵測 `prefers-color-scheme` → 如果未偵測到，查 localStorage
- 若 localStorage 有值則使用該值， 否則使用系統偵測到的暗色
- 透過切換 `<html>` 的 class 來控制 Tailwind `dark:` 模式
- 提供 `useTheme()` hook 綈費當前主題和 `isDark` 瀏覽

**API**：
```jsx
export const useTheme = useTheme
```

```jsx
function ThemeProvider({ children }) {
  // 1. 偵測系統偏好（prefers-color-scheme）
  const [isDark, setIsDark] = useState(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    return mq.matches
  })

  // 2. 讀取 localStorage
  useEffect(() => {
    const stored = localStorage.getItem('theme')
    if (stored === 'dark' || stored === 'light') {
      setIsDark(stored === 'dark')
    }
  }, [])

  // 3. 監聽系統偏好變化
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => setIsDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [isDark])

  })

  // 4. 切換時更新 HTML class 和 localStorage
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

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
```

````

### Navbar 切換按鈕

在 `Navbar.jsx` 中「後台管理」按鈕左側新增一個切換按鈕：

使用 `useTheme()` hook 讀取當前狀態，顯示太陽/月亮 SVG 圖示。

點擊時呼叫 `toggleTheme()`。

**桌面版**： 後台管理按鈕左側，**手機版**； 漢堡選單按鈕右側（漢堡選單上方獨立顯示。

### Tailwind 設定

在 `tailwind.config.js` 加入 `darkMode: 'class'`。

新增暖色品牌色 `palette：
（`warm` brand color overrides for `warm` key in `theme.extend.colors`）

### index.css 修改

`glass`、`btn-*`、`glow-border` 等 component class 加上 `dark:` 變體。
`body` 預設背景改為響應式。

### 所有頁面和元件

將現有硬編碼暗色 class 改為「預設亮色 + `dark: 暗色」雙向 class。

**受影響檔案清單**：

| 檔案 | 關鍵修改 |
|---|---|
| `Navbar/Navbar.jsx` | 切換按鈕 |
| `Footer/Footer.jsx` | 色彩 |
| `FloatingCart/FloatingCart.jsx` | 色彩 + 背景 |
| `pages/Home/Home.jsx` | Hero + 特色 + CTA 區塊 |
| `pages/Product/Product.jsx` | 列表+詳情 |
| `pages/Purchase/Purchase.jsx` | 表單 |
| `pages/Purchase/PurchaseResult.jsx` | 結果頁 |
| `pages/Team/Team.jsx` | 團隊成員卡片 |
| `pages/Download/Download.jsx` | 下載頁 + CTA |
| `pages/Project/Project.jsx` | 專案介紹 |
| `pages/Announcements/Announcements.jsx` | 公告列表 |
| `App.jsx` | 佈局包裹 ThemeProvider |
| `index.css` | CSS 變數 |
| `tailwind.config.js` | Tailwind 設定 |
| `main.jsx` | ThemeContext 初始化 |

## 色彩對應表

| 皗色硬編碼 | 亮色對應 |
|---|---|
| `bg-gray-950` | `bg-white dark:bg-gray-950` |
| `bg-gray-900/50` | `bg-gray-50 dark:bg-gray-900/50` |
| `bg-gray-900` | `bg-gray-50 dark:bg-gray-900` |
| `bg-gray-800` | `bg-gray-100 dark:bg-gray-800` |
| `bg-white/5` | `bg-gray-100/5 dark:bg-white/5` |
| `bg-white/10` | `bg-gray-200/10 dark:bg-white/10` |
| `text-white` | `text-gray-900 dark:text-white` |
| `text-gray-300` | `text-gray-700 dark:text-gray-300` |
| `text-gray-400` | `text-gray-600 dark:text-gray-400` |
| `text-gray-500` | `text-gray-500`（不變） |
| `text-gray-600` | `text-gray-400 dark:text-gray-600` |
| `border-white/10` | `border-gray-200 dark:border-white/10` |
| `border-white/5` | `border-gray-100 dark:border-white/5` |
| `shadow-black/20` | `shadow-gray-300/20 dark:shadow-black/20` |

## 亮色模式暖色品牌色

在 `tailwind.config.js` 的 `theme.extend.colors` 中新增 `warm` 色板：

```javascript
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
}
```

## 蚪蟲風險

- 開關元件檔案較多（~15 個 JSX），每個逐一修改），整體工作量可控
- 爭 Tailwind 官方 `dark:` class 策略，生態系支援最好
- 亮色模式使用暖色調（橘/金），與品牌藍色形成視覺對比

## 邊界條件

- 使用 `class` 策略，CSS 層面切換，無運行時開銷
- 記憶: 涉及 2 個 JSX 檔案
