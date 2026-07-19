<script setup lang="ts">
import { computed, h, ref, type VNodeChild } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import {
  NLayout,
  NLayoutHeader,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NButton,
  NIcon,
  NTag,
  type MenuOption
} from 'naive-ui'
import { currentUsername } from '@/api'
import { themeMode, toggleTheme } from '@/theme'

const router = useRouter()
const route = useRoute()
const username = ref(currentUsername())

function renderIcon(path: string): () => VNodeChild {
  return () =>
    h(
      NIcon,
      null,
      {
        default: () =>
          h('svg', { viewBox: '0 0 24 24', width: 18, height: 18 }, [
            h('path', { fill: 'currentColor', d: path })
          ])
      }
    )
}

const ICONS = {
  subs: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  create: 'M11 11V5h2v6h6v2h-6v6h-2v-6H5v-2h6z',
  parse: 'M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z',
  settings:
    'M19.14 12.94a7.5 7.5 0 000-1.88l2.03-1.58a.5.5 0 00.12-.64l-1.92-3.32a.5.5 0 00-.6-.22l-2.39.96a7 7 0 00-1.62-.94l-.36-2.54a.5.5 0 00-.5-.42h-3.84a.5.5 0 00-.5.42l-.36 2.54c-.58.24-1.12.56-1.62.94l-2.39-.96a.5.5 0 00-.6.22L2.68 8.84a.5.5 0 00.12.64l2.03 1.58a7.5 7.5 0 000 1.88l-2.03 1.58a.5.5 0 00-.12.64l1.92 3.32a.5.5 0 00.6.22l2.39-.96c.5.38 1.04.7 1.62.94l.36 2.54a.5.5 0 00.5.42h3.84a.5.5 0 00.5-.42l.36-2.54c.58-.24 1.12-.56 1.62-.94l2.39.96a.5.5 0 00.6-.22l1.92-3.32a.5.5 0 00-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1112 8.5a3.5 3.5 0 010 7z',
  account:
    'M12 12a5 5 0 100-10 5 5 0 000 10zm0 2c-4.42 0-8 2.24-8 5v1h16v-1c0-2.76-3.58-5-8-5z',
  logins:
    'M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V6a2 2 0 00-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z'
}

const menuOptions: MenuOption[] = [
  {
    label: () => h(RouterLink, { to: '/subs' }, { default: () => '订阅管理' }),
    key: '/subs',
    icon: renderIcon(ICONS.subs)
  },
  {
    label: () => h(RouterLink, { to: '/subs/create' }, { default: () => '创建订阅' }),
    key: '/subs/create',
    icon: renderIcon(ICONS.create)
  },
  {
    label: () => h(RouterLink, { to: '/parse' }, { default: () => '订阅解析' }),
    key: '/parse',
    icon: renderIcon(ICONS.parse)
  },
  {
    label: () => h(RouterLink, { to: '/settings' }, { default: () => '全局设置' }),
    key: '/settings',
    icon: renderIcon(ICONS.settings)
  },
  {
    label: () => h(RouterLink, { to: '/account' }, { default: () => '账号设置' }),
    key: '/account',
    icon: renderIcon(ICONS.account)
  },
  {
    label: () => h(RouterLink, { to: '/logins' }, { default: () => '登录记录' }),
    key: '/logins',
    icon: renderIcon(ICONS.logins)
  }
]

// /subs/create 高亮到创建订阅，其余按前缀匹配。
const activeKey = computed(() => {
  if (route.path.startsWith('/subs/create')) return '/subs/create'
  if (route.path.startsWith('/subs')) return '/subs'
  return route.path
})

const pageTitle = computed(() => (route.meta.title as string) ?? 'Sublink')

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh')
  router.push('/login')
}
</script>

<template>
  <n-layout class="shell" has-sider>
    <n-layout-sider bordered :width="230" content-style="display:flex;flex-direction:column;">
      <div class="side-head">
        <div class="brand-logo">S</div>
        <div>
          <div class="brand-title">Sublink</div>
          <div class="brand-sub">订阅管理后台</div>
        </div>
      </div>
      <n-menu :value="activeKey" :options="menuOptions" />
    </n-layout-sider>

    <n-layout>
      <n-layout-header bordered class="top-bar">
        <div class="top-title">{{ pageTitle }}</div>
        <div class="top-actions">
          <n-button quaternary circle @click="toggleTheme">
            <template #icon>
              <n-icon>
                <svg viewBox="0 0 24 24" width="18" height="18">
                  <path
                    v-if="themeMode === 'light'"
                    fill="currentColor"
                    d="M12 7a5 5 0 100 10 5 5 0 000-10zM11 2v2a1 1 0 002 0V2a1 1 0 00-2 0zm0 18v2a1 1 0 002 0v-2a1 1 0 00-2 0zM2 13h2a1 1 0 000-2H2a1 1 0 000 2zm18 0h2a1 1 0 000-2h-2a1 1 0 000 2zM5.64 4.22a1 1 0 00-1.42 1.42l1.06 1.06a1 1 0 001.42-1.42L5.64 4.22zm12.02 12.02a1 1 0 00-1.42 1.42l1.06 1.06a1 1 0 001.42-1.42l-1.06-1.06zm1.06-11.6l-1.06 1.06a1 1 0 001.42 1.42l1.06-1.06a1 1 0 00-1.42-1.42zM6.34 16.24l-1.06 1.06a1 1 0 001.42 1.42l1.06-1.06a1 1 0 00-1.42-1.42z"
                  />
                  <path
                    v-else
                    fill="currentColor"
                    d="M12 3a9 9 0 109 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 01-4.4 2.26 5.4 5.4 0 01-3.14-9.8c-.44-.06-.9-.1-1.36-.1z"
                  />
                </svg>
              </n-icon>
            </template>
          </n-button>
          <n-button size="small" quaternary tag="a" href="/">返回旧版</n-button>
          <n-tag :bordered="false" round type="info">{{ username || '未登录' }}</n-tag>
          <n-button size="small" secondary @click="logout">退出</n-button>
        </div>
      </n-layout-header>

      <n-layout-content class="main">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.shell {
  min-height: 100vh;
}

.side-head {
  align-items: center;
  display: flex;
  gap: 12px;
  padding: 18px 20px;
}

.brand-logo {
  align-items: center;
  background: linear-gradient(135deg, #6366f1, #22d3ee);
  border-radius: 12px;
  color: #fff;
  display: flex;
  font-size: 20px;
  font-weight: 700;
  height: 40px;
  justify-content: center;
  width: 40px;
}

.brand-title {
  font-size: 16px;
  font-weight: 700;
}

.brand-sub {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
}

.top-bar {
  align-items: center;
  display: flex;
  height: 60px;
  justify-content: space-between;
  padding: 0 22px;
}

.top-title {
  font-size: 16px;
  font-weight: 600;
}

.top-actions {
  align-items: center;
  display: flex;
  gap: 12px;
}

.main {
  padding: 24px;
}
</style>
