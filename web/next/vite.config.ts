import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 新版 UI 与老版隔离共存：
// - 产物（含 index.html）全部输出到 app/static/next/，资源以 /static/next/ 为前缀
// - Flask 通过 /next 路由返回 app/static/next/index.html，老版仍占用 /
// - baseURL 生产环境为 ''（见 request.ts），接口打到同源根路径，不受此前缀影响
export default defineConfig({
  base: '/static/next/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    // 独立子目录，emptyOutDir 可安全清理旧的新版产物，且不影响老版 app/static/{js,css}
    outDir: fileURLToPath(new URL('../../app/static/next', import.meta.url)),
    emptyOutDir: true
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      },
      '/sub': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true
      }
    }
  }
})
