<script setup lang="ts">
import { computed, ref } from 'vue'
import { useThemeVars } from 'naive-ui'

const props = withDefaults(
  defineProps<{ modelValue: string; rows?: number; placeholder?: string; readonly?: boolean }>(),
  { rows: 12, placeholder: '', readonly: false }
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const LINE_HEIGHT = 20.8 // 13px * 1.6
const PADDING_Y = 16 // 上下各 8px

const themeVars = useThemeVars()
const gutter = ref<HTMLDivElement | null>(null)

// 行号根据内容行数生成，至少铺满可视高度。
const lineCount = computed(() => Math.max(props.modelValue.split('\n').length, 1))
const lines = computed(() => Array.from({ length: lineCount.value }, (_, i) => i + 1))

// 容器固定高度（由 rows 决定），超出内容由文本域内部滚动。
const boxHeight = computed(() => `${props.rows * LINE_HEIGHT + PADDING_Y}px`)

const wrapVars = computed(() => ({
  '--code-bg': themeVars.value.inputColor,
  '--code-border': themeVars.value.borderColor,
  '--code-text': themeVars.value.textColor1,
  '--code-gutter-text': themeVars.value.textColor3,
  '--code-gutter-bg': themeVars.value.actionColor,
  height: boxHeight.value
}))

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

// 文本域滚动时同步行号列。
function onScroll(e: Event) {
  if (gutter.value) gutter.value.scrollTop = (e.target as HTMLTextAreaElement).scrollTop
}
</script>

<template>
  <div class="code-textarea" :style="wrapVars">
    <div ref="gutter" class="gutter">
      <div v-for="n in lines" :key="n" class="gutter-line">{{ n }}</div>
    </div>
    <textarea
      class="editor"
      :value="modelValue"
      :placeholder="placeholder"
      :readonly="readonly"
      spellcheck="false"
      wrap="off"
      @input="onInput"
      @scroll="onScroll"
    />
  </div>
</template>

<style scoped>
.code-textarea {
  background: var(--code-bg, #fff);
  border: 1px solid var(--code-border, #e0e0e6);
  border-radius: 6px;
  display: flex;
  overflow: hidden;
  width: 100%;
}

.gutter {
  background: var(--code-gutter-bg, #f5f5f7);
  border-right: 1px solid var(--code-border, #e0e0e6);
  box-sizing: border-box;
  color: var(--code-gutter-text, #b0b3bd);
  flex: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  height: 100%;
  line-height: 1.6;
  overflow: hidden;
  padding: 8px 8px 8px 10px;
  text-align: right;
  user-select: none;
}

.gutter-line {
  min-width: 22px;
}

.editor {
  background: transparent;
  border: none;
  box-sizing: border-box;
  color: var(--code-text, #333);
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  height: 100%;
  line-height: 1.6;
  outline: none;
  overflow: auto;
  padding: 8px 10px;
  resize: none;
  white-space: pre;
}
</style>
