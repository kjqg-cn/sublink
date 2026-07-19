<script setup lang="ts">
import { ref } from 'vue'
import { useMessage, NCard, NButton } from 'naive-ui'
import { decodeSub } from '@/api'
import CodeTextarea from '@/components/CodeTextarea.vue'

const message = useMessage()

const input = ref('')
const output = ref('')
const parsing = ref(false)

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
      output.value = msg.join('\n')
    } else {
      message.error(String(msg))
    }
  } catch {
    message.error('解析失败')
  } finally {
    parsing.value = false
  }
}
</script>

<template>
  <n-card class="parse-card" title="订阅解析">
    <p class="parse-tip">仅支持 base64 编码的订阅，多条用回车分开。</p>
    <code-textarea v-model="input" :rows="8" placeholder="粘贴订阅链接" />
    <n-button
      type="primary"
      :loading="parsing"
      style="margin: 14px 0"
      @click="handleParse"
    >
      解析
    </n-button>
    <code-textarea
      v-if="output"
      :model-value="output"
      :rows="10"
      readonly
      placeholder="解析结果"
    />
  </n-card>
</template>

<style scoped>
.parse-card {
  margin: 0 auto;
  max-width: 720px;
}

.parse-tip {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
  margin: 0 0 12px;
}
</style>
