<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NCard, NInput, NButton, NForm, NFormItem } from 'naive-ui'
import { createSub, validateSubName } from '@/api'
import CodeTextarea from '@/components/CodeTextarea.vue'
import { DRAFT_NODES_STORAGE_KEY, storageGet, storageRemove } from '@/utils/storage'

const router = useRouter()
const message = useMessage()

const name = ref('')
const sub = ref('')
const saving = ref(false)

onMounted(() => {
  const draft = storageGet('session', DRAFT_NODES_STORAGE_KEY)
  if (draft) {
    sub.value = draft
    storageRemove('session', DRAFT_NODES_STORAGE_KEY)
  }
})

async function handleCreate() {
  if (saving.value) return
  const createdName = name.value.trim()
  if (!createdName || !sub.value.trim()) {
    message.warning('请填写订阅名称和节点')
    return
  }
  const nameErr = validateSubName(createdName)
  if (nameErr) {
    message.warning(nameErr)
    return
  }
  saving.value = true
  try {
    const { code, msg } = await createSub({
      name: createdName,
      node: sub.value.split('\n')
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      router.push({ path: '/subs', query: { sub: createdName } })
    }
  } catch {
    message.error('创建订阅失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-section">
    <p class="page-desc">
      填写订阅名称并粘贴节点或远程订阅链接，每行一条；节点后可用 <code>|备注</code> 补充兜底名称，创建成功后将自动定位至新订阅。
    </p>
    <n-card>
      <n-form>
        <n-form-item label="订阅名称">
          <n-input
            v-model:value="name"
            placeholder="订阅名称（支持 emoji，最多 40 字）"
            :maxlength="40"
            show-count
            style="max-width: 440px"
          />
        </n-form-item>
        <n-form-item label="节点与远程订阅">
          <code-textarea
            v-model="sub"
            :rows="12"
            placeholder="支持 vless/vmess/ss/ssr/trojan/hy/hy2 与 http(s) 远程订阅，多个用回车分开；节点含 | 可写作 \|"
          />
        </n-form-item>
      </n-form>
      <n-button type="primary" :loading="saving" @click="handleCreate">创建订阅</n-button>
    </n-card>
  </div>
</template>
