<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NAlert, NButton, NCard, NSwitch, NSpin } from 'naive-ui'
import { getConfig, setConfig, type GlobalConfig } from '@/api'

const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const loadFailed = ref(false)
const config = ref<GlobalConfig>({
  udp: false,
  skipcert: false,
  emoji: false,
  hy2_pin_fallback: false,
  custom: false,
  custom_loopback: false,
  custom_node_name: false
})

async function load() {
  loading.value = true
  loadFailed.value = false
  try {
    const res = await getConfig()
    config.value = {
      udp: !!res.udp,
      skipcert: !!res.skipcert,
      emoji: !!res.emoji,
      hy2_pin_fallback: !!res.hy2_pin_fallback,
      custom: !!res.custom,
      custom_loopback: !!res.custom_loopback,
      custom_node_name: !!res.custom_node_name
    }
  } catch {
    loadFailed.value = true
    message.error('加载设置失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (loading.value || saving.value || loadFailed.value) return
  saving.value = true
  try {
    const { code, msg } = await setConfig({ ...config.value })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code !== 200) {
      await load()
    }
  } catch {
    message.error('保存设置失败')
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="page-section">
    <p class="page-desc">
      所有开关修改后自动保存，实时作用于 V2Ray / Clash / Surge / sing-box 订阅生成。
    </p>
    <n-alert v-if="loadFailed" type="error" :bordered="false" style="margin-bottom: 16px">
      <div class="load-error-row">
        <span>全局设置读取失败，已禁用开关操作以防覆盖原有配置</span>
        <n-button size="small" secondary type="error" :disabled="loading" @click="load">
          重新加载
        </n-button>
      </div>
    </n-alert>
    <n-spin :show="loading || saving">
      <div class="settings-stack">
        <n-card size="small" title="基础导出选项">
          <div class="setting-row">
            <div class="setting-copy">
              <div class="setting-title">开启 UDP</div>
              <div class="setting-desc">
                控制导出配置中的 UDP 转发开关（如 Clash 的 udp: true、Surge 的 udp-relay），适用于游戏、语音与 QUIC 流量。
              </div>
            </div>
            <n-switch
              v-model:value="config.udp"
              :disabled="loading || saving || loadFailed"
              @update:value="save"
            />
          </div>

          <div class="setting-row">
            <div class="setting-copy">
              <div class="setting-title">跳过证书验证</div>
              <div class="setting-desc">
                导出配置开启 skip-cert-verify，用于兼容自签名证书或域名不匹配节点，会降低传输安全性。
              </div>
            </div>
            <n-switch
              v-model:value="config.skipcert"
              :disabled="loading || saving || loadFailed"
              @update:value="save"
            />
          </div>

          <div class="setting-row">
            <div class="setting-copy">
              <div class="setting-title">sing-box 兼容 Hysteria2 指纹节点</div>
              <div class="setting-desc">
                sing-box 稳定版暂不支持整证书 pinSHA256 校验；开启后仅将带 pinSHA256 的 Hysteria2 节点在 sing-box 导出时自动设为 insecure: true（会降低对应节点的防中间人校验，也支持通过订阅链接附加 ?hy2_pin_fallback=1 按需开启）。
              </div>
            </div>
            <n-switch
              v-model:value="config.hy2_pin_fallback"
              :disabled="loading || saving || loadFailed"
              @update:value="save"
            />
          </div>

          <div class="setting-row">
            <div class="setting-copy">
              <div class="setting-title">Emoji 入口国旗</div>
              <div class="setting-desc">
                按节点服务器 IP 自动查询地理位置并在名称前补国旗 Emoji；节点较多时会增加首次订阅生成耗时。
              </div>
            </div>
            <n-switch
              v-model:value="config.emoji"
              :disabled="loading || saving || loadFailed"
              @update:value="save"
            />
          </div>
        </n-card>

        <n-card size="small" title="远程订阅自定义重写">
          <div class="setting-row">
            <div class="setting-copy">
              <div class="setting-title">开启自定义功能</div>
              <div class="setting-desc">
                仅在展开 HTTP/HTTPS 远程订阅时生效，用于定制中转回环地址替换与落地节点改名；如不使用请保持关闭。
              </div>
            </div>
            <n-switch
              v-model:value="config.custom"
              :disabled="loading || saving || loadFailed"
              @update:value="save"
            />
          </div>

          <div v-if="config.custom" class="sub-rows">
            <div class="setting-row">
              <div class="setting-copy">
                <div class="setting-title">回环地址与端口重写</div>
                <div class="setting-desc">
                  将远程订阅中地址为 127.0.0.1 的节点自动替换为订阅域名，并将端口改为目标端口（默认 443，可通过环境变量覆盖）。
                </div>
              </div>
              <n-switch
                v-model:value="config.custom_loopback"
                :disabled="loading || saving || loadFailed"
                @update:value="save"
              />
            </div>

            <div class="setting-row">
              <div class="setting-copy">
                <div class="setting-title">节点名称与国旗重写</div>
                <div class="setting-desc">
                  识别中转前缀及地区代号（如 -SG/-TYO/-LAX）自动修正落地国旗与城市名称，远程订阅为 IPv6 目标时自动延续 IPv6 标识。
                </div>
              </div>
              <n-switch
                v-model:value="config.custom_node_name"
                :disabled="loading || saving || loadFailed"
                @update:value="save"
              />
            </div>
          </div>
        </n-card>
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.load-error-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: space-between;
}

.settings-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.setting-row {
  align-items: center;
  border-top: 1px solid var(--n-border-color, #eee);
  display: flex;
  gap: 20px;
  justify-content: space-between;
  padding: 14px 0;
}

.setting-row:first-child {
  border-top: none;
  padding-top: 4px;
}

.setting-row:last-child {
  padding-bottom: 4px;
}

.setting-copy {
  flex: 1;
  max-width: 760px;
  min-width: 0;
}

.setting-title {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
}

.setting-desc {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 13px;
  line-height: 1.55;
  margin-top: 3px;
}

.sub-rows {
  border-top: 1px solid var(--n-border-color, #eee);
  margin-top: 4px;
  padding-left: 20px;
}

.sub-rows .setting-row:first-child {
  padding-top: 14px;
}
</style>
