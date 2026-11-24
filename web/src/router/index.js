import Vue from 'vue'
import VueRouter from 'vue-router'
import { readStoredToken } from '@/utils/request'

Vue.use(VueRouter)

const routes = [
  {
    path: '/login',
    name: 'login',
    meta: {
      title: '登录页'
    },
    component: () => import('@/views/login')
  },
  {
    path: '/',
    name: 'index',
    meta: {
      title: '订阅管理系统'
    },
    component: () => import('@/views/index')
  }
]

const router = new VueRouter({
  mode: 'hash',
  base: process.env.BASE_URL,
  routes
})
router.beforeEach((to, from, next) => {
  document.title = (to.meta && to.meta.title) || '订阅管理系统'
  const token = readStoredToken('token')
  if (to.path !== '/login' && !token) { // 判断是否登录
    return next('/login') // 如果没登录直接跳回登录页
  }
  next()
})

export default router
