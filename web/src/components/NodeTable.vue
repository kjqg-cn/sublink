<script setup lang="ts">
import { computed, h, reactive, ref, watch, type CSSProperties } from 'vue'
import {
  useMessage,
  useDialog,
  NCard,
  NDataTable,
  NButton,
  NSpace,
  NTag,
  NModal,
  NInput,
  NForm,
  NFormItem,
  type DataTableColumns
} from 'naive-ui'
import { delSubNode, setNode, type SubNode } from '@/api'
import { copyText } from '@/utils/clipboard'

const props = defineProps<{ subName: string; nodes: SubNode[]; loading: boolean }>()
const emit = defineEmits<{ refresh: [] }>()

const message = useMessage()
const dialog = useDialog()

const keyword = ref('')
const showEdit = ref(false)
const saving = ref(false)
const edit = ref({ id: 0, node: '', remarks: '' })

const pageState = reactive({
  page: 1,
  pageSize: 20,
  onChange: (page: number) => {
    pageState.page = page
  }
})

type TagType = 'default' | 'info' | 'success' | 'warning' | 'error' | 'primary'

interface NodePreview {
  proto: string
  tagType: TagType
  title: string
}

interface EnrichedNodeRow {
  row: SubNode
  preview: NodePreview
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

function parseNodePreview(nodeRow: SubNode): NodePreview {
  const raw = (nodeRow.node || '').trim()
  const fallbackRemark = nodeRow.remarks || ''
  const schemeMatch = raw.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//)
  const scheme = schemeMatch ? schemeMatch[1].toLowerCase() : ''
  const meta = PROTO_META[scheme] ?? { label: scheme ? scheme.toUpperCase() : 'NODE', type: 'default' as TagType }

  if (scheme === 'vmess') {
    const body = raw.slice('vmess://'.length)
    const obj = decodeBase64Json(body.split('#', 1)[0])
    if (obj) {
      const ps = typeof obj.ps === 'string' ? obj.ps.trim() : ''
      if (ps) return { proto: meta.label, tagType: meta.type, title: ps }
      const add = typeof obj.add === 'string' ? obj.add.trim() : ''
      const port = obj.port != null ? String(obj.port).trim() : ''
      const hostFallback = add ? (port ? `${add}:${port}` : add) : ''
      return { proto: meta.label, tagType: meta.type, title: fallbackRemark.trim() || hostFallback || '未命名节点' }
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
      return { proto: meta.label, tagType: meta.type, title: `${u.host}${u.pathname === '/' ? '' : u.pathname}` }
    } catch {
      return { proto: meta.label, tagType: meta.type, title: fallbackRemark.trim() || '远程订阅' }
    }
  }

  return { proto: meta.label, tagType: meta.type, title: safeHostFallback(raw, fallbackRemark) }
}

const enrichedNodes = computed<EnrichedNodeRow[]>(() =>
  props.nodes.map((row) => ({ row, preview: parseNodePreview(row) }))
)

const filteredNodes = computed<EnrichedNodeRow[]>(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return enrichedNodes.value
  return enrichedNodes.value.filter(({ row, preview }) =>
    preview.proto.toLowerCase().includes(q) ||
    preview.title.toLowerCase().includes(q) ||
    row.node.toLowerCase().includes(q) ||
    (row.remarks || '').toLowerCase().includes(q)
  )
})

watch(
  () => props.subName,
  () => {
    keyword.value = ''
    pageState.page = 1
  }
)

watch(
  () => filteredNodes.value.length,
  (len) => {
    const maxPage = Math.max(1, Math.ceil(len / pageState.pageSize))
    if (pageState.page > maxPage) {
      pageState.page = maxPage
    }
  }
)

const pagination = computed(() => (filteredNodes.value.length > pageState.pageSize ? pageState : false))

async function copy(text: string) {
  const ok = await copyText(text)
  message[ok ? 'success' : 'error'](ok ? '复制成功' : '复制失败')
}

function openEdit(row: SubNode) {
  edit.value = { id: row.id, node: row.node, remarks: row.remarks }
  showEdit.value = true
}

async function handleEdit() {
  if (saving.value) return
  if (!edit.value.node.trim()) {
    message.warning('节点不能为空')
    return
  }
  saving.value = true
  try {
    const { code, msg } = await setNode({
      id: edit.value.id,
      node: edit.value.node.trim(),
      remarks: edit.value.remarks.trim()
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      showEdit.value = false
      emit('refresh')
    }
  } catch {
    message.error('保存节点失败')
  } finally {
    saving.value = false
  }
}

function confirmDel(item: EnrichedNodeRow) {
  const label = item.row.remarks || item.preview.title.slice(0, 40)
  dialog.warning({
    title: '删除节点',
    content: `删除后无法恢复，确定删除节点“${label}”吗？`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const { code, msg } = await delSubNode(item.row.id)
        message[code === 200 ? 'success' : 'warning'](msg)
        if (code === 200) emit('refresh')
      } catch {
        message.error('删除节点失败')
      }
    }
  })
}

// 悬浮框限制宽度并强制换行，避免长节点撑出屏幕产生滚动条
const tooltip = {
  tooltip: {
    style: { maxWidth: '480px' } as CSSProperties,
    contentStyle: { wordBreak: 'break-all', whiteSpace: 'normal' } as CSSProperties
  }
}

const columns: DataTableColumns<EnrichedNodeRow> = [
  {
    title: '协议',
    key: 'proto',
    width: 92,
    render: (item) =>
      h(
        NTag,
        { size: 'small', bordered: false, type: item.preview.tagType, class: 'proto-tag' },
        { default: () => item.preview.proto }
      )
  },
  {
    title: '节点',
    key: 'node',
    minWidth: 240,
    ellipsis: tooltip,
    render: (item) => h('span', { class: 'node-title' }, item.preview.title)
  },
  {
    title: '备注',
    key: 'remarks',
    width: 170,
    ellipsis: tooltip,
    render: (item) =>
      item.row.remarks || h('span', { style: { color: 'var(--n-text-color-disabled)' } }, '—')
  },
  {
    title: '操作',
    key: 'actions',
    width: 132,
    render: (item) =>
      h(NSpace, { size: 8, wrap: false }, {
        default: () => [
          h(NButton, { text: true, type: 'primary', size: 'small', onClick: () => openEdit(item.row) }, { default: () => '编辑' }),
          h(NButton, { text: true, size: 'small', onClick: () => copy(item.row.node) }, { default: () => '复制' }),
          h(NButton, { text: true, type: 'error', size: 'small', onClick: () => confirmDel(item) }, { default: () => '删除' })
        ]
      })
  }
]
</script>

<template>
  <n-card size="small" class="node-card">
    <template #header>
      <div class="node-card-head">
        <span>节点列表</span>
        <span class="node-stat">
          {{ keyword.trim() ? `${filteredNodes.length} / ${props.nodes.length}` : `共 ${props.nodes.length} 条` }}
        </span>
      </div>
    </template>
    <template #header-extra>
      <n-input
        v-model:value="keyword"
        size="small"
        clearable
        placeholder="筛选协议、名称或备注"
        style="width: 210px"
      />
    </template>

    <n-data-table
      :columns="columns"
      :data="filteredNodes"
      :row-key="(item: EnrichedNodeRow) => item.row.id"
      :loading="props.loading"
      :pagination="pagination"
      :scroll-x="640"
      :bordered="false"
      size="small"
    />

    <n-modal
      v-model:show="showEdit"
      preset="card"
      title="编辑节点"
      style="width: calc(100vw - 32px); max-width: 560px"
    >
      <n-form>
        <n-form-item label="节点">
          <n-input v-model:value="edit.node" type="textarea" :rows="6" placeholder="节点链接" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input
            v-model:value="edit.remarks"
            :maxlength="40"
            show-count
            placeholder="可选备注（无 #名称 节点导出时自动兜底）"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="showEdit = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleEdit">确定</n-button>
        </div>
      </template>
    </n-modal>
  </n-card>
</template>

<style scoped>
.node-card-head {
  align-items: center;
  display: flex;
  font-size: 15px;
  font-weight: 600;
  gap: 8px;
}

.node-stat {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
  font-weight: 400;
}

:deep(.proto-tag) {
  font-weight: 600;
}

:deep(.node-title) {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
  white-space: nowrap;
}

.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
</style>
