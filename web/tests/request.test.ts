import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios, { type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import request, { decodeJwtPayload, readStoredToken } from '@/utils/request'
import { ACTIVE_SUB_STORAGE_KEY, DRAFT_NODES_STORAGE_KEY } from '@/utils/storage'

function makeJwt(payload: Record<string, unknown>): string {
  const encode = (obj: Record<string, unknown>) => {
    const bytes = new TextEncoder().encode(JSON.stringify(obj))
    let binary = ''
    bytes.forEach((b) => {
      binary += String.fromCharCode(b)
    })
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  }
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.sig`
}

function makeHttpError(status: number, config: InternalAxiosRequestConfig) {
  return {
    isAxiosError: true,
    config,
    response: { status, data: { msg: 'error' } }
  }
}

describe('request token utilities', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('reads valid JSON string tokens and purges corrupted values', () => {
    localStorage.setItem('token', JSON.stringify('abc.def.ghi'))
    expect(readStoredToken('token')).toBe('abc.def.ghi')

    localStorage.setItem('token', JSON.stringify('   '))
    expect(readStoredToken('token')).toBeNull()

    localStorage.setItem('token', '{broken-json')
    expect(readStoredToken('token')).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('decodes UTF-8 base64url JWT payloads and rejects malformed tokens', () => {
    const jwt = makeJwt({ sub: '管理员', exp: 1999999999 })
    expect(decodeJwtPayload(jwt)).toEqual({ sub: '管理员', exp: 1999999999 })
    expect(decodeJwtPayload('not-a-jwt')).toBeNull()
    expect(decodeJwtPayload('a.!!!.c')).toBeNull()
  })
})

describe('request interceptors and concurrent 401 refresh lock', () => {
  const originalAdapter = request.defaults.adapter
  let reloadSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    window.location.hash = '#/subs'
    reloadSpy = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
  })

  afterEach(() => {
    request.defaults.adapter = originalAdapter
    vi.restoreAllMocks()
  })

  it('attaches Authorization header to API requests but skips /login and /refresh', async () => {
    localStorage.setItem('token', JSON.stringify('access-1'))
    const seenAuth: Record<string, unknown> = {}

    const adapter: AxiosAdapter = async (config) => {
      seenAuth[config.url ?? ''] = config.headers.Authorization
      return { status: 200, statusText: 'OK', headers: {}, config, data: { ok: true } }
    }
    request.defaults.adapter = adapter

    await request.post('/get_subs')
    await request.post('/login', {})
    await request.post('/refresh', {})
    await request.post('/login?from=guard', {})

    expect(seenAuth['/get_subs']).toBe('Bearer access-1')
    expect(seenAuth['/login']).toBeUndefined()
    expect(seenAuth['/refresh']).toBeUndefined()
    expect(seenAuth['/login?from=guard']).toBeUndefined()
  })

  it('deduplicates concurrent 401 refreshes into a single /refresh call and replays all requests', async () => {
    localStorage.setItem('token', JSON.stringify('expired-access'))
    localStorage.setItem('refresh', JSON.stringify('valid-refresh'))

    const postSpy = vi.spyOn(axios, 'post').mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({ status: 200, data: 'fresh-access' }), 15)
        })
    )

    const adapter: AxiosAdapter = async (config) => {
      if (config.headers.Authorization === 'Bearer expired-access') {
        throw makeHttpError(401, config)
      }
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: { path: config.url, auth: config.headers.Authorization }
      }
    }
    request.defaults.adapter = adapter

    const results = await Promise.all([
      request.post('/sub_a'),
      request.post('/sub_b'),
      request.post('/sub_c')
    ])

    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(postSpy.mock.calls[0][0]).toMatch(/\/refresh$/)
    expect(postSpy.mock.calls[0][2]).toEqual({
      headers: { Authorization: 'Bearer valid-refresh' }
    })
    expect(readStoredToken('token')).toBe('fresh-access')
    expect(results).toEqual([
      { path: '/sub_a', auth: 'Bearer fresh-access' },
      { path: '/sub_b', auth: 'Bearer fresh-access' },
      { path: '/sub_c', auth: 'Bearer fresh-access' }
    ])
    expect(reloadSpy).not.toHaveBeenCalled()
  })

  it('clears auth and session state and reloads when refresh fails with 401 outside #/login', async () => {
    localStorage.setItem('token', JSON.stringify('expired-access'))
    localStorage.setItem('refresh', JSON.stringify('expired-refresh'))
    sessionStorage.setItem(ACTIVE_SUB_STORAGE_KEY, 'HK')
    sessionStorage.setItem(DRAFT_NODES_STORAGE_KEY, 'vless://x')

    vi.spyOn(axios, 'post').mockRejectedValue({ response: { status: 401 } })
    request.defaults.adapter = async (config) => {
      throw makeHttpError(401, config)
    }

    await expect(request.post('/get_subs')).rejects.toBeDefined()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('refresh')).toBeNull()
    expect(sessionStorage.getItem(ACTIVE_SUB_STORAGE_KEY)).toBeNull()
    expect(sessionStorage.getItem(DRAFT_NODES_STORAGE_KEY)).toBeNull()
    expect(reloadSpy).toHaveBeenCalledTimes(1)
  })

  it('does not reload when already on #/login', async () => {
    window.location.hash = '#/login'
    localStorage.setItem('token', JSON.stringify('expired-access'))

    request.defaults.adapter = async (config) => {
      throw makeHttpError(401, config)
    }

    await expect(request.post('/get_subs')).rejects.toBeDefined()
    expect(localStorage.getItem('token')).toBeNull()
    expect(reloadSpy).not.toHaveBeenCalled()
  })

  it('preserves stored tokens when /refresh fails with transient 500 error', async () => {
    localStorage.setItem('token', JSON.stringify('expired-access'))
    localStorage.setItem('refresh', JSON.stringify('valid-refresh'))

    vi.spyOn(axios, 'post').mockRejectedValue({ response: { status: 500 } })
    request.defaults.adapter = async (config) => {
      throw makeHttpError(401, config)
    }

    await expect(request.post('/get_subs')).rejects.toBeDefined()
    expect(readStoredToken('token')).toBe('expired-access')
    expect(readStoredToken('refresh')).toBe('valid-refresh')
    expect(reloadSpy).not.toHaveBeenCalled()
  })

  it('prevents infinite retry loop if replayed request still responds with 401', async () => {
    localStorage.setItem('token', JSON.stringify('expired-access'))
    localStorage.setItem('refresh', JSON.stringify('valid-refresh'))

    const postSpy = vi.spyOn(axios, 'post').mockResolvedValue({ status: 200, data: 'still-rejected' })
    request.defaults.adapter = async (config) => {
      throw makeHttpError(401, config)
    }

    await expect(request.post('/get_subs')).rejects.toBeDefined()
    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('token')).toBeNull()
    expect(reloadSpy).toHaveBeenCalledTimes(1)
  })
})
