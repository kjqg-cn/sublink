<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage, NModal, NButton, NAlert } from 'naive-ui'
import { getRule, saveRule, type RuleKind } from '@/api'
import CodeTextarea from './CodeTextarea.vue'

const props = defineProps<{ show: boolean; kind: RuleKind }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const message = useMessage()
const text = ref('')
const loading = ref(false)
const saving = ref(false)

const tips: Record<RuleKind, string> = {
  clash: 'proxies 节点字段会自动生成无需填写；proxy-groups 下写 auto 会插入本订阅所有节点名称。',
  surge: '[Proxy Group] 下写 auto 会插入本订阅所有节点名称列表。',
  'sing-box': 'outbounds 中的节点会自动注入，保存前会校验 JSON 格式。'
}

// 弹窗打开时加载规则内容。
watch(
  () => props.show,
  async (show) => {
    if (!show) return
    loading.value = true
    try {
      const { code, msg } = await getRule(props.kind)
      text.value = code === 200 ? msg : ''
      if (code !== 200) message.warning('读取规则失败')
    } catch {
      message.error('读取规则失败')
    } finally {
      loading.value = false
    }
  }
)

async function handleSave() {
  saving.value = true
  try {
    const { code, msg } = await saveRule(props.kind, text.value)
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) emit('update:show', false)
  } catch {
    message.error('保存规则失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="`${kind} 规则编辑（所有订阅共用）`"
    style="max-width: 900px"
    @update:show="emit('update:show', $event)"
  >
    <n-alert type="info" :bordered="false" style="margin-bottom: 12px">{{ tips[kind] }}</n-alert>
    <code-textarea v-model="text" :rows="18" placeholder="规则内容" />
    <template #footer>
      <div class="modal-footer">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
</style>
