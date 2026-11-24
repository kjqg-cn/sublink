import axios from 'axios'
import { Loading } from 'element-ui'

const baseURL = process.env.NODE_ENV === 'development' ? '/api' : ''

const instance = axios.create({
  baseURL: baseURL
})

let loadingCount = 0
let loadingInstance = null
let refreshPromise = null

const showLoading = () => {
  loadingCount += 1
  if (!loadingInstance) {
    loadingInstance = Loading.service({
      lock: true,
      text: 'Loading',
      spinner: 'el-icon-loading',
      background: 'rgba(0, 0, 0, 0.7)'
    })
  }
}

const hideLoading = () => {
  loadingCount = Math.max(0, loadingCount - 1)
  if (loadingCount === 0 && loadingInstance) {
    loadingInstance.close()
    loadingInstance = null
  }
}

export const readStoredToken = (key) => {
  const raw = localStorage.getItem(key)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return typeof parsed === 'string' && parsed.trim() ? parsed : null
  } catch (e) {
    localStorage.removeItem(key)
    return null
  }
}

export const decodeJwtPayload = (token) => {
  if (!token || typeof token !== 'string') return null
  try {
    const parts = token.split('.')
    if (parts.length !== 3 || !parts[1]) return null
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padLen = (4 - (base64.length % 4)) % 4
    const padded = base64 + '='.repeat(padLen)
    const binary = atob(padded)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i)
    }
    const jsonText = new TextDecoder().decode(bytes)
    return JSON.parse(jsonText)
  } catch (e) {
    return null
  }
}

const clearAuthAndReload = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh')
  if (!location.hash.startsWith('#/login')) {
    location.reload()
  }
}

const SetRefresh = async () => { // 刷新token（带并发互斥锁）
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
      const response = await axios.post(`${baseURL}/refresh`, {}, {
        headers: {
          Authorization: 'Bearer ' + refresh
        }
      })
      if (response.status === 200 && typeof response.data === 'string' && response.data.trim()) {
        localStorage.setItem('token', JSON.stringify(response.data)) // 设置token
        return response.data
      }
      clearAuthAndReload()
      throw new Error('刷新令牌返回无效数据')
    } catch (error) {
      const status = error?.response?.status
      if (status === 401 || status === 422) {
        clearAuthAndReload()
      }
      throw error // 抛出异常，由调用方处理
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

const AUTH_ENDPOINT_RE = /^\/?(login|refresh)(\?|$)/

// 添加请求拦截器
instance.interceptors.request.use(function (config) {
  showLoading()
  const url = config.url || ''
  if (!AUTH_ENDPOINT_RE.test(url)) {
    const token = readStoredToken('token')
    if (token) {
      config.headers.Authorization = 'Bearer ' + token
    }
  }
  return config
}, function (error) {
  hideLoading()
  return Promise.reject(error)
})

// 添加响应拦截器：服务端返回 401 时用 refresh token 刷新并重放请求，不依赖本地时钟
instance.interceptors.response.use(function (response) {
  hideLoading()
  return response.data
}, async function (error) {
  hideLoading()
  const status = error?.response?.status
  const originalConfig = error?.config
  const url = originalConfig?.url || ''

  if (
    status === 401 &&
    originalConfig &&
    !originalConfig._retry &&
    !AUTH_ENDPOINT_RE.test(url) &&
    readStoredToken('refresh')
  ) {
    originalConfig._retry = true
    try {
      const newToken = await SetRefresh()
      originalConfig.headers = originalConfig.headers || {}
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
})

export default instance
