<template>
  <section class="page" data-module="rtg">
    <header class="page-head">
      <div>
        <h2>场桥调度管理</h2>
        <p class="page-desc">维护场桥，围绕场桥编号、场桥型号、作业箱区、跨距参数做登记、筛选与状态流转。</p>
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
        <input v-model.trim="draftBlock" placeholder="输入作业箱区，全角半角均可" />
      </label>
      <label class="filter-item">
        <span>场桥编号</span>
        <input v-model.trim="draftKeyword" placeholder="按场桥编号检索" />
      </label>
      <label class="filter-item">
        <span>场桥状态</span>
        <select v-model="draftStatus">
          <option value="">全部在场状态</option>
          <option v-for="option in statuses.filter((s) => s !== '停用')" :key="option" :value="option">
            {{ option }}
          </option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in sortableColumns" :key="column.key" class="sort-head">
            <button type="button" class="sort-btn" @click="changeSort(column.key)">
              {{ column.label }}
              <span class="sort-mark">{{ sortMark(column.key) }}</span>
            </button>
          </th>
          <th v-for="column in plainColumns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
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
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">没有符合条件的在场场桥，换个箱区或重置条件试试</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条在场场桥记录，第 {{ page }} / {{ totalPages }} 页</span>
      <span class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="gotoPage(page - 1)">上一页</button>
        <button
          v-for="p in totalPages"
          :key="p"
          class="btn"
          :class="{ primary: p === page }"
          type="button"
          @click="gotoPage(p)"
        >
          {{ p }}
        </button>
        <button class="btn" type="button" :disabled="page >= totalPages" @click="gotoPage(page + 1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button class="link" type="button" @click="reload">重试</button>
      </span>
    </footer>
  </section>
</template>

<script lang="ts">
export default { name: 'RtgList' }
</script>

<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatsMap = Record<string, number>

const ENDPOINT = '/api/rtg'
const PAGE_SIZE = 5
const columns = ['场桥编号', '场桥型号', '作业箱区', '跨距参数', '起升高度', '作业司机', '柴油油量', '场桥状态']
const sortableColumns = [
  { key: '场桥编号', label: '场桥编号' },
  { key: '作业司机', label: '作业司机' },
  { key: '跨距参数', label: '跨距参数' },
]
const plainColumns = columns.filter((column) => !sortableColumns.some((item) => item.key === column))
const actions = ['分配作业', '释放场桥', '登记检修']
const statuses = ['空闲', '作业中', '检修中', '停用']
const SORT_OPTIONS = new Set(['场桥编号', '作业司机', '跨距参数'])

// 已生效的查询条件（与输入框分离，避免输入过程触发查询）。
const appliedBlock = ref('')
const appliedKeyword = ref('')
const appliedStatus = ref('')
// 输入框草稿。
const draftBlock = ref('')
const draftKeyword = ref('')
const draftStatus = ref('')
// 排列方式与翻页在查询后保持，不靠 URL 之外的临时状态。
const sortBy = ref('场桥编号')
const sortOrder = ref<'asc' | 'desc'>('asc')
const page = ref(1)
const requestSeq = ref(0)

const rows = ref<Row[]>([])
const total = ref(0)
const statsMap = ref<StatsMap>({})
const errorMessage = ref('')

const router = useRouter()
const route = useRoute()
let savedScrollTop = 0

const stats = computed(() => [
  { label: '空闲场桥', value: statsMap.value['空闲'] ?? 0 },
  { label: '作业场桥', value: statsMap.value['作业中'] ?? 0 },
  { label: '检修场桥', value: statsMap.value['检修中'] ?? 0 },
])
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

/** 全角半角、大小写与空白归一，用于条件去重比较。 */
function normalize(value: string) {
  return value.normalize('NFKC').replace(/\s+/g, '').toLowerCase()
}

/** 全角半角归一后再比较条件，同一作业箱区重复提交只生效一次。 */
function sameCondition() {
  return (
    normalize(draftBlock.value) === normalize(appliedBlock.value) &&
    normalize(draftKeyword.value) === normalize(appliedKeyword.value) &&
    draftStatus.value === appliedStatus.value
  )
}

function syncDrafts() {
  draftBlock.value = appliedBlock.value
  draftKeyword.value = appliedKeyword.value
  draftStatus.value = appliedStatus.value
}

function submitQuery() {
  // 条件归一比较：Ａ区与 A区视为同一条件，重复提交不再发请求。
  if (sameCondition()) {
    return
  }
  appliedBlock.value = draftBlock.value.trim()
  appliedKeyword.value = draftKeyword.value.trim()
  appliedStatus.value = draftStatus.value
  // 新条件从第一页开始；排列方式保持不变。
  page.value = 1
  void reload()
}

function resetFilters() {
  draftBlock.value = ''
  draftKeyword.value = ''
  draftStatus.value = ''
  appliedBlock.value = ''
  appliedKeyword.value = ''
  appliedStatus.value = ''
  sortBy.value = '场桥编号'
  sortOrder.value = 'asc'
  page.value = 1
  void reload()
}

function changeSort(column: string) {
  // 排列方式与已选条件冲突时以已选条件为准：排序只改顺序，条件集合不变。
  if (sortBy.value === column) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = column
    sortOrder.value = 'asc'
  }
  page.value = 1
  void reload()
}

function sortMark(column: string) {
  if (sortBy.value !== column) {
    return '↕'
  }
  return sortOrder.value === 'asc' ? '↑' : '↓'
}

function gotoPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value) {
    return
  }
  page.value = target
  void reload()
}

function exportRows() {
  // 导出沿用列表当前的已选条件，台数与清单和列表页对得上。
  const params = new URLSearchParams()
  if (appliedBlock.value) {
    params.set('block', appliedBlock.value)
  }
  if (appliedKeyword.value) {
    params.set('keyword', appliedKeyword.value)
  }
  if (appliedStatus.value) {
    params.set('status', appliedStatus.value)
  }
  const query = params.toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '场桥登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  // 从列表钻取前记录滚动位置，配合 keep-alive 返回时停在原处。
  savedScrollTop = window.scrollY
  const backQuery: Record<string, string> = {}
  if (appliedBlock.value) backQuery.block = appliedBlock.value
  if (appliedKeyword.value) backQuery.keyword = appliedKeyword.value
  if (appliedStatus.value) backQuery.status = appliedStatus.value
  backQuery.sort_by = sortBy.value
  backQuery.sort_order = sortOrder.value
  backQuery.page = String(page.value)
  void router.push({ name: 'rtg-detail', params: { id: String(row.id) }, query: backQuery })
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('场桥调度动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场桥调度操作失败，请重试'
  }
}

function buildQuery() {
  const params = new URLSearchParams({
    page: String(page.value),
    size: String(PAGE_SIZE),
    sort_by: sortBy.value,
    sort_order: sortOrder.value,
  })
  if (appliedBlock.value) {
    params.set('block', appliedBlock.value)
  }
  if (appliedKeyword.value) {
    params.set('keyword', appliedKeyword.value)
  }
  if (appliedStatus.value) {
    params.set('status', appliedStatus.value)
  }
  return params.toString()
}

async function reload() {
  const query = buildQuery()
  // 条件与排列同步进地址栏，刷新或从详情回来都能还原到原处。
  router.replace({ query: Object.fromEntries(new URLSearchParams(query)) })
  const seq = ++requestSeq.value
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('场桥列表取数失败，请检查网络后点“重试”')
    }
    const payload = await response.json()
    // 慢响应先回来时不能覆盖最新一页的数据。
    if (seq !== requestSeq.value) {
      return
    }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    statsMap.value = payload.stats ?? {}
    errorMessage.value = ''
  } catch (error) {
    if (seq !== requestSeq.value) {
      return
    }
    errorMessage.value = error instanceof Error ? error.message : '场桥调度列表取数失败，请重试'
  }
}

/** 从地址栏恢复已选条件、排列方式与页码（详情返回/刷新场景）。 */
function restoreFromRoute() {
  const q = route.query
  appliedBlock.value = typeof q.block === 'string' ? q.block : ''
  appliedKeyword.value = typeof q.keyword === 'string' ? q.keyword : ''
  appliedStatus.value = typeof q.status === 'string' ? q.status : ''
  const sortColumn = typeof q.sort_by === 'string' ? q.sort_by : '场桥编号'
  sortBy.value = SORT_OPTIONS.has(sortColumn) ? sortColumn : '场桥编号'
  sortOrder.value = q.sort_order === 'desc' ? 'desc' : 'asc'
  const parsedPage = Number(q.page)
  page.value = Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1
  syncDrafts()
}

let restored = false
onMounted(() => {
  restoreFromRoute()
  void reload()
})

onActivated(() => {
  if (!restored) {
    // 首次挂载时 onMounted 已加载，避免重复请求。
    restored = true
    return
  }
  // 详情页可能执行过动作，回到列表时刷新当前页；页码、条件与滚动位置保持不变。
  void reload()
  window.scrollTo({ top: savedScrollTop })
})

onDeactivated(() => {
  savedScrollTop = window.scrollY
})
</script>

<style scoped>
.page-actions {
  display: flex;
  gap: 8px;
}
.filter-item select {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.sort-head {
  padding: 0;
}
.sort-btn {
  width: 100%;
  border: none;
  background: none;
  padding: 8px 10px;
  text-align: left;
  font: inherit;
  color: inherit;
  cursor: pointer;
}
.sort-btn:hover {
  color: var(--brand);
}
.sort-mark {
  color: var(--muted);
  font-size: 11px;
}
.pager {
  display: flex;
  gap: 4px;
  align-items: center;
}
.pager .btn {
  padding: 2px 10px;
}
.pager .btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.error-text .link {
  margin-left: 6px;
}
</style>
