<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NCard, NCheckbox, NSpace, NSpin } from 'naive-ui'
import { getConfig, setConfig } from '@/api'

const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const config = ref({ udp: false, skipcert: false, emoji: false })

async function load() {
  loading.value = true
  try {
    const res = await getConfig()
    config.value = {
      udp: !!res.udp,
      skipcert: !!res.skipcert,
      emoji: !!res.emoji
    }
  } catch {
    message.error('加载设置失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const { code, msg } = await setConfig({ ...config.value })
    message[code === 200 ? 'success' : 'warning'](msg)
  } catch {
    message.error('保存设置失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-card class="settings-card" title="全局设置">
    <n-spin :show="loading || saving">
      <p class="settings-tip">修改后自动保存，作用于所有订阅生成。</p>
      <n-space vertical size="large">
        <n-checkbox v-model:checked="config.udp" @update:checked="save">开启 UDP</n-checkbox>
        <n-checkbox v-model:checked="config.skipcert" @update:checked="save">跳过证书验证</n-checkbox>
        <n-checkbox v-model:checked="config.emoji" @update:checked="save">emoji 入口国旗</n-checkbox>
      </n-space>
    </n-spin>
  </n-card>
</template>

<style scoped>
.settings-card {
  margin: 0 auto;
  max-width: 560px;
}

.settings-tip {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
  margin: 0 0 16px;
}
</style>
