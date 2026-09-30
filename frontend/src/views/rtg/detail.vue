<template>
  <section class="page detail-page">
    <header class="page-head">
      <div>
        <h2>场桥调度明细</h2>
        <p class="page-desc">明细与列表读取同一份场桥记录，作业司机等字段保持一致。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" :to="backRoute">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="loading" class="inline-notice">正在读取场桥明细…</p>
    <div v-else-if="errorMessage" class="error-panel">
      <strong class="error-text">{{ errorMessage }}</strong>
      <button class="btn" type="button" @click="loadEntry">重试</button>
    </div>

    <table v-else-if="entry" class="data-table detail-table">
      <tbody>
        <tr v-for="field in fields" :key="field">
          <th>{{ field }}</th>
          <td>{{ displayValue(entry[field]) }}</td>
        </tr>
        <tr>
          <th>记录状态</th>
          <td>{{ displayValue(entry.status) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const route = useRoute()
const entry = ref<Row | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const fields = ['场桥编号', '场桥型号', '作业箱区', '跨距参数', '起升高度', '作业司机', '柴油油量', '场桥状态']

const backRoute = computed(() => {
  const backPath = route.query.back_path
  if (typeof backPath === 'string' && backPath.startsWith('/rtg')) {
    return backPath
  }
  return {
    path: '/rtg',
    query: {
      status: '在场',
      sort_by: '场桥编号',
      sort_order: 'asc',
      page: '1',
      size: '10',
    },
  }
})

function displayValue(value: Row[keyof Row] | undefined): string {
  return value === null || value === undefined || String(value).trim() === '' ? '—' : String(value)
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string }
    if (payload.detail) {
      return `场桥明细取数失败：${payload.detail}，请重试`
    }
  } catch {
    // 后端未返回可读 JSON 时使用兜底提示
  }
  return '场桥明细取数失败，请重试'
}

async function loadEntry() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`/api/rtg/${route.params.id}`)
    if (!response.ok) {
      throw new Error(await readError(response))
    }
    entry.value = (await response.json()) as Row
  } catch (error) {
    entry.value = null
    errorMessage.value = error instanceof Error ? error.message : '场桥明细取数失败，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadEntry)
</script>
