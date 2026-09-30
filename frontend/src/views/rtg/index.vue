<template>
  <section class="page" data-module="rtg">
    <header class="page-head">
      <div>
        <h2>场桥调度管理</h2>
        <p class="page-desc">按作业箱区查询在场场桥，筛选、排列和页码会保留；从明细返回时回到原来的位置。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记场桥</button>
        <button class="btn" type="button" @click="exportRows">导出场桥调度清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="submitQuery">
      <label class="filter-item">
        <span>作业箱区</span>
        <input v-model.trim="yardBlockInput" placeholder="如 A01（全角Ａ０１也可）" />
      </label>
      <label class="filter-item">
        <span>场桥范围</span>
        <select v-model="statusInput">
          <option value="在场">在场场桥</option>
          <option value="">全部场桥</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>排列方式</span>
        <select v-model="sortInput">
          <option v-for="option in sortOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="filter-item">
        <span>排列顺序</span>
        <select v-model="orderInput">
          <option value="asc">升序</option>
          <option value="desc">降序</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="queryNotice" class="inline-notice">{{ queryNotice }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink
              v-if="column === '场桥编号'"
              class="detail-link"
              :to="detailRoute(row.id)"
              @click="rememberPosition"
            >
              {{ row[column] ?? '—' }}
            </RouterLink>
            <template v-else>{{ displayValue(row[column]) }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length && !loading">
          <td :colspan="columns.length + 1" class="empty-state">没有符合当前条件的场桥</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot list-foot">
      <div class="pager">
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goToPage(page - 1)">
          上一页
        </button>
        <span>第 {{ page }} / {{ totalPages }} 页，共 {{ total }} 条</span>
        <button
          class="btn"
          type="button"
          :disabled="page >= totalPages || loading"
          @click="goToPage(page + 1)"
        >
          下一页
        </button>
        <label class="page-size">
          每页
          <select v-model.number="sizeInput" @change="changePageSize">
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
          </select>
          条
        </label>
      </div>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button class="link retry-link" type="button" @click="reload({ force: true })">重试</button>
      </span>
      <span v-else-if="reportMessage" class="error-text">
        {{ reportMessage }}
        <button class="link retry-link" type="button" @click="loadReport(true)">重试</button>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Report = {
  total: number
  on_site_total: number
  empty_span_total: number
  status_counts: Record<string, number>
}

const ENDPOINT = '/api/rtg'
const PAGE_SIZE = 10
const RETURN_POSITION_KEY = 'rtg-list-return-position'
const columns = ['场桥编号', '场桥型号', '作业箱区', '跨距参数', '起升高度', '作业司机', '柴油油量', '场桥状态'] as const
const sortOptions = [
  { label: '按场桥编号', value: '场桥编号' },
  { label: '按作业司机', value: '作业司机' },
  { label: '按作业箱区', value: '作业箱区' },
  { label: '按跨距参数', value: '跨距参数' },
  { label: '按场桥状态', value: '场桥状态' },
]
const actions = ['分配作业', '释放场桥', '登记检修']
const statuses = ['空闲', '作业中', '检修中', '停用']

const route = useRoute()
const router = useRouter()
const rows = ref<Row[]>([])
const report = ref<Report | null>(null)
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const errorMessage = ref('')
const reportMessage = ref('')
const queryNotice = ref('')
const yardBlockInput = ref('')
const statusInput = ref('在场')
const sortInput = ref('场桥编号')
const orderInput = ref('asc')
const sizeInput = ref(PAGE_SIZE)

const totalPages = computed(() => Math.max(Math.ceil(total.value / sizeInput.value), 1))
const stats = computed(() => {
  if (loading.value && !rows.value.length) {
    return [
      { label: '查询台数', value: '—' },
      { label: '报表台数', value: '—' },
      { label: '台数核对', value: '—' },
      { label: '跨距未填', value: '—' },
    ]
  }
  return [
    { label: '查询台数', value: total.value },
    { label: '报表台数', value: report.value?.total ?? '—' },
    { label: '台数核对', value: report.value && report.value.total === total.value ? '一致' : '不一致' },
    { label: '跨距未填', value: report.value?.empty_span_total ?? '—' },
  ]
})

function queryValue(value: unknown): string {
  return Array.isArray(value) ? String(value[0] ?? '') : String(value ?? '')
}

function normalizeQuery(value: string): string {
  return value.normalize('NFKC').replace(/\s+/g, '').toLowerCase()
}

function syncInputsFromRoute() {
  yardBlockInput.value = queryValue(route.query.yard_block)
  statusInput.value = queryValue(route.query.status) || '在场'
  sortInput.value = queryValue(route.query.sort_by) || '场桥编号'
  orderInput.value = queryValue(route.query.sort_order) === 'desc' ? 'desc' : 'asc'
  page.value = Math.max(Number.parseInt(queryValue(route.query.page), 10) || 1, 1)
  sizeInput.value = Math.min(Math.max(Number.parseInt(queryValue(route.query.size), 10) || PAGE_SIZE, 1), 200)
}

function queryKey(forReport = false): string {
  const params = new URLSearchParams()
  const yardBlock = normalizeQuery(yardBlockInput.value)
  if (yardBlock) {
    params.set('yard_block', yardBlock)
  }
  if (statusInput.value) {
    params.set('status', normalizeQuery(statusInput.value))
  }
  if (!forReport) {
    params.set('sort_by', sortInput.value)
    params.set('sort_order', orderInput.value)
    params.set('page', String(page.value))
    params.set('size', String(sizeInput.value))
  }
  return params.toString()
}

function buildQueryString(forReport = false): string {
  return queryKey(forReport)
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string }
    if (payload.detail) {
      return `${fallback}：${payload.detail}，请重试`
    }
  } catch {
    // 后端未返回可读 JSON 时使用兜底提示
  }
  return `${fallback}，请重试`
}

let activeListToken = 0
let activeListKey = ''
let loadedListKey = ''

async function loadList(force = false) {
  const key = queryKey()
  if (!force && (activeListKey === key || loadedListKey === key)) {
    queryNotice.value = '相同查询条件已生效，无需重复提交'
    window.setTimeout(() => {
      queryNotice.value = ''
    }, 1800)
    return
  }

  const token = ++activeListToken
  activeListKey = key
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQueryString()}`)
    if (!response.ok) {
      throw new Error(await readError(response, '场桥调度列表取数失败'))
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    if (token !== activeListToken) {
      return
    }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    loadedListKey = key
  } catch (error) {
    if (token === activeListToken) {
      errorMessage.value = error instanceof Error ? error.message : '场桥调度列表取数失败，请重试'
    }
  } finally {
    if (token === activeListToken) {
      activeListKey = ''
      loading.value = false
    }
  }
}

let activeReportKey = ''

async function loadReport(force = false) {
  const key = queryKey(true)
  if (!force && activeReportKey === key) {
    return
  }
  activeReportKey = key
  reportMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/report?${buildQueryString(true)}`)
    if (!response.ok) {
      throw new Error(await readError(response, '场桥报表取数失败'))
    }
    report.value = (await response.json()) as Report
  } catch (error) {
    report.value = null
    reportMessage.value = error instanceof Error ? error.message : '场桥报表取数失败，请重试'
  }
}

async function reload(options: { force?: boolean } = {}) {
  await Promise.all([loadList(options.force), loadReport(options.force)])
}

async function navigateWithQuery(query: Record<string, string | number>) {
  await router.push({ path: ENDPOINT, query })
}

async function submitQuery() {
  const query: Record<string, string | number> = {
    sort_by: sortInput.value,
    sort_order: orderInput.value,
    page: 1,
    size: sizeInput.value,
  }
  if (yardBlockInput.value.trim()) {
    query.yard_block = yardBlockInput.value.trim()
  }
  if (statusInput.value) {
    query.status = statusInput.value
  }
  await navigateWithQuery(query)
}

async function resetFilters() {
  yardBlockInput.value = ''
  statusInput.value = '在场'
  sortInput.value = '场桥编号'
  orderInput.value = 'asc'
  sizeInput.value = PAGE_SIZE
  await navigateWithQuery({ status: '在场', sort_by: '场桥编号', sort_order: 'asc', page: 1, size: PAGE_SIZE })
}

async function goToPage(nextPage: number) {
  const targetPage = Math.min(Math.max(nextPage, 1), totalPages.value)
  if (targetPage === page.value) {
    return
  }
  const query: Record<string, string | number> = {
    sort_by: sortInput.value,
    sort_order: orderInput.value,
    page: targetPage,
    size: sizeInput.value,
  }
  if (yardBlockInput.value.trim()) {
    query.yard_block = yardBlockInput.value.trim()
  }
  if (statusInput.value) {
    query.status = statusInput.value
  }
  await navigateWithQuery(query)
}

async function changePageSize() {
  await goToPage(1)
}

function detailRoute(id: Row['id']) {
  return {
    name: 'rtg-detail',
    params: { id: String(id) },
    query: { back_path: route.fullPath },
  }
}

function rememberPosition() {
  sessionStorage.setItem(RETURN_POSITION_KEY, String(window.scrollY))
}

function displayValue(value: Row[keyof Row]): string {
  return value === null || value === undefined || String(value).trim() === '' ? '—' : String(value)
}

function openCreate() {
  errorMessage.value = '场桥登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as { ok?: boolean; message?: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '场桥调度动作未生效，请重试')
    }
    loadedListKey = ''
    activeReportKey = ''
    await reload({ force: true })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场桥调度操作失败，请重试'
  }
}

async function exportRows() {
  try {
    const response = await request(`${ENDPOINT}/export?${buildQueryString()}`)
    if (!response.ok) {
      throw new Error(await readError(response, '场桥报表取数失败'))
    }
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '场桥调度清单.json'
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    reportMessage.value = error instanceof Error ? error.message : '场桥报表取数失败，请重试'
  }
}

watch(
  () => route.fullPath,
  () => {
    if (route.name !== 'rtg') {
      return
    }
    syncInputsFromRoute()
    void reload()
  },
)

onMounted(async () => {
  syncInputsFromRoute()
  if (route.path === ENDPOINT && !Object.keys(route.query).length) {
    await router.replace({ path: ENDPOINT, query: { status: '在场', sort_by: '场桥编号', sort_order: 'asc', page: 1, size: PAGE_SIZE } })
    return
  }
  await reload()
  window.requestAnimationFrame(() => {
    const top = Number(sessionStorage.getItem(RETURN_POSITION_KEY) ?? 0)
    if (top > 0) {
      window.scrollTo({ top })
      sessionStorage.removeItem(RETURN_POSITION_KEY)
    }
  })
})

onBeforeRouteLeave(() => {
  activeListToken += 1
})
</script>
