<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NCard, NCheckbox, NSpace, NSpin, NTooltip, NIcon } from 'naive-ui'
import { getConfig, setConfig, type GlobalConfig } from '@/api'

const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const config = ref<GlobalConfig>({
  udp: false,
  skipcert: false,
  emoji: false,
  custom: false,
  custom_loopback: false,
  custom_node_name: false
})

async function load() {
  loading.value = true
  try {
    const res = await getConfig()
    config.value = {
      udp: !!res.udp,
      skipcert: !!res.skipcert,
      emoji: !!res.emoji,
      custom: !!res.custom,
      custom_loopback: !!res.custom_loopback,
      custom_node_name: !!res.custom_node_name
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

onMounted(() => {
  load()
})
</script>

<template>
  <n-card class="settings-card" title="全局设置">
    <n-spin :show="loading || saving">
      <p class="settings-tip">修改后自动保存，作用于所有订阅生成。</p>
      <n-space vertical size="large">
        <div class="setting-item">
          <n-checkbox v-model:checked="config.udp" @update:checked="save">开启 UDP</n-checkbox>
          <n-tooltip trigger="hover" :style="{ maxWidth: '340px' }">
            <template #trigger>
              <n-icon class="help-icon" :size="16">
                <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
              </n-icon>
            </template>
            <span>控制导出的客户端配置（如 Clash 的 udp: true、Surge 的 udp-relay）。开启后客户端才会向节点发送 UDP 流量（用于游戏、语音通话及 QUIC 等）；若关闭，客户端将在本地禁止该节点的 UDP 转发。</span>
          </n-tooltip>
        </div>

        <div class="setting-item">
          <n-checkbox v-model:checked="config.skipcert" @update:checked="save">跳过证书验证</n-checkbox>
          <n-tooltip trigger="hover" :style="{ maxWidth: '340px' }">
            <template #trigger>
              <n-icon class="help-icon" :size="16">
                <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
              </n-icon>
            </template>
            <span>在客户端配置中跳过 TLS 证书合法性校验（skip-cert-verify）。可解决自签名证书或域名不匹配导致的连接失败，但会降低传输安全性。</span>
          </n-tooltip>
        </div>

        <div class="setting-item">
          <n-checkbox v-model:checked="config.emoji" @update:checked="save">emoji 入口国旗</n-checkbox>
          <n-tooltip trigger="hover" :style="{ maxWidth: '340px' }">
            <template #trigger>
              <n-icon class="help-icon" :size="16">
                <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
              </n-icon>
            </template>
            <span>根据节点服务器 IP 自动查询地理位置并在节点名称前添加对应国旗 Emoji。注意：节点较多时会因请求外部 IP 接口增加订阅生成耗时。</span>
          </n-tooltip>
        </div>

        <div class="setting-item">
          <n-checkbox v-model:checked="config.custom" @update:checked="save">开启自定义功能</n-checkbox>
          <n-tooltip trigger="hover" :style="{ maxWidth: '320px' }">
            <template #trigger>
              <n-icon class="help-icon" :size="16">
                <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
              </n-icon>
            </template>
            <span>该功能为作者定制规则，仅在拉取远程订阅时生效。如不了解具体逻辑，请保持关闭。</span>
          </n-tooltip>
        </div>

        <div v-if="config.custom" class="sub-settings-block">
          <n-space vertical size="medium">
            <div class="setting-item">
              <n-checkbox v-model:checked="config.custom_loopback" @update:checked="save">回环地址与端口重写</n-checkbox>
              <n-tooltip trigger="hover" :style="{ maxWidth: '340px' }">
                <template #trigger>
                  <n-icon class="help-icon" :size="16">
                    <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
                  </n-icon>
                </template>
                <span>将远程订阅中地址为 127.0.0.1 的节点服务器自动替换为订阅域名，并将端口强制改为 443（适用于通过本地隧道回环中转的场景）。</span>
              </n-tooltip>
            </div>
            <div class="setting-item">
              <n-checkbox v-model:checked="config.custom_node_name" @update:checked="save">节点名称与国旗重写</n-checkbox>
              <n-tooltip trigger="hover" :style="{ maxWidth: '340px' }">
                <template #trigger>
                  <n-icon class="help-icon" :size="16">
                    <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
                  </n-icon>
                </template>
                <span>识别以“🇭🇰【香港”开头且带有 SG/TYO/LAX 等地区代号的中转节点，自动修正为对应落地国家的国旗与城市名称（如新加坡、东京等）；若远程订阅域名/目标为 IPv6，自动将线路标识标记为 IPv6。</span>
              </n-tooltip>
            </div>
          </n-space>
        </div>
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

.setting-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  color: var(--n-text-color-3, #8a8f98);
  cursor: help;
  display: inline-flex;
  align-items: center;
  transition: color 0.2s ease;
}

.help-icon:hover {
  color: var(--n-text-color-1, #1f2225);
}

.sub-settings-block {
  padding-left: 24px;
}
</style>
