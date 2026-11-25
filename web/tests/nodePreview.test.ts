import { describe, expect, it } from 'vitest'
import { parseNodePreview } from '@/utils/nodePreview'

function encodeBase64Utf8(text: string): string {
  const bytes = new TextEncoder().encode(text)
  let binary = ''
  bytes.forEach((b) => {
    binary += String.fromCharCode(b)
  })
  return btoa(binary)
}

function encodeBase64UrlUtf8(text: string): string {
  return encodeBase64Utf8(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

describe('parseNodePreview', () => {
  it('parses VLESS URI fragment, invalid percent-encoding, and host fallbacks', () => {
    const emojiTitle = parseNodePreview({
      node: 'vless://uuid@example.com:443?security=reality#%F0%9F%87%AD%F0%9F%87%B0%20%E9%A6%99%E6%B8%AF',
      remarks: '备用'
    })
    expect(emojiTitle).toEqual({ proto: 'VLESS', tagType: 'primary', title: '🇭🇰 香港' })

    const invalidPct = parseNodePreview({
      node: 'vless://uuid@example.com:443#bad%E0%A4%A',
      remarks: ''
    })
    expect(invalidPct.title).toBe('bad%E0%A4%A')

    const remarkFallback = parseNodePreview({
      node: 'vless://uuid@example.com:443?security=tls',
      remarks: '我的备注'
    })
    expect(remarkFallback.title).toBe('我的备注')

    const ipv6Fallback = parseNodePreview({
      node: 'vless://uuid@[2001:db8::1]:443?security=tls',
      remarks: ''
    })
    expect(ipv6Fallback.title).toBe('[2001:db8::1]:443')
  })

  it('parses VMess Base64 JSON (including trailing slash and URL-safe base64) and query format', () => {
    const payload = JSON.stringify({ ps: '日本东京', add: 'jp.example.com', port: 443 })
    const trailingSlash = parseNodePreview({
      node: `vmess://${encodeBase64Utf8(payload)}/`,
      remarks: ''
    })
    expect(trailingSlash).toEqual({ proto: 'VMess', tagType: 'info', title: '日本东京' })

    const urlSafeNoPs = parseNodePreview({
      node: `vmess://${encodeBase64UrlUtf8(JSON.stringify({ add: 'sg.example.com', port: 8443 }))}`,
      remarks: ''
    })
    expect(urlSafeNoPs.title).toBe('sg.example.com:8443')

    const fallbackRemark = parseNodePreview({
      node: `vmess://${encodeBase64Utf8(JSON.stringify({ add: 'sg.example.com', port: 8443 }))}`,
      remarks: '自定义VMess'
    })
    expect(fallbackRemark.title).toBe('自定义VMess')

    const queryStyle = parseNodePreview({
      node: 'vmess://uuid@1.2.3.4:443?remarks=SG-Query&tls=1',
      remarks: ''
    })
    expect(queryStyle.title).toBe('SG-Query')
  })

  it('parses SSR remarks with plus-sign restoration and IPv4/IPv6 host fallbacks', () => {
    // '>>>' base64 is 'Pj4+', ensuring '+' decoded as space by URLSearchParams is restored.
    const remB64 = encodeBase64Utf8('>>>')
    expect(remB64).toContain('+')
    const ssrWithRemark = parseNodePreview({
      node: `ssr://${encodeBase64UrlUtf8(`1.2.3.4:8388:origin:aes-256-cfb:plain:cHdk/?remarks=${remB64}`)}`,
      remarks: ''
    })
    expect(ssrWithRemark).toEqual({ proto: 'SSR', tagType: 'default', title: '>>>' })

    const ssrIpv6 = parseNodePreview({
      node: `ssr://${encodeBase64UrlUtf8('[2001:db8::2]:8388:origin:aes-256-cfb:plain:cHdk')}`,
      remarks: ''
    })
    expect(ssrIpv6.title).toBe('[2001:db8::2]:8388')

    const ssrIpv4WithFallback = parseNodePreview({
      node: `ssr://${encodeBase64UrlUtf8('8.8.8.8:8388:origin:aes-256-cfb:plain:cHdk')}`,
      remarks: 'SSR 兜底'
    })
    expect(ssrIpv4WithFallback.title).toBe('SSR 兜底')
  })

  it('parses SS (SIP002 & legacy full-base64), Trojan, Hysteria, and Hysteria2/Hy2', () => {
    const ssSip002 = parseNodePreview({
      node: 'ss://YWVzLTI1Ni1nY206cGFzcw@ss.example.com:8388#HK-SS',
      remarks: ''
    })
    expect(ssSip002).toEqual({ proto: 'SS', tagType: 'success', title: 'HK-SS' })

    const ssLegacy = parseNodePreview({
      node: `ss://${encodeBase64Utf8('aes-256-gcm:secret@legacy.example.com:9000')}`,
      remarks: ''
    })
    expect(ssLegacy).toEqual({ proto: 'SS', tagType: 'success', title: 'legacy.example.com:9000' })

    expect(
      parseNodePreview({ node: 'trojan://pwd@tr.example.com:443#TR-1', remarks: '' })
    ).toEqual({ proto: 'Trojan', tagType: 'warning', title: 'TR-1' })

    expect(
      parseNodePreview({ node: 'hysteria://hy.example.com:443?auth=a#HY-1', remarks: '' })
    ).toEqual({ proto: 'Hy', tagType: 'warning', title: 'HY-1' })

    expect(
      parseNodePreview({ node: 'hy2://pwd@hy2.example.com:443#HY2-A', remarks: '' })
    ).toEqual({ proto: 'Hy2', tagType: 'error', title: 'HY2-A' })

    expect(
      parseNodePreview({ node: 'hysteria2://pwd@hy2.example.com:443#HY2-B', remarks: '' })
    ).toEqual({ proto: 'Hy2', tagType: 'error', title: 'HY2-B' })
  })

  it('parses remote http(s) subscriptions and unknown/empty nodes', () => {
    expect(
      parseNodePreview({ node: 'https://sub.example.com/', remarks: '' })
    ).toEqual({ proto: '远程订阅', tagType: 'info', title: 'sub.example.com' })

    expect(
      parseNodePreview({ node: 'https://sub.example.com:2096/sub/token123', remarks: '' })
    ).toEqual({ proto: '远程订阅', tagType: 'info', title: 'sub.example.com:2096/sub/token123' })

    expect(
      parseNodePreview({ node: 'tuic://uuid:pwd@tuic.example.com:443#TUIC-1', remarks: '' })
    ).toEqual({ proto: 'TUIC', tagType: 'default', title: 'TUIC-1' })

    expect(parseNodePreview({ node: '   ', remarks: '' })).toEqual({
      proto: 'NODE',
      tagType: 'default',
      title: '未命名节点'
    })
  })
})
