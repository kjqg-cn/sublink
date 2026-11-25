<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NCard, NButton, NSpace, NTag } from 'naive-ui'
import { decodeSub } from '@/api'
import CodeTextarea from '@/components/CodeTextarea.vue'
import { copyText } from '@/utils/clipboard'
import { DRAFT_NODES_STORAGE_KEY, storageSet } from '@/utils/storage'

const router = useRouter()
const message = useMessage()

const input = ref('')
const parsedList = ref<string[]>([])
const parsing = ref(false)

const output = computed(() => parsedList.value.join('\n'))

async function handleParse() {
  const matches = input.value.match(/(http|https):\/\/[^\s]+/g)
  if (!matches) {
    message.error('格式不正确，请粘贴 http(s) 订阅链接')
    return
  }
  parsing.value = true
  try {
    const { code, msg } = await decodeSub(matches)
    if (code === 200) {
      parsedList.value = msg
      message.success(`成功解析 ${msg.length} 条节点`)
    } else {
      message.error(String(msg))
    }
  } catch {
    message.error('解析失败')
  } finally {
    parsing.value = false
  }
}

async function copyResult() {
  if (!output.value) return
  const ok = await copyText(output.value)
  message[ok ? 'success' : 'error'](ok ? '已复制全部节点' : '复制失败')
}

function createSubFromResult() {
  if (!parsedList.value.length) return
  // 对含 \ 或 | 的原始节点做对称转义，防止提交 /create_sub 时被误拆为节点与备注。
  const escapedDraft = parsedList.value
    .map((line) => line.replace(/\\/g, '\\\\').replace(/\|/g, '\\|'))
    .join('\n')
  if (!storageSet('session', DRAFT_NODES_STORAGE_KEY, escapedDraft)) {
    message.warning('解析结果过大或浏览器禁用存储，请点击「复制全部」后手动粘贴创建')
    return
  }
  router.push('/subs/create')
}

function clearResult() {
  parsedList.value = []
}
</script>

<template>
  <div class="page-section">
    <p class="page-desc">
      粘贴 Base64 编码的远程订阅链接（支持多条，每行一个，单次最多 20 条），快速展开为明文节点列表。
    </p>
    <n-card>
      <code-textarea v-model="input" :rows="7" placeholder="粘贴 http(s):// 远程订阅链接" />
      <div class="parse-actions">
        <n-button type="primary" :loading="parsing" @click="handleParse">开始解析</n-button>
        <n-button v-if="input" quaternary @click="input = ''">清空输入</n-button>
      </div>

      <template v-if="parsedList.length > 0">
        <div class="result-bar">
          <div class="result-title">
            <span>解析结果</span>
            <n-tag size="small" :bordered="false" type="success" round>
              共 {{ parsedList.length }} 条节点
            </n-tag>
          </div>
          <n-space :size="8">
            <n-button size="small" @click="copyResult">复制全部</n-button>
            <n-button size="small" type="primary" secondary @click="createSubFromResult">
              以此创建订阅
            </n-button>
            <n-button size="small" quaternary @click="clearResult">清空</n-button>
          </n-space>
        </div>
        <code-textarea
          :model-value="output"
          :rows="11"
          readonly
          placeholder="解析结果"
        />
      </template>
    </n-card>
  </div>
</template>

<style scoped>
.parse-actions {
  display: flex;
  gap: 8px;
  margin: 14px 0 4px;
}

.result-bar {
  align-items: center;
  border-top: 1px solid var(--n-border-color, #eee);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: space-between;
  margin: 18px 0 10px;
  padding-top: 16px;
}

.result-title {
  align-items: center;
  display: flex;
  font-size: 15px;
  font-weight: 600;
  gap: 8px;
}
</style>
