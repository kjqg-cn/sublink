<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch, type VNodeChild } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import {
  useDialog,
  NLayout,
  NLayoutHeader,
  NLayoutSider,
  NLayoutContent,
  NDrawer,
  NDrawerContent,
  NMenu,
  NButton,
  NIcon,
  NTag,
  type MenuOption
} from 'naive-ui'
import { currentUsername } from '@/api'
import { themeMode, toggleTheme } from '@/theme'
import { clearSessionState, storageRemove } from '@/utils/storage'

const router = useRouter()
const route = useRoute()
const dialog = useDialog()
const username = ref(currentUsername())

const MOBILE_BREAKPOINT = 768
const isMobile = ref(typeof window !== 'undefined' ? window.innerWidth < MOBILE_BREAKPOINT : false)
const collapsed = ref(false)
const drawerOpen = ref(false)

function syncUsername() {
  username.value = currentUsername()
}

function handleResize() {
  isMobile.value = window.innerWidth < MOBILE_BREAKPOINT
  if (!isMobile.value) {
    drawerOpen.value = false
  }
}

watch(
  () => route.fullPath,
  () => {
    syncUsername()
    drawerOpen.value = false
  }
)

onMounted(() => {
  window.addEventListener('storage', syncUsername)
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('storage', syncUsername)
  window.removeEventListener('resize', handleResize)
})

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

function confirmLogout() {
  dialog.warning({
    title: '退出登录',
    content: '确定要退出当前登录会话吗？',
    positiveText: '退出登录',
    negativeText: '取消',
    onPositiveClick: () => {
      storageRemove('local', 'token')
      storageRemove('local', 'refresh')
      clearSessionState()
      router.push('/login')
    }
  })
}
</script>

<template>
  <n-layout class="shell" :class="themeMode" has-sider position="absolute">
    <n-layout-sider
      v-if="!isMobile"
      bordered
      collapsible
      collapse-mode="width"
      :collapsed="collapsed"
      :collapsed-width="64"
      :width="220"
      show-trigger="arrow-circle"
      content-style="display:flex;flex-direction:column;height:100%;"
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="side-head" :class="{ compact: collapsed }">
        <div class="brand-logo">S</div>
        <div class="brand-copy">
          <div class="brand-title">Sublink</div>
          <div class="brand-sub">订阅管理后台</div>
        </div>
      </div>
      <n-menu
        :value="activeKey"
        :options="menuOptions"
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="20"
      />
    </n-layout-sider>

    <n-drawer v-model:show="drawerOpen" placement="left" :width="230">
      <n-drawer-content body-content-style="padding: 0">
        <div class="side-head">
          <div class="brand-logo">S</div>
          <div class="brand-copy">
            <div class="brand-title">Sublink</div>
            <div class="brand-sub">订阅管理后台</div>
          </div>
        </div>
        <n-menu :value="activeKey" :options="menuOptions" />
      </n-drawer-content>
    </n-drawer>

    <n-layout
      class="right-shell"
      content-style="display:flex;flex-direction:column;height:100%;overflow:hidden;"
    >
      <n-layout-header bordered class="top-bar">
        <div class="top-bar-inner">
          <div class="top-left">
            <n-button v-if="isMobile" quaternary circle @click="drawerOpen = true">
              <template #icon>
                <n-icon>
                  <svg viewBox="0 0 24 24" width="20" height="20">
                    <path fill="currentColor" d="M3 6h18v2H3V6zm0 5h18v2H3v-2zm0 5h18v2H3v-2z" />
                  </svg>
                </n-icon>
              </template>
            </n-button>
            <div class="top-title">{{ pageTitle }}</div>
          </div>
          <div class="top-actions">
            <n-button
              quaternary
              circle
              :title="themeMode === 'light' ? '切换深色主题' : '切换浅色主题'"
              @click="toggleTheme"
            >
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
            <n-tag :bordered="false" round type="primary">{{ username || '未登录' }}</n-tag>
            <n-button size="small" secondary @click="confirmLogout">退出登录</n-button>
          </div>
        </div>
      </n-layout-header>

      <n-layout-content class="main" :native-scrollbar="false" content-style="min-height:100%;">
        <div class="page-container">
          <router-view />
        </div>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
/* 锁定视口高度，仅右侧内容区独立滚动，侧栏与顶栏始终固定 */
.shell {
  height: 100vh;
  overflow: hidden;
}

.right-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

/* 与顶栏保持等高 58px，左侧固定 14px 边距（(64-36)/2=14px），展开收起时图标零位移零跳动 */
.side-head {
  align-items: center;
  display: flex;
  flex: none;
  gap: 12px;
  height: 58px;
  overflow: hidden;
  padding: 0 14px;
}

.brand-logo {
  align-items: center;
  background: linear-gradient(135deg, #6366f1, #22d3ee);
  border-radius: 10px;
  color: #fff;
  display: flex;
  flex: none;
  font-size: 19px;
  font-weight: 700;
  height: 36px;
  justify-content: center;
  width: 36px;
}

.brand-copy {
  min-width: 0;
  opacity: 1;
  overflow: hidden;
  transition: opacity 0.18s ease;
  white-space: nowrap;
}

.side-head.compact .brand-copy {
  opacity: 0;
  pointer-events: none;
}

.brand-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
}

.brand-sub {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
  line-height: 1.3;
  margin-top: 2px;
}

.top-bar {
  display: flex;
  flex: none;
  height: 58px;
  min-height: 58px;
  overflow: hidden;
}

/* 顶栏与下方内容容器共享 1160px 居中骨架：左右边界严丝合缝，大屏不空荡、小屏自适应 */
.top-bar-inner {
  align-items: center;
  display: flex;
  height: 100%;
  justify-content: space-between;
  margin: 0 auto;
  max-width: 1160px;
  padding: 0 24px;
  width: 100%;
}

.top-left {
  align-items: center;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.top-title {
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-actions {
  align-items: center;
  display: flex;
  flex: none;
  gap: 10px;
  white-space: nowrap;
}

/* 亮色模式下铺满整屏浅灰画布，让白色卡片层级分明；暗色模式沿用深底 */
.shell.light .main,
.shell.light .main :deep(.n-layout-scroll-container) {
  background: #f5f7fa;
}

.main {
  flex: 1;
  min-height: 0;
}

.page-container {
  margin: 0 auto;
  max-width: 1160px;
  padding: 24px;
  width: 100%;
}

@media (max-width: 767px) {
  .top-bar-inner {
    padding: 0 14px;
  }

  .page-container {
    padding: 14px;
  }
}
</style>
