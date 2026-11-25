<script setup lang="ts">
import { h, onMounted, reactive, ref } from 'vue'
import { useMessage, NCard, NDataTable, NButton, NTag, type DataTableColumns } from 'naive-ui'
import { getAddress, type LoginRecord } from '@/api'

const message = useMessage()

const records = ref<LoginRecord[]>([])
const loading = ref(false)

const pagination = reactive({
  page: 1,
  pageSize: 20,
  onChange: (page: number) => {
    pagination.page = page
  }
})

const columns: DataTableColumns<LoginRecord> = [
  {
    title: '#',
    key: 'index',
    width: 64,
    render: (_row, i) => (pagination.page - 1) * pagination.pageSize + i + 1
  },
  { title: 'IP 地址', key: 'ip', width: 360, ellipsis: { tooltip: true } },
  {
    title: '来源地区',
    key: 'address',
    minWidth: 180,
    ellipsis: { tooltip: true },
    render: (row) => row.address || h('span', { style: { color: 'var(--n-text-color-disabled)' } }, '—')
  },
  {
    title: '登录时间',
    key: 'time',
    width: 196,
    sorter: (a, b) => a.time.localeCompare(b.time)
  }
]

async function load() {
  loading.value = true
  try {
    records.value = await getAddress()
    pagination.page = 1
  } catch {
    message.error('加载登录记录失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-section">
    <p class="page-desc">记录后台管理员登录来源 IP 与时间，系统默认自动保留最近 500 条记录。</p>
    <n-card size="small">
      <template #header>
        <div class="logins-head">
          <span>审计明细</span>
          <n-tag size="small" :bordered="false" round>共 {{ records.length }} 条</n-tag>
        </div>
      </template>
      <template #header-extra>
        <n-button size="small" tertiary :loading="loading" @click="load">刷新</n-button>
      </template>

      <n-data-table
        :columns="columns"
        :data="records"
        :loading="loading"
        :pagination="pagination"
        :scroll-x="800"
        :bordered="false"
        size="small"
      />
    </n-card>
  </div>
</template>

<style scoped>
.logins-head {
  align-items: center;
  display: flex;
  font-size: 15px;
  font-weight: 600;
  gap: 8px;
}
</style>
