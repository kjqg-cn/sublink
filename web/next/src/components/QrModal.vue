<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { NModal } from 'naive-ui'
import QRCode from 'qrcode'

const props = defineProps<{ show: boolean; text: string }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const canvas = ref<HTMLCanvasElement | null>(null)

// 监听弹窗状态、文本以及 canvas 引用挂载，确保首次打开即可稳定渲染二维码。
watch(
  [() => props.show, () => props.text, canvas],
  async ([show, text, canvasEl]) => {
    if (!show || !text) return
    await nextTick()
    const target = canvasEl ?? canvas.value
    if (target) {
      QRCode.toCanvas(target, text, { width: 240, margin: 1 }).catch(() => {})
    }
  },
  { immediate: true, flush: 'post' }
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
