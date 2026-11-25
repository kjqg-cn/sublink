import type { SubNode } from '@/api'

export type TagType = 'default' | 'info' | 'success' | 'warning' | 'error' | 'primary'

export interface NodePreview {
  proto: string
  tagType: TagType
  title: string
}

const PROTO_META: Record<string, { label: string; type: TagType }> = {
  vless: { label: 'VLESS', type: 'primary' },
  vmess: { label: 'VMess', type: 'info' },
  trojan: { label: 'Trojan', type: 'warning' },
  ss: { label: 'SS', type: 'success' },
  ssr: { label: 'SSR', type: 'default' },
  hysteria: { label: 'Hy', type: 'warning' },
  hysteria2: { label: 'Hy2', type: 'error' },
  hy2: { label: 'Hy2', type: 'error' },
  http: { label: '远程订阅', type: 'info' },
  https: { label: '远程订阅', type: 'info' }
}

function decodeBase64Text(raw: string): string | null {
  try {
    const normalized = raw.trim().replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4)
    const binary = atob(padded)
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0))
    return new TextDecoder().decode(bytes)
  } catch {
    return null
  }
}

function decodeBase64Json(raw: string): Record<string, unknown> | null {
  const text = decodeBase64Text(raw)
  if (!text) return null
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function safeHostFallback(raw: string, fallbackRemark: string): string {
  if (fallbackRemark.trim()) return fallbackRemark.trim()
  const atIdx = raw.lastIndexOf('@')
  if (atIdx !== -1) {
    try {
      const u = new URL(raw)
      if (u.host) return u.host
    } catch {
      // Non-standard proxy URI; fall through to manual host extraction
    }
    const hostPort = raw.slice(atIdx + 1).split(/[/?#]/, 1)[0].trim()
    if (hostPort) return hostPort
  }
  return '未命名节点'
}

function extractSsrHostPort(decoded: string): string {
  if (decoded.startsWith('[')) {
    const closeIdx = decoded.indexOf(']:')
    if (closeIdx !== -1) {
      const restPort = decoded.slice(closeIdx + 2).split(':', 1)[0]
      if (restPort) return `${decoded.slice(0, closeIdx + 1)}:${restPort}`
    }
  }
  const parts = decoded.split(':')
  return parts.length >= 2 && parts[0] && parts[1] ? `${parts[0]}:${parts[1]}` : ''
}

export function parseNodePreview(nodeRow: Pick<SubNode, 'node' | 'remarks'>): NodePreview {
  const raw = (nodeRow.node || '').trim()
  const fallbackRemark = nodeRow.remarks || ''
  const schemeMatch = raw.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//)
  const scheme = schemeMatch ? schemeMatch[1].toLowerCase() : ''
  const meta = PROTO_META[scheme] ?? {
    label: scheme ? scheme.toUpperCase() : 'NODE',
    type: 'default' as TagType
  }

  if (scheme === 'vmess') {
    const body = raw.slice('vmess://'.length)
    const obj = decodeBase64Json(body.split('#', 1)[0].replace(/\/+$/, ''))
    if (obj) {
      const ps = typeof obj.ps === 'string' ? obj.ps.trim() : ''
      if (ps) return { proto: meta.label, tagType: meta.type, title: ps }
      const add = typeof obj.add === 'string' ? obj.add.trim() : ''
      const port = obj.port != null ? String(obj.port).trim() : ''
      const hostFallback = add ? (port ? `${add}:${port}` : add) : ''
      return {
        proto: meta.label,
        tagType: meta.type,
        title: fallbackRemark.trim() || hostFallback || '未命名节点'
      }
    }

    // 兼容 Query 风格 vmess://uuid@host:port?remarks=...
    const qIdx = body.indexOf('?')
    if (qIdx !== -1) {
      const params = new URLSearchParams(body.slice(qIdx + 1).split('#', 1)[0])
      const rem = (params.get('remarks') || '').trim()
      if (rem) return { proto: meta.label, tagType: meta.type, title: rem }
    }
  }

  if (scheme === 'ssr') {
    const decoded = decodeBase64Text(raw.slice('ssr://'.length).split('#', 1)[0])
    if (decoded) {
      const qIdx = decoded.indexOf('/?')
      if (qIdx !== -1) {
        const params = new URLSearchParams(decoded.slice(qIdx + 2))
        const remB64 = params.get('remarks')
        if (remB64) {
          // URLSearchParams 会把 '+' 解码为空格，Base64 解码前先还原 '+'。
          const remText = decodeBase64Text(remB64.replace(/ /g, '+'))?.trim()
          if (remText) return { proto: meta.label, tagType: meta.type, title: remText }
        }
      }
      const hostPart = extractSsrHostPort(decoded)
      if (hostPart) {
        return { proto: meta.label, tagType: meta.type, title: fallbackRemark.trim() || hostPart }
      }
    }
  }

  const hashIdx = raw.indexOf('#')
  if (hashIdx !== -1) {
    const frag = raw.slice(hashIdx + 1).trim()
    if (frag) {
      try {
        return { proto: meta.label, tagType: meta.type, title: decodeURIComponent(frag) }
      } catch {
        return { proto: meta.label, tagType: meta.type, title: frag }
      }
    }
  }

  if (scheme === 'ss' && !raw.includes('@')) {
    const decoded = decodeBase64Text(raw.slice('ss://'.length).split(/[?#]/, 1)[0])
    if (decoded && decoded.includes('@')) {
      const hostPart = decoded.slice(decoded.lastIndexOf('@') + 1).trim()
      if (hostPart) {
        return { proto: meta.label, tagType: meta.type, title: fallbackRemark.trim() || hostPart }
      }
    }
  }

  if (scheme === 'http' || scheme === 'https') {
    try {
      const u = new URL(raw)
      return {
        proto: meta.label,
        tagType: meta.type,
        title: `${u.host}${u.pathname === '/' ? '' : u.pathname}`
      }
    } catch {
      return { proto: meta.label, tagType: meta.type, title: fallbackRemark.trim() || '远程订阅' }
    }
  }

  return { proto: meta.label, tagType: meta.type, title: safeHostFallback(raw, fallbackRemark) }
}
