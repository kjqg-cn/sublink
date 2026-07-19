<script setup lang="ts">
import { h, ref, type CSSProperties } from 'vue'
import {
  useMessage,
  useDialog,
  NDataTable,
  NButton,
  NSpace,
  NModal,
  NInput,
  NForm,
  NFormItem,
  type DataTableColumns
} from 'naive-ui'
import { delSubNode, setNode, type SubNode } from '@/api'

const props = defineProps<{ nodes: SubNode[]; loading: boolean }>()
const emit = defineEmits<{ refresh: [] }>()

const message = useMessage()
const dialog = useDialog()

const showEdit = ref(false)
const saving = ref(false)
const edit = ref({ id: 0, node: '', remarks: '' })

function copy(text: string) {
  navigator.clipboard.writeText(text).then(
    () => message.success('复制成功'),
    () => message.error('复制失败')
  )
}

function openEdit(row: SubNode) {
  edit.value = { id: row.id, node: row.node, remarks: row.remarks }
  showEdit.value = true
}

async function handleEdit() {
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

function confirmDel(row: SubNode) {
  const label = row.remarks || row.node.slice(0, 40)
  dialog.warning({
    title: '删除节点',
    content: `删除后无法恢复，确定删除节点“${label}”吗？`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const { code, msg } = await delSubNode(row.id)
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

const columns: DataTableColumns<SubNode> = [
  // 节点 : 备注 : 操作 = 55 : 35 : 10
  { title: '节点', key: 'node', width: '55%', ellipsis: tooltip },
  {
    title: '备注',
    key: 'remarks',
    width: '35%',
    ellipsis: tooltip,
    render: (row) => row.remarks || h('span', { style: { color: 'var(--n-text-color-disabled)' } }, '无备注')
  },
  {
    title: '操作',
    key: 'actions',
    width: '10%',
    render: (row) =>
      h(NSpace, { size: 4 }, {
        default: () => [
          h(NButton, { text: true, type: 'primary', size: 'small', onClick: () => openEdit(row) }, { default: () => '编辑' }),
          h(NButton, { text: true, size: 'small', onClick: () => copy(row.node) }, { default: () => '复制' }),
          h(NButton, { text: true, type: 'error', size: 'small', onClick: () => confirmDel(row) }, { default: () => '删除' })
        ]
      })
  }
]
</script>

<template>
  <div>
    <n-data-table
      :columns="columns"
      :data="props.nodes"
      :loading="props.loading"
      :max-height="440"
      :bordered="false"
      size="small"
    />

    <n-modal v-model:show="showEdit" preset="card" title="编辑节点" style="max-width: 560px">
      <n-form>
        <n-form-item label="节点">
          <n-input v-model:value="edit.node" type="textarea" :rows="6" placeholder="节点链接" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="edit.remarks" placeholder="可选备注" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="showEdit = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleEdit">确定</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
</style>
