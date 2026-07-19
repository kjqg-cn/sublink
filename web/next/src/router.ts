import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    meta: { title: '登录' },
    component: () => import('@/views/LoginView.vue')
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    redirect: '/subs',
    children: [
      {
        path: 'subs',
        name: 'subs',
        meta: { title: '订阅管理' },
        component: () => import('@/views/SubsView.vue')
      },
      {
        path: 'subs/create',
        name: 'create-sub',
        meta: { title: '创建订阅' },
        component: () => import('@/views/CreateSubView.vue')
      },
      {
        path: 'parse',
        name: 'parse',
        meta: { title: '订阅解析' },
        component: () => import('@/views/ParseView.vue')
      },
      {
        path: 'settings',
        name: 'settings',
        meta: { title: '全局设置' },
        component: () => import('@/views/SettingsView.vue')
      },
      {
        path: 'account',
        name: 'account',
        meta: { title: '账号设置' },
        component: () => import('@/views/AccountView.vue')
      },
      {
        path: 'logins',
        name: 'logins',
        meta: { title: '登录记录' },
        component: () => import('@/views/LoginsView.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  document.title = (to.meta.title as string) ?? 'Sublink'
  const token = localStorage.getItem('token')
  if (to.path !== '/login' && !token) {
    next('/login')
    return
  }
  next()
})

export default router
