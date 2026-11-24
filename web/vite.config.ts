import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端构建产物不提交至 Git，由 Docker 多阶段构建或部署端本地编译生成：
// - 产物（含 index.html）输出至 app/static/dist/，静态资源以 /static/dist/ 为前缀
// - 使用独立子目录以便 emptyOutDir 安全清理旧产物，同时保留版本库中的 app/static/favicon.ico
// - Flask 根路径 / 直接返回 app/static/dist/index.html，/next 自动重定向至 /
export default defineConfig({
  base: '/static/dist/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    outDir: fileURLToPath(new URL('../app/static/dist', import.meta.url)),
    emptyOutDir: true
  },
  server: {
    host: '0.0.0.0',
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
