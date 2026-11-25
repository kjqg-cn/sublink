<script setup lang="ts">
import { computed } from 'vue'
import {
  darkTheme,
  zhCN,
  dateZhCN,
  NConfigProvider,
  NGlobalStyle,
  NMessageProvider,
  NDialogProvider,
  type GlobalThemeOverrides
} from 'naive-ui'
import { themeMode } from './theme'

const theme = computed(() => (themeMode.value === 'dark' ? darkTheme : null))

// 统一品牌靛蓝主色与全站圆角层级，消除默认绿色控件与品牌色的视觉割裂。
const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const isDark = themeMode.value === 'dark'
  return {
    common: {
      primaryColor: isDark ? '#818cf8' : '#6366f1',
      primaryColorHover: isDark ? '#a5b4fc' : '#4f46e5',
      primaryColorPressed: isDark ? '#6366f1' : '#4338ca',
      primaryColorSuppl: isDark ? '#818cf8' : '#6366f1',
      borderRadius: '8px',
      borderRadiusSmall: '6px'
    },
    Card: {
      borderRadius: '12px',
      titleFontSizeSmall: '15px',
      titleFontSizeMedium: '15px',
      titleFontWeight: '600',
      paddingSmall: '16px 20px',
      paddingMedium: '20px 24px'
    },
    Modal: {
      borderRadius: '12px'
    }
  }
})
</script>

<template>
  <n-config-provider
    :theme="theme"
    :theme-overrides="themeOverrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
    <n-global-style />
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>
