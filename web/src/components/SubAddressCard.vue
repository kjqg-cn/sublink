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
  NCheckbox,
  NTag,
  NSpace
} from 'naive-ui'
import {
  setSubLegacy,
  subUrl,
  legacySubUrl,
  type SubType
} from '@/api'
import QrModal from './QrModal.vue'
import RuleEditorModal from './RuleEditorModal.vue'
import { copyText } from '@/utils/clipboard'

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
const singboxLegacy = ref(false)
const legacy = ref(props.legacyEnabled)
const legacyUpdating = ref(false)
const showQr = ref(false)
const qrText = ref('')
const showRule = ref(false)

watch(
  () => props.name,
  () => {
    legacy.value = props.legacyEnabled
    legacyUpdating.value = false
  }
)

watch(
  () => props.legacyEnabled,
  (v) => {
    legacy.value = v
  }
)

function appendQuery(url: string): string {
  if (subType.value === 'sing-box' && singboxLegacy.value) {
    return `${url}?legacy=1`
  }
  return url
}

// 有 token 用 token 地址，否则回退到 base64 旧地址编码。
const mainUrl = computed(() =>
  appendQuery(props.token ? subUrl(subType.value, props.token) : legacySubUrl(subType.value, props.name))
)
const legacyUrl = computed(() => appendQuery(legacySubUrl(subType.value, props.name)))

// clash/surge/sing-box 才有规则编辑。
const ruleKind = computed(() => (subType.value === 'v2ray' ? null : subType.value))

async function copy(text: string) {
  const ok = await copyText(text)
  message[ok ? 'success' : 'error'](ok ? '复制成功' : '复制失败')
}

function openQr(text: string) {
  qrText.value = text
  showQr.value = true
}

async function toggleLegacy(value: boolean) {
  if (legacyUpdating.value) return
  const targetName = props.name
  legacyUpdating.value = true
  try {
    const { code, msg } = await setSubLegacy(targetName, value)
    if (props.name !== targetName) return
    if (code === 200) {
      legacy.value = value
      emit('legacy-changed', value)
    } else {
      legacy.value = !value
      message.warning(msg)
    }
  } catch {
    if (props.name !== targetName) return
    legacy.value = !value
    message.warning('旧地址兼容状态保存失败，请刷新后重试')
  } finally {
    if (props.name === targetName) {
      legacyUpdating.value = false
    }
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
        <n-select v-model:value="subType" :options="typeOptions" size="small" style="width: 124px" />
      </div>
    </template>

    <div class="addr-label">
      <div class="addr-label-left">
        <n-tag :bordered="false" size="small" type="success">Token 地址</n-tag>
        <span>新客户端推荐使用</span>
      </div>
      <n-checkbox v-if="subType === 'sing-box'" v-model:checked="singboxLegacy" size="small">
        1.12～1.13 兼容 (?legacy=1)
      </n-checkbox>
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
        <span class="legacy-desc">仅为仍在使用 Base64 地址的旧客户端开启</span>
      </div>
      <n-space align="center">
        <span class="legacy-status">{{ legacy ? '已开启' : '已关闭' }}</span>
        <n-switch :value="legacy" :loading="legacyUpdating" @update:value="toggleLegacy" />
      </n-space>
    </div>

    <template v-if="legacy">
      <div class="addr-label">
        <div class="addr-label-left">
          <n-tag :bordered="false" size="small" type="info">Base64 旧地址</n-tag>
          <span>用于兼容已部署的旧客户端</span>
        </div>
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
  margin-bottom: 16px;
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
  flex-wrap: wrap;
  gap: 8px;
  justify-content: space-between;
  margin: 10px 0 6px;
}

.addr-label-left {
  align-items: center;
  display: flex;
  gap: 8px;
}

.addr-label-left span {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 13px;
}

.legacy-row {
  align-items: center;
  border-top: 1px solid var(--n-border-color, #eee);
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 14px;
}

.legacy-row strong {
  font-size: 14px;
  font-weight: 500;
}

.legacy-desc {
  color: var(--n-text-color-3, #8a8f98);
  display: block;
  font-size: 13px;
  margin-top: 3px;
}

.legacy-status {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 13px;
}
</style>
