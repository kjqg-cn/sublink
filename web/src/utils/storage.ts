/**
 * Safe Web Storage helpers that guard against SecurityError (private/sandboxed contexts)
 * and QuotaExceededError when reading or writing localStorage / sessionStorage.
 */
export type StorageArea = 'local' | 'session'

export const ACTIVE_SUB_STORAGE_KEY = 'sublink-active-sub'
export const DRAFT_NODES_STORAGE_KEY = 'sublink-draft-nodes'

function resolveStorage(area: StorageArea): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return area === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export function storageGet(area: StorageArea, key: string): string | null {
  const store = resolveStorage(area)
  if (!store) return null
  try {
    return store.getItem(key)
  } catch {
    return null
  }
}

export function storageSet(area: StorageArea, key: string, value: string): boolean {
  const store = resolveStorage(area)
  if (!store) return false
  try {
    store.setItem(key, value)
    return true
  } catch {
    return false
  }
}

export function storageRemove(area: StorageArea, key: string): void {
  const store = resolveStorage(area)
  if (!store) return
  try {
    store.removeItem(key)
  } catch {
    // Ignore storage removal errors in restricted browser contexts
  }
}

export function clearSessionState(): void {
  storageRemove('session', ACTIVE_SUB_STORAGE_KEY)
  storageRemove('session', DRAFT_NODES_STORAGE_KEY)
}
