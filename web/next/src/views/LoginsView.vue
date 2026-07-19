<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, NCard, NDataTable, type DataTableColumns } from 'naive-ui'
import { getAddress, type LoginRecord } from '@/api'

const message = useMessage()

const records = ref<LoginRecord[]>([])
const loading = ref(false)

const columns: DataTableColumns<LoginRecord> = [
  { title: '#', key: 'index', width: 60, render: (_row, i) => i + 1 },
  { title: 'IP 地址', key: 'ip', width: 180 },
  { title: '来源', key: 'address', ellipsis: { tooltip: true } },
  { title: '时间', key: 'time', width: 200, sorter: (a, b) => a.time.localeCompare(b.time) }
]

const pagination = { pageSize: 20 }

async function load() {
  loading.value = true
  try {
    records.value = await getAddress()
  } catch {
    message.error('加载登录记录失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <n-card title="登录记录">
    <n-data-table
      :columns="columns"
      :data="records"
      :loading="loading"
      :pagination="pagination"
      :bordered="false"
    />
  </n-card>
</template>
