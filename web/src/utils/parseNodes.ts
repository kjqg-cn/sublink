export function extractRemoteSubUrls(raw: string): string[] {
  return raw.match(/https?:\/\/[^\s]+/gi) ?? []
}

export function flattenDecodedNodes(msg: unknown): string[] {
  const chunks = Array.isArray(msg) ? msg : [msg]
  return chunks
    .flatMap((chunk) => String(chunk ?? '').split(/\r?\n/))
    .map((line) => line.trim())
    .filter(Boolean)
}

// 对含 \ 或 | 的原始节点做对称转义，防止提交 /create_sub 时被误拆为节点与备注。
export function escapeDraftNodes(nodes: string[]): string {
  return nodes
    .map((line) => line.replace(/\\/g, '\\\\').replace(/\|/g, '\\|'))
    .join('\n')
}
