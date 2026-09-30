<template>
  <section class="page" data-module="rtg-detail">
    <header class="page-head">
      <div>
        <h2>场桥明细</h2>
        <p class="page-desc">查看单台场桥的调度信息；明细与列表取自同一份数据，司机等字段保持一致。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <article v-if="entry" class="detail-card">
      <dl class="detail-grid">
        <template v-for="field in fields" :key="field">
          <dt>{{ field }}</dt>
          <dd>{{ entry[field] ?? '—' }}</dd>
        </template>
      </dl>
      <div class="detail-actions">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          type="button"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
      </div>
    </article>

    <p v-if="errorMessage" class="error-text">
      {{ errorMessage }}
      <button class="link" type="button" @click="load">重试</button>
    </p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const fields = ['场桥编号', '场桥型号', '作业箱区', '跨距参数', '起升高度', '作业司机', '柴油油量', '场桥状态']
const actions = ['分配作业', '释放场桥', '登记检修']

const route = useRoute()
const router = useRouter()
const entry = ref<Row | null>(null)
const errorMessage = ref('')

async function load() {
  errorMessage.value = ''
  try {
    const response = await request(`/api/rtg/${route.params.id}`)
    if (!response.ok) {
      throw new Error('场桥明细取数失败，请检查网络后点“重试”')
    }
    entry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场桥明细取数失败，请重试'
  }
}

async function runAction(action: string) {
  if (!entry.value) {
    return
  }
  errorMessage.value = ''
  try {
    const response = await request(`/api/rtg/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('场桥调度动作未生效，请稍后重试')
    }
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场桥调度操作失败，请重试'
  }
}

function goBack() {
  // 回到列表路由并带上离开时的条件、页码与排列，列表组件由 keep-alive 保持在原处。
  void router.push({ name: 'rtg', query: route.query })
}

onMounted(load)
</script>

<style scoped>
.page-actions {
  display: flex;
  gap: 8px;
}
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 120px 1fr 120px 1fr;
  gap: 10px 16px;
  margin: 0;
}
.detail-grid dt {
  color: var(--muted);
  font-size: 13px;
}
.detail-grid dd {
  margin: 0;
  font-size: 13px;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}
.error-text .link {
  margin-left: 6px;
}
</style>
