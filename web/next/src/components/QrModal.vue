<script setup lang="ts">
import { ref, watch } from 'vue'
import { NModal } from 'naive-ui'
import QRCode from 'qrcode'

const props = defineProps<{ show: boolean; text: string }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const canvas = ref<HTMLCanvasElement | null>(null)

// 弹窗打开且拿到 canvas 后再渲染二维码。
watch(
  () => [props.show, props.text] as const,
  async ([show, text]) => {
    if (!show || !text) return
    await Promise.resolve()
    if (canvas.value) {
      QRCode.toCanvas(canvas.value, text, { width: 240, margin: 1 }).catch(() => {})
    }
  }
)
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    title="订阅二维码"
    style="max-width: 320px"
    @update:show="emit('update:show', $event)"
  >
    <div class="qr-body">
      <canvas ref="canvas" />
      <p class="qr-text">{{ text }}</p>
    </div>
  </n-modal>
</template>

<style scoped>
.qr-body {
  align-items: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.qr-text {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
  margin: 0;
  text-align: center;
  word-break: break-all;
}
</style>
