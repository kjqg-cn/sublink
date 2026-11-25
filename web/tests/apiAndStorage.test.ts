import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  currentUsername,
  encodeLegacyName,
  groupSubs,
  legacySubUrl,
  subUrl,
  validateSubName,
  type SubNode
} from '@/api'
import {
  ACTIVE_SUB_STORAGE_KEY,
  clearSessionState,
  DRAFT_NODES_STORAGE_KEY,
  storageGet,
  storageRemove,
  storageSet
} from '@/utils/storage'

function makeJwt(payload: Record<string, unknown>): string {
  const b64 = (obj: Record<string, unknown>) => {
    const bytes = new TextEncoder().encode(JSON.stringify(obj))
    let bin = ''
    bytes.forEach((b) => {
      bin += String.fromCharCode(b)
    })
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  }
  return `${b64({ alg: 'HS256' })}.${b64(payload)}.sig`
}

describe('api pure helpers', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('validates subscription names against empty, length, and URL-sensitive characters', () => {
    expect(validateSubName('')).toBeTruthy()
    expect(validateSubName('   ')).toBeTruthy()
    expect(validateSubName('a'.repeat(41))).toBeTruthy()
    expect(validateSubName('.')).toBeTruthy()
    expect(validateSubName('..')).toBeTruthy()
    expect(validateSubName('foo/bar')).toBeTruthy()
    expect(validateSubName('foo\\bar')).toBeTruthy()
    expect(validateSubName('foo?bar')).toBeTruthy()
    expect(validateSubName('foo#bar')).toBeTruthy()
    expect(validateSubName('bad\x07name')).toBeTruthy()

    expect(validateSubName('🇭🇰 香港主力节点')).toBeNull()
    expect(validateSubName('a'.repeat(40))).toBeNull()
  })

  it('groups flat SubNode rows and sorts summaries by sort_order', () => {
    const rows: SubNode[] = [
      { id: 1, name: 'US', node: 'vless://1', remarks: '', access_token: 't1', legacy_enabled: false, sort_order: 2 },
      { id: 2, name: 'HK', node: 'vless://2', remarks: '', access_token: 't2', legacy_enabled: false, sort_order: 0 },
      { id: 3, name: 'HK', node: 'vless://3', remarks: '', access_token: 't2', legacy_enabled: false, sort_order: 0 },
      { id: 4, name: 'JP', node: 'vless://4', remarks: '', access_token: 't3', legacy_enabled: true, sort_order: 1 }
    ]
    expect(groupSubs(rows)).toEqual([
      { name: 'HK', count: 2, sortOrder: 0 },
      { name: 'JP', count: 1, sortOrder: 1 },
      { name: 'US', count: 1, sortOrder: 2 }
    ])
  })

  it('builds token and legacy base64 subscription URLs with UTF-8/Emoji support', () => {
    const name = '🇭🇰 香港+测试'
    const encoded = encodeLegacyName(name)
    const decodedBytes = Uint8Array.from(atob(decodeURIComponent(encoded)), (c) => c.charCodeAt(0))
    expect(new TextDecoder().decode(decodedBytes)).toBe(name)

    expect(subUrl('sing-box', 'tok_123')).toBe(`${location.origin}/sub/sing-box/tok_123`)
    expect(legacySubUrl('clash', name)).toBe(`${location.origin}/sub/clash/${encoded}`)
  })

  it('extracts currentUsername from stored JWT sub claim', () => {
    expect(currentUsername()).toBe('')
    localStorage.setItem('token', JSON.stringify(makeJwt({ sub: 'admin' })))
    expect(currentUsername()).toBe('admin')
    localStorage.setItem('token', JSON.stringify('invalid.token'))
    expect(currentUsername()).toBe('')
  })
})

describe('safe storage helpers', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('reads, writes, removes, and clears known session keys', () => {
    expect(storageSet('local', 'k1', 'v1')).toBe(true)
    expect(storageGet('local', 'k1')).toBe('v1')
    storageRemove('local', 'k1')
    expect(storageGet('local', 'k1')).toBeNull()

    storageSet('session', ACTIVE_SUB_STORAGE_KEY, 'HK')
    storageSet('session', DRAFT_NODES_STORAGE_KEY, 'vless://x')
    clearSessionState()
    expect(storageGet('session', ACTIVE_SUB_STORAGE_KEY)).toBeNull()
    expect(storageGet('session', DRAFT_NODES_STORAGE_KEY)).toBeNull()
  })

  it('handles storage exceptions gracefully without throwing', () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError')
    })
    vi.spyOn(window.sessionStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('Full', 'QuotaExceededError')
    })
    vi.spyOn(window.localStorage, 'removeItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError')
    })

    expect(storageGet('local', 'k1')).toBeNull()
    expect(storageSet('session', 'k2', 'v2')).toBe(false)
    expect(() => storageRemove('local', 'k1')).not.toThrow()
  })
})
