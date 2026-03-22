
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
  server: {
    host: '0.0.0.0',
    port: 3000,
    
    // ▼▼▼ 加在這裡！告訴 Vite 不要擋 Cloudflare 的網址 ▼▼▼
    allowedHosts: true, 
    // ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
    
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