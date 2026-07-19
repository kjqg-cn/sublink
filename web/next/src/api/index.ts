import request from '@/utils/request'

// —— 通用响应结构 ——
export interface ApiResult<T = unknown> {
  code: number
  msg: T
}

export interface LoginResult {
  code: number
  msg: string
  token?: string
  refresh?: string
}

// get_subs 返回的是所有订阅下节点的扁平数组，name 为所属订阅名。
export interface SubNode {
  id: number
  name: string
  node: string
  remarks: string
  access_token: string
  legacy_enabled: boolean
  sort_order: number
}

// —— 认证 ——
export const login = (data: { username: string; password: string }) =>
  request.post('/login', data) as Promise<LoginResult>

// —— 订阅 ——
export const getSubs = () => request.post('/get_subs') as Promise<SubNode[]>

export const getSubByName = (name: string) =>
  request.post('/get_sub/' + encodeURIComponent(name)) as Promise<SubNode[]>

// 把扁平节点数组按订阅名分组，返回按 sort_order 排序的订阅摘要。
export interface SubSummary {
  name: string
  count: number
  sortOrder: number
}

export function groupSubs(nodes: SubNode[]): SubSummary[] {
  const map = new Map<string, SubSummary>()
  for (const n of nodes) {
    const existing = map.get(n.name)
    if (existing) {
      existing.count += 1
    } else {
      map.set(n.name, { name: n.name, count: 1, sortOrder: n.sort_order })
    }
  }
  return [...map.values()].sort((a, b) => a.sortOrder - b.sortOrder)
}

export const createSub = (data: { name: string; node: string[] }) =>
  request.post('/create_sub', data) as Promise<ApiResult<string>>

export const createNode = (data: { name: string; node: string; remarks: string }) =>
  request.post('/create_node', data) as Promise<ApiResult<string>>

export const sortSubs = (names: string[]) =>
  request.post('/sort_subs', { names }) as Promise<ApiResult<string>>

export const delSub = (name: string) =>
  request.post('/del_sub/' + encodeURIComponent(name)) as Promise<ApiResult<string>>

export const delSubNode = (id: number) =>
  request.post('/del_sub_node/' + id) as Promise<ApiResult<string>>

// 批量覆盖某订阅的节点，newNode 每行 `节点|备注`。
export const setSub = (data: { name: string; newNode: string[] }) =>
  request.post('/set_sub', data) as Promise<ApiResult<string>>

// 修改单个节点。
export const setNode = (data: { id: number; node: string; remarks: string }) =>
  request.post('/set_node', data) as Promise<ApiResult<string>>

export const renameSub = (name: string, newName: string) =>
  request.post('/rename_sub/' + encodeURIComponent(name), { newName }) as Promise<ApiResult<string>>

export const setSubLegacy = (name: string, enabled: boolean) =>
  request.post('/set_sub_legacy/' + encodeURIComponent(name), { enabled }) as Promise<
    ApiResult<string>
  >

// base64 订阅解析，返回明文节点列表。
export const decodeSub = (urls: string[]) =>
  request.post('/decode_sub', { urls }) as Promise<ApiResult<string[]>>

// —— 账号 / 记录 / 全局设置 ——
export const setUser = (data: { username: string; newUserName: string; password: string }) =>
  request.post('/set_user', data) as Promise<ApiResult<string>>

export interface LoginRecord {
  id: number
  ip: string
  address: string
  time: string
}

export const getAddress = () => request.post('/get_ip_address') as Promise<LoginRecord[]>

// 全局设置：后端存 udp / skipcert / emoji（注意 skipcert 为小写）。
export interface GlobalConfig {
  udp: boolean
  skipcert: boolean
  emoji: boolean
}

export const getConfig = () => request.post('/get_conifg') as Promise<Partial<GlobalConfig>>

export const setConfig = (data: GlobalConfig) =>
  request.post('/set_conifg', data) as Promise<ApiResult<string>>

// —— 规则 / 配置编辑（clash / surge / sing-box 各一份，读写共用一个接口）——
export type RuleKind = 'clash' | 'surge' | 'sing-box'

const ruleEndpoint: Record<RuleKind, string> = {
  clash: '/clash_config',
  surge: '/surge_config',
  'sing-box': '/singbox_config'
}

export const getRule = (kind: RuleKind) =>
  request.post(ruleEndpoint[kind], { index: 'read' }) as Promise<ApiResult<string>>

export const saveRule = (kind: RuleKind, text: string) =>
  request.post(ruleEndpoint[kind], { index: 'save', text }) as Promise<ApiResult<string>>

// 订阅地址：/sub/{type}/{token}。dev 下 /sub 已代理到后端。
export type SubType = 'v2ray' | 'clash' | 'surge' | 'sing-box'

export function subUrl(type: SubType, token: string): string {
  return location.origin + `/sub/${type}/${token}`
}

// 旧版 base64 地址：对订阅名做 utf8 -> base64 -> uriencode。
export function encodeLegacyName(name: string): string {
  const bytes = new TextEncoder().encode(name)
  let binary = ''
  bytes.forEach((b) => {
    binary += String.fromCharCode(b)
  })
  return encodeURIComponent(btoa(binary))
}

export function legacySubUrl(type: SubType, name: string): string {
  return location.origin + `/sub/${type}/${encodeLegacyName(name)}`
}

// —— 账号 ——
export function currentUsername(): string {
  const raw = localStorage.getItem('token')
  if (!raw) return ''
  try {
    const token = JSON.parse(raw) as string
    const payload = JSON.parse(atob(token.split('.')[1])) as { sub: string }
    return payload.sub
  } catch {
    return ''
  }
}
