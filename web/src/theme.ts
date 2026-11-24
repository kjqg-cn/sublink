import { ref } from 'vue'

// 亮/暗主题状态，持久化到 localStorage。
const STORAGE_KEY = 'sublink-theme'

export type ThemeMode = 'light' | 'dark'

const saved = (localStorage.getItem(STORAGE_KEY) as ThemeMode | null) ?? 'light'

export const themeMode = ref<ThemeMode>(saved)

export function toggleTheme(): void {
  themeMode.value = themeMode.value === 'light' ? 'dark' : 'light'
  localStorage.setItem(STORAGE_KEY, themeMode.value)
}
