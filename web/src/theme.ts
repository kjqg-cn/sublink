import { ref } from 'vue'
import { storageGet, storageSet } from '@/utils/storage'

// 亮/暗主题状态：优先读取用户缓存，首次访问自动跟随系统外观偏好。
const STORAGE_KEY = 'sublink-theme'

export type ThemeMode = 'light' | 'dark'

function getInitialTheme(): ThemeMode {
  const saved = storageGet('local', STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') {
    return saved
  }
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

export const themeMode = ref<ThemeMode>(getInitialTheme())

export function toggleTheme(): void {
  themeMode.value = themeMode.value === 'light' ? 'dark' : 'light'
  storageSet('local', STORAGE_KEY, themeMode.value)
}
