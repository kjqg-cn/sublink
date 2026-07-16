const path = require('path')
const { defineConfig } = require('@vue/cli-service')
module.exports = defineConfig({
  transpileDependencies: true,
  outputDir: path.resolve(__dirname, '../app/static'),
  indexPath: path.resolve(__dirname, '../app/templates/index.html'),
  devServer: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        pathRewrite: {
          '^/api': '' // 重写路径
        }
      },
      '/sub': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true
      }
    }
  },
  publicPath: process.env.NODE_ENV === 'development' ? '/' : '../static/'
})
