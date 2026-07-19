<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  useMessage,
  NCard,
  NSelect,
  NInput,
  NInputGroup,
  NInputGroupLabel,
  NButton,
  NSwitch,
  NTag,
  NSpace
} from 'naive-ui'
import {
  setSubLegacy,
  subUrl,
  legacySubUrl,
  type SubType,
  type SubNode
} from '@/api'
import QrModal from './QrModal.vue'
import RuleEditorModal from './RuleEditorModal.vue'

const props = defineProps<{ name: string; token: string; legacyEnabled: boolean }>()
const emit = defineEmits<{ 'legacy-changed': [enabled: boolean] }>()

const message = useMessage()

const typeOptions: { label: string; value: SubType }[] = [
  { label: 'v2ray', value: 'v2ray' },
  { label: 'clash', value: 'clash' },
  { label: 'surge', value: 'surge' },
  { label: 'sing-box', value: 'sing-box' }
]

const subType = ref<SubType>('v2ray')
const legacy = ref(props.legacyEnabled)
const legacyUpdating = ref(false)
const showQr = ref(false)
const qrText = ref('')
const showRule = ref(false)

watch(
  () => props.legacyEnabled,
  (v) => {
    legacy.value = v
  }
)

// 有 token 用 token 地址，否则回退到 base64 旧地址编码。
const mainUrl = computed(() =>
  props.token ? subUrl(subType.value, props.token) : legacySubUrl(subType.value, props.name)
)
const legacyUrl = computed(() => legacySubUrl(subType.value, props.name))

// clash/surge/sing-box 才有规则编辑。
const ruleKind = computed(() => (subType.value === 'v2ray' ? null : subType.value))

function copy(text: string) {
  navigator.clipboard.writeText(text).then(
    () => message.success('复制成功'),
    () => message.error('复制失败')
  )
}

function openQr(text: string) {
  qrText.value = text
  showQr.value = true
}

async function toggleLegacy(value: boolean) {
  legacyUpdating.value = true
  try {
    const { code, msg } = await setSubLegacy(props.name, value)
    if (code === 200) {
      legacy.value = value
      emit('legacy-changed', value)
    } else {
      legacy.value = !value
      message.warning(msg)
    }
  } catch {
    legacy.value = !value
    message.warning('旧地址兼容状态保存失败，请刷新后重试')
  } finally {
    legacyUpdating.value = false
  }
}
</script>

<template>
  <n-card size="small" class="addr-card" title="订阅地址">
    <template #header-extra>
      <div class="addr-toolbar">
        <div class="rule-slot">
          <n-button v-show="ruleKind" size="small" tertiary @click="showRule = true">编辑规则</n-button>
        </div>
        <n-select v-model:value="subType" :options="typeOptions" size="small" style="width: 130px" />
      </div>
    </template>

    <div class="addr-label">
      <n-tag :bordered="false" size="small" type="success">Token 新地址</n-tag>
      <span>新客户端请使用此地址</span>
    </div>
    <n-input-group>
      <n-input-group-label>订阅地址</n-input-group-label>
      <n-input :value="mainUrl" readonly />
      <n-button @click="copy(mainUrl)">复制</n-button>
      <n-button @click="openQr(mainUrl)">二维码</n-button>
    </n-input-group>

    <div class="legacy-row">
      <div>
        <strong>旧地址兼容</strong>
        <span class="legacy-desc">仅为仍在使用 Base64 地址的客户端开启</span>
      </div>
      <n-space align="center">
        <span class="legacy-status">{{ legacy ? '已开启' : '已关闭' }}</span>
        <n-switch :value="legacy" :loading="legacyUpdating" @update:value="toggleLegacy" />
      </n-space>
    </div>

    <template v-if="legacy">
      <div class="addr-label">
        <n-tag :bordered="false" size="small" type="info">Base64 旧地址</n-tag>
        <span>用于兼容已部署的旧客户端</span>
      </div>
      <n-input-group>
        <n-input-group-label>旧版地址</n-input-group-label>
        <n-input :value="legacyUrl" readonly />
        <n-button @click="copy(legacyUrl)">复制</n-button>
      </n-input-group>
    </template>

    <qr-modal v-model:show="showQr" :text="qrText" />
    <rule-editor-modal v-if="ruleKind" v-model:show="showRule" :kind="ruleKind" />
  </n-card>
</template>

<style scoped>
.addr-card {
  margin-bottom: 18px;
}

/* 右侧下拉框位置固定，编辑规则按钮占位在左侧，切换格式时不再左右跳动 */
.addr-toolbar {
  align-items: center;
  display: flex;
  gap: 10px;
}

.rule-slot {
  align-items: center;
  display: flex;
  justify-content: flex-end;
  min-width: 72px;
}

.addr-label {
  align-items: center;
  display: flex;
  gap: 8px;
  margin: 12px 0 6px;
}

.addr-label span {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
}

.legacy-row {
  align-items: center;
  border-top: 1px solid var(--n-border-color, #eee);
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 14px;
}

.legacy-desc {
  color: var(--n-text-color-3, #8a8f98);
  display: block;
  font-size: 12px;
  margin-top: 2px;
}

.legacy-status {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 13px;
}
</style>
