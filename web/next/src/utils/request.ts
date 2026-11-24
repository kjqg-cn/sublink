import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

// 复现旧版 request.js 的行为：JWT 携带、401 自动刷新并重放请求（带并发互斥锁，不依赖本地时钟）、刷新失败清 token 重登。
const baseURL = import.meta.env.DEV ? '/api' : ''

const instance: AxiosInstance = axios.create({ baseURL })

export interface JwtPayload {
  exp?: number
  sub?: string
}

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

export function readStoredToken(key: 'token' | 'refresh'): string | null {
  const raw = localStorage.getItem(key)
  if (!raw) return null
  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed === 'string' && parsed.trim()) {
      return parsed
    }
    return null
  } catch {
    localStorage.removeItem(key)
    return null
  }
}

export function decodeJwtPayload<T = JwtPayload>(token: string): T | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3 || !parts[1]) return null
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padLen = (4 - (base64.length % 4)) % 4
    const padded = base64 + '='.repeat(padLen)
    const binary = atob(padded)
    const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0))
    const jsonText = new TextDecoder().decode(bytes)
    return JSON.parse(jsonText) as T
  } catch {
    return null
  }
}

let refreshPromise: Promise<string> | null = null

async function refreshToken(): Promise<string> {
  if (refreshPromise) {
    return refreshPromise
  }
  const refresh = readStoredToken('refresh')
  if (!refresh) {
    clearAuthAndReload()
    throw new Error('缺少刷新令牌')
  }
  refreshPromise = (async () => {
    try {
      const res = await axios.post(
        `${baseURL}/refresh`,
        {},
        { headers: { Authorization: 'Bearer ' + refresh } }
      )
      if (res.status === 200 && typeof res.data === 'string' && res.data.trim()) {
        localStorage.setItem('token', JSON.stringify(res.data))
        return res.data
      }
      clearAuthAndReload()
      throw new Error('刷新令牌返回无效数据')
    } catch (error: unknown) {
      const status = (error as { response?: { status?: number } })?.response?.status
      if (status === 401 || status === 422) {
        clearAuthAndReload()
      }
      throw error
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

function clearAuthAndReload(): void {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh')
  if (!location.hash.startsWith('#/login')) {
    location.reload()
  }
}

const AUTH_ENDPOINT_RE = /^\/?(login|refresh)(\?|$)/

instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const url = config.url ?? ''
  if (!AUTH_ENDPOINT_RE.test(url)) {
    const token = readStoredToken('token')
    if (token) {
      config.headers.Authorization = 'Bearer ' + token
    }
  }
  return config
})

instance.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error?.response?.status
    const originalConfig = error?.config as RetryableRequestConfig | undefined
    const url = originalConfig?.url ?? ''

    if (
      status === 401 &&
      originalConfig &&
      !originalConfig._retry &&
      !AUTH_ENDPOINT_RE.test(url) &&
      readStoredToken('refresh')
    ) {
      originalConfig._retry = true
      try {
        const newToken = await refreshToken()
        originalConfig.headers.Authorization = 'Bearer ' + newToken
        return instance(originalConfig)
      } catch (refreshError) {
        return Promise.reject(refreshError)
      }
    }

    if (status === 401 || status === 422) {
      clearAuthAndReload()
    }
    return Promise.reject(error)
  }
)

export default instance
