
// import { defineConfig } from 'vite'
// import react from '@vitejs/plugin-react'

// export default defineConfig({
//   plugins: [react()],
//   server: {
//     host: '0.0.0.0',
//     port: 3000,
//     proxy: {
//       // 開發模式下將 API 請求代理至 Django 後端
//       '/api': {
//         target: 'http://backend:8000',
//         changeOrigin: true,
//       },
//       '/media': {
//         target: 'http://backend:8000',
//         changeOrigin: true,
//       },
//     },
//   },
// })




import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  // ── 預先打包重量級依賴，避免首次載入時大量零散請求 ──────────────
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react-router-dom',
      'framer-motion',
      '@react-three/fiber',
      '@react-three/drei',
      'three',
    ],
  },

  // ── 建置時分割 vendor chunk，減少單一 bundle 大小 ────────────────
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-three': ['three', '@react-three/fiber', '@react-three/drei'],
          'vendor-motion': ['framer-motion'],
        },
      },
    },
  },

  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: true,
    // HMR 輪詢（Docker on Windows 的 inotify 不可靠，改用輪詢避免 HMR 失效）
    watch: {
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      // 開發模式下將 API 請求代理至 Django 後端
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      // FastAPI 裝置後台（port 8081，host.docker.internal 指向宿主機）
      '/device-api': {
        target: 'http://host.docker.internal:8081',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/device-api/, ''),
      },
    },
  },
})