import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

// 复现旧版 request.js 的行为：JWT 携带、过期自动刷新、401/400 清 token 重登。
const baseURL = import.meta.env.DEV ? '/api' : ''

const instance: AxiosInstance = axios.create({ baseURL })

interface JwtPayload {
  exp: number
  sub: string
}

function decodeToken(token: string): JwtPayload {
  const payload = token.split('.')[1]
  return JSON.parse(atob(payload)) as JwtPayload
}

function isTokenExpired(): boolean {
  const raw = localStorage.getItem('token')
  if (!raw) return false
  const token = JSON.parse(raw) as string
  const decoded = decodeToken(token)
  const now = Math.floor(Date.now() / 1000)
  return now > decoded.exp
}

async function refreshToken(): Promise<void> {
  const refresh = JSON.parse(localStorage.getItem('refresh') ?? 'null')
  try {
    const res = await axios.post(
      `${baseURL}/refresh`,
      {},
      { headers: { Authorization: 'Bearer ' + refresh } }
    )
    if (res.status === 200) {
      localStorage.setItem('token', JSON.stringify(res.data))
    }
  } catch (error) {
    clearAuthAndReload()
    throw error
  }
}

function clearAuthAndReload(): void {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh')
  location.reload()
}

instance.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  if (isTokenExpired()) {
    await refreshToken()
  }
  const token = JSON.parse(localStorage.getItem('token') ?? 'null')
  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }
  return config
})

instance.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error?.response?.status
    if (status === 400 || status === 401) {
      clearAuthAndReload()
    }
    return Promise.reject(error)
  }
)

export default instance
