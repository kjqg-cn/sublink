<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NCard, NInput, NButton, NForm, NFormItem } from 'naive-ui'
import { createSub } from '@/api'
import CodeTextarea from '@/components/CodeTextarea.vue'

const router = useRouter()
const message = useMessage()

const name = ref('')
const sub = ref('')
const saving = ref(false)

async function handleCreate() {
  if (!name.value.trim() || !sub.value.trim()) {
    message.warning('请填写订阅名称和节点')
    return
  }
  saving.value = true
  try {
    const { code, msg } = await createSub({
      name: name.value.trim(),
      node: sub.value.split('\n')
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      router.push('/subs')
    }
  } catch {
    message.error('创建订阅失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-card class="create-card" title="创建订阅">
    <n-form>
      <n-form-item label="订阅名称">
        <n-input
          v-model:value="name"
          placeholder="订阅名称（支持 emoji，最多 40 字）"
          :maxlength="40"
          show-count
        />
      </n-form-item>
      <n-form-item label="节点">
        <code-textarea
          v-model="sub"
          :rows="12"
          placeholder="订阅或节点，多个用回车分开；节点与备注用 | 分隔（节点链接含 | 可用 \| 转义，无 #名称 节点导出时自动用备注兜底）"
        />
      </n-form-item>
    </n-form>
    <n-button type="primary" :loading="saving" @click="handleCreate">创建订阅</n-button>
  </n-card>
</template>

<style scoped>
.create-card {
  margin: 0 auto;
  max-width: 720px;
}
</style>
