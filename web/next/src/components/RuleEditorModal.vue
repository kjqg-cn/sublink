<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useMessage, NModal, NButton, NAlert, NSpin } from 'naive-ui'
import { getRule, saveRule, type RuleKind } from '@/api'
import CodeTextarea from './CodeTextarea.vue'

const props = defineProps<{ show: boolean; kind: RuleKind }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const message = useMessage()
const text = ref('')
const loading = ref(false)
const loadFailed = ref(false)
const loadError = ref('')
const saving = ref(false)
let loadSeq = 0

const tips: Record<RuleKind, string> = {
  clash: 'proxies 节点字段会自动生成无需填写；proxy-groups 下写 auto 会插入本订阅所有节点名称。',
  surge: '[Proxy Group] 下写 auto 会插入本订阅所有节点名称列表。',
  'sing-box': 'outbounds 中的节点会自动注入，保存前会校验 JSON 格式。默认按 sing-box 1.14+ 语法输出（无 download_detour 弃用警告）；sing-box 1.12～1.13 旧版客户端可在订阅地址后追加 ?legacy=1 或 ?version=1.12。'
}

async function loadRule(kind: RuleKind) {
  const seq = ++loadSeq
  loading.value = true
  loadFailed.value = false
  loadError.value = ''
  text.value = ''
  try {
    const { code, msg } = await getRule(kind)
    if (seq !== loadSeq) return
    if (code === 200 && typeof msg === 'string') {
      text.value = msg
    } else {
      const detail = typeof msg === 'string' && msg.trim() ? msg.trim() : '读取规则失败'
      loadFailed.value = true
      loadError.value = `${detail}，已禁用保存以防覆盖原有规则`
      message.warning(detail)
    }
  } catch {
    if (seq !== loadSeq) return
    loadFailed.value = true
    loadError.value = '读取规则失败，已禁用保存以防覆盖原有规则'
    message.error('读取规则失败')
  } finally {
    if (seq === loadSeq) {
      loading.value = false
    }
  }
}

// 弹窗打开或切换规则类型时加载规则内容，使用序号防止过期响应覆盖。
watch(
  () => [props.show, props.kind] as const,
  ([show, kind]) => {
    if (!show) {
      loadSeq += 1
      loading.value = false
      loadFailed.value = false
      loadError.value = ''
      return
    }
    loadRule(kind)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  loadSeq += 1
})

async function handleSave() {
  if (loading.value || saving.value || loadFailed.value) return
  const saveSeq = loadSeq
  saving.value = true
  try {
    const { code, msg } = await saveRule(props.kind, text.value)
    const notice = typeof msg === 'string' && msg.trim()
      ? msg
      : code === 200
        ? '保存成功'
        : '保存规则失败'
    message[code === 200 ? 'success' : 'warning'](notice)
    if (code === 200 && saveSeq === loadSeq) emit('update:show', false)
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
    <n-alert v-if="loadFailed" type="error" :bordered="false" style="margin-bottom: 12px">
      <div class="load-error-row">
        <span>{{ loadError }}</span>
        <n-button size="small" secondary type="error" :disabled="loading" @click="loadRule(kind)">
          重新加载
        </n-button>
      </div>
    </n-alert>
    <n-spin :show="loading">
      <code-textarea
        v-model="text"
        :rows="18"
        :readonly="loading || saving || loadFailed"
        placeholder="规则内容"
      />
    </n-spin>
    <template #footer>
      <div class="modal-footer">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button
          type="primary"
          :loading="saving"
          :disabled="loading || saving || loadFailed"
          @click="handleSave"
        >
          保存
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.load-error-row {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
</style>
