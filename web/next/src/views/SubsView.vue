<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  useMessage,
  useDialog,
  useThemeVars,
  NButton,
  NIcon,
  NEmpty,
  NTag,
  NSpin,
  NModal,
  NInput,
  NForm,
  NFormItem
} from 'naive-ui'
import {
  getSubs,
  getSubByName,
  groupSubs,
  createNode,
  sortSubs,
  setSub,
  renameSub,
  delSub,
  type SubNode,
  type SubSummary
} from '@/api'
import NodeTable from '@/components/NodeTable.vue'
import SubAddressCard from '@/components/SubAddressCard.vue'
import CodeTextarea from '@/components/CodeTextarea.vue'

const message = useMessage()
const dialog = useDialog()
const themeVars = useThemeVars()

// 面板配色跟随明/暗主题，绑定成 CSS 变量供 <style> 使用。
const panelVars = computed(() => ({
  '--panel-bg': themeVars.value.cardColor,
  '--panel-border': themeVars.value.borderColor,
  '--panel-text': themeVars.value.textColor2,
  '--panel-text-3': themeVars.value.textColor3,
  '--panel-hover': themeVars.value.hoverColor,
  '--panel-active': themeVars.value.primaryColorSuppl
}))

const subs = ref<SubSummary[]>([])
const activeSub = ref('')
const nodes = ref<SubNode[]>([])
const loadingSubs = ref(false)
const loadingNodes = ref(false)

// 当前订阅的 token / legacy 状态从节点数据里取。
const activeToken = computed(() => nodes.value[0]?.access_token ?? '')
const activeLegacy = computed(() => nodes.value.some((n) => n.legacy_enabled))

const dragIndex = ref<number | null>(null)

// 新增节点弹窗
const showAddNode = ref(false)
const newNode = ref({ node: '', remarks: '' })
const savingNode = ref(false)

// 批量编辑弹窗
const showBatch = ref(false)
const batchText = ref('')
const savingBatch = ref(false)

// 重命名弹窗
const showRename = ref(false)
const renameText = ref('')
const savingRename = ref(false)

async function loadSubs() {
  loadingSubs.value = true
  try {
    const all = await getSubs()
    subs.value = groupSubs(all)
    // 与老版一致：初次加载不默认选中任何订阅，右侧保持空态，需用户手动点击列表项。
    // 仅当已选中的订阅不在最新列表里（被删除/重命名）时，清空选中回到空态。
    if (!subs.value.some((s) => s.name === activeSub.value)) {
      activeSub.value = ''
      nodes.value = []
    }
  } catch {
    message.error('加载订阅失败')
  } finally {
    loadingSubs.value = false
  }
}

async function selectSub(name: string) {
  activeSub.value = name
  loadingNodes.value = true
  try {
    nodes.value = await getSubByName(name)
  } catch {
    message.error('加载节点失败')
  } finally {
    loadingNodes.value = false
  }
}

async function refreshCurrent() {
  await selectSub(activeSub.value)
  await loadSubs()
}

// —— 拖拽排序（持久化到后端）——
function onDragStart(index: number) {
  dragIndex.value = index
}

function onDragEnd() {
  // 兜底：无论 drop 是否命中有效目标，拖拽结束都清理状态。
  dragIndex.value = null
}

async function onDrop(index: number) {
  const from = dragIndex.value
  dragIndex.value = null
  if (from === null || from === index) return
  const previous = [...subs.value]
  const list = [...subs.value]
  const [moved] = list.splice(from, 1)
  list.splice(index, 0, moved)
  subs.value = list
  try {
    const { code, msg } = await sortSubs(list.map((s) => s.name))
    if (code !== 200) {
      subs.value = previous
      message.warning(msg)
    }
  } catch {
    subs.value = previous
    message.warning('订阅排序保存失败，请刷新后重试')
  }
}

// —— 新增节点 ——
function openAddNode() {
  newNode.value = { node: '', remarks: '' }
  showAddNode.value = true
}

async function handleAddNode() {
  if (!newNode.value.node.trim()) {
    message.warning('请输入节点')
    return
  }
  savingNode.value = true
  try {
    const { code, msg } = await createNode({
      name: activeSub.value,
      node: newNode.value.node.trim(),
      remarks: newNode.value.remarks.trim()
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      showAddNode.value = false
      await refreshCurrent()
    }
  } catch {
    message.error('新增节点失败')
  } finally {
    savingNode.value = false
  }
}

// —— 批量编辑 ——
function openBatch() {
  batchText.value = nodes.value
    .map((n) => n.node + (n.remarks ? '|' + n.remarks : ''))
    .join('\n')
  showBatch.value = true
}

async function handleBatch() {
  savingBatch.value = true
  try {
    const { code, msg } = await setSub({
      name: activeSub.value,
      newNode: batchText.value.split('\n')
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      showBatch.value = false
      await refreshCurrent()
    }
  } catch {
    message.error('保存节点失败')
  } finally {
    savingBatch.value = false
  }
}

// —— 重命名 ——
function openRename() {
  renameText.value = activeSub.value
  showRename.value = true
}

async function handleRename() {
  const newName = renameText.value.trim()
  if (!newName || newName === activeSub.value) {
    showRename.value = false
    return
  }
  savingRename.value = true
  try {
    const { code, msg } = await renameSub(activeSub.value, newName)
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      showRename.value = false
      activeSub.value = newName
      await selectSub(newName)
      await loadSubs()
    }
  } catch {
    message.error('重命名失败')
  } finally {
    savingRename.value = false
  }
}

// —— 删除订阅 ——
function confirmDelSub() {
  const name = activeSub.value
  dialog.warning({
    title: '删除订阅',
    content: `删除后无法恢复，确定删除订阅“${name}”吗？`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const { code, msg } = await delSub(name)
        message[code === 200 ? 'success' : 'warning'](msg)
        if (code === 200) {
          activeSub.value = ''
          await loadSubs()
        }
      } catch {
        message.error('删除订阅失败')
      }
    }
  })
}

onMounted(() => loadSubs())
</script>

<template>
  <div class="subs-page" :style="panelVars">
    <aside class="sub-list-panel">
      <div class="panel-title">订阅列表 <span>拖动排序</span></div>
      <n-spin :show="loadingSubs">
        <div class="sub-list">
          <div
            v-for="(item, index) in subs"
            :key="item.name"
            class="sub-item"
            :class="{ active: activeSub === item.name }"
            draggable="true"
            @click="selectSub(item.name)"
            @dragstart="onDragStart(index)"
            @dragover.prevent
            @drop="onDrop(index)"
            @dragend="onDragEnd"
          >
            <n-icon class="drag-handle" :draggable="false">
              <svg viewBox="0 0 24 24" width="16" height="16">
                <path
                  fill="currentColor"
                  d="M9 5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm0 7a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm-1.5 8.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM18 5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm-1.5 8.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zm0 7a1.5 1.5 0 100-3 1.5 1.5 0 000 3z"
                />
              </svg>
            </n-icon>
            <span class="sub-name">{{ item.name }}</span>
            <n-tag size="small" :bordered="false" round>{{ item.count }}</n-tag>
          </div>
          <n-empty v-if="!loadingSubs && !subs.length" description="暂无订阅" style="padding: 24px 0" />
        </div>
      </n-spin>
    </aside>

    <section class="sub-detail">
      <template v-if="activeSub">
        <div class="detail-head">
          <div>
            <h2>{{ activeSub }}</h2>
            <span class="node-count">共 {{ nodes.length }} 个节点</span>
          </div>
          <div class="detail-actions">
            <n-button size="small" @click="openRename">重命名</n-button>
            <n-button size="small" type="error" secondary @click="confirmDelSub">删除订阅</n-button>
            <n-button size="small" @click="openBatch">批量编辑</n-button>
            <n-button size="small" type="primary" @click="openAddNode">新增节点</n-button>
          </div>
        </div>

        <sub-address-card
          :name="activeSub"
          :token="activeToken"
          :legacy-enabled="activeLegacy"
          @legacy-changed="refreshCurrent"
        />

        <node-table :nodes="nodes" :loading="loadingNodes" @refresh="refreshCurrent" />
      </template>
      <n-empty v-else description="选择左侧订阅查看节点" style="margin-top: 80px" />
    </section>

    <n-modal v-model:show="showAddNode" preset="card" title="新增节点" style="max-width: 560px">
      <n-form>
        <n-form-item :label="`订阅：${activeSub}`">
          <n-input
            v-model:value="newNode.node"
            type="textarea"
            :rows="6"
            placeholder="粘贴节点链接（vmess:// vless:// ss:// trojan:// 等）"
          />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="newNode.remarks" placeholder="可选备注" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="showAddNode = false">取消</n-button>
          <n-button type="primary" :loading="savingNode" @click="handleAddNode">确定</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal v-model:show="showBatch" preset="card" title="批量编辑节点" style="max-width: 760px">
      <p class="batch-tip">每行一个节点，节点和备注使用 | 分隔。此操作会整体覆盖该订阅的节点。</p>
      <code-textarea
        v-model="batchText"
        :rows="16"
        placeholder="节点多个用回车分开，每个节点最后带上 |备注"
      />
      <template #footer>
        <div class="modal-footer">
          <n-button @click="showBatch = false">取消</n-button>
          <n-button type="primary" :loading="savingBatch" @click="handleBatch">保存全部节点</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal v-model:show="showRename" preset="card" title="重命名订阅" style="max-width: 460px">
      <n-input v-model:value="renameText" placeholder="新的订阅名称" @keyup.enter="handleRename" />
      <template #footer>
        <div class="modal-footer">
          <n-button @click="showRename = false">取消</n-button>
          <n-button type="primary" :loading="savingRename" @click="handleRename">确定</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.subs-page {
  display: grid;
  gap: 20px;
  grid-template-columns: 240px 1fr;
  align-items: start;
}

.sub-list-panel {
  background: var(--panel-bg, #fff);
  border: 1px solid var(--panel-border, #eee);
  border-radius: 10px;
  padding: 12px;
}

.panel-title {
  align-items: center;
  color: var(--panel-text, #666);
  display: flex;
  font-size: 13px;
  font-weight: 600;
  justify-content: space-between;
  margin-bottom: 10px;
  padding: 0 4px;
}

.panel-title span {
  color: var(--panel-text-3, #8a8f98);
  font-size: 11px;
  font-weight: 400;
}

.sub-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sub-item {
  align-items: center;
  border-radius: 8px;
  color: var(--panel-text, inherit);
  cursor: pointer;
  display: flex;
  gap: 8px;
  padding: 9px 10px;
  transition: background 0.15s;
}

/* 子元素（尤其内联 SVG 图标）默认可拖拽，会与整行拖拽冲突导致拖拽会话卡死；
   统一禁止子元素单独发起拖拽，只允许整行 draggable。 */
.sub-item * {
  -webkit-user-drag: none;
  user-select: none;
}

.sub-item:hover {
  background: var(--panel-hover, rgba(99, 102, 241, 0.08));
}

.sub-item.active {
  background: rgba(99, 102, 241, 0.16);
  color: var(--panel-active, #6366f1);
}

.drag-handle {
  color: var(--panel-text-3, #b3b8c0);
  cursor: grab;
}

.sub-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sub-detail {
  min-width: 0;
}

.detail-head {
  align-items: flex-end;
  display: flex;
  justify-content: space-between;
  margin-bottom: 18px;
}

.detail-head h2 {
  margin: 0;
}

.node-count {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 13px;
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.batch-tip {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 12px;
  margin: 0 0 10px;
}

.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
</style>
