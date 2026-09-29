<template>
  <section class="page" data-module="pressurepipe">
    <header class="page-head">
      <div>
        <h2>压力管道管理</h2>
        <p class="page-desc">维护压力管道，按模板成批录入管道级别、输送介质与下次检验日，逐行校验、可断点续做。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记压力管道</button>
        <a class="btn" :href="templateUrl" download>下载导入模板</a>
        <button class="btn" type="button" @click="triggerImport">批量导入</button>
        <button class="btn" type="button" @click="exportRows">导出压力管道清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,text/csv,text/plain"
          hidden
          @change="onFileChange"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>管道状态</span>
        <select v-model="filters['status']">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无压力管道数据，可先登记压力管道</td>
        </tr>
      </tbody>
    </table>

    <section v-if="importResult" class="import-panel">
      <header class="import-head">
        <strong>批量导入结果（{{ importResult.filename }}）</strong>
        <span class="import-summary">
          共 {{ importResult.total }} 行：新增 {{ importResult.created }}，更新 {{ importResult.updated }}，跳过 {{ importResult.skipped }}
        </span>
        <button
          v-if="!importResult.done"
          class="btn primary"
          type="button"
          :disabled="resuming"
          @click="resumeImport"
        >
          {{ resuming ? '正在从失败行继续…' : '从失败行继续导入' }}
        </button>
      </header>
      <p v-if="importResult.fatal" class="error-text import-fatal">
        中断原因：{{ importResult.fatal }}
      </p>
      <table class="data-table">
        <thead>
          <tr>
            <th>行号</th>
            <th>管道编号</th>
            <th>结果</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in importResult.results" :key="item.row">
            <td>{{ item.row }}</td>
            <td>{{ item.管道编号 || '—' }}</td>
            <td>
              <span v-if="item.ok" :class="item.action === 'created' ? 'tag tag-created' : 'tag tag-updated'">
                {{ item.action === 'created' ? '已录入' : '已更新' }}
              </span>
              <span v-else class="tag tag-skipped">已跳过</span>
            </td>
            <td>{{ item.reason || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条压力管道记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ImportRowResult = {
  row: number
  管道编号: string
  ok: boolean
  action: string | null
  reason: string | null
}
type ImportResult = {
  ok: boolean
  message?: string
  batch_id: string
  filename: string
  total: number
  processed: number
  created: number
  updated: number
  skipped: number
  done: boolean
  fatal: string | null
  results: ImportRowResult[]
}

const ENDPOINT = '/api/pressurepipe'
const columns = ["管道编号", "管道名称", "管道级别", "公称直径", "输送介质", "敷设方式", "下次检验日", "管道状态"]
const actions = ["办理投用", "安排检修", "停用管道"]
const statuses = ["待投用", "在用运行", "隔离检修", "已停用"]
const stats = [{"label": "在用管道", "value": 0}, {"label": "隔离检修", "value": 0}, {"label": "管道总长", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const fileInput = ref<HTMLInputElement | null>(null)
const importResult = ref<ImportResult | null>(null)
const resuming = ref(false)

const templateUrl = `${ENDPOINT}/template`

function resetFilters() {
  filters.value = {}
  void reload()
}

function buildQuery(): string {
  return new URLSearchParams(filters.value as Record<string, string>).toString()
}

function exportRows() {
  window.open(`${ENDPOINT}/export?${buildQuery()}`, '_blank')
}

function triggerImport() {
  fileInput.value?.click()
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  errorMessage.value = ''
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content }),
    })
    if (!response.ok) {
      throw new Error('批量导入请求失败，请稍后重试')
    }
    const result = await response.json() as ImportResult
    importResult.value = result
    if (!result.ok) {
      errorMessage.value = result.message ?? '批量导入失败'
      return
    }
    if (!result.done) {
      await resumeImport()
    } else {
      await reload()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量导入失败'
  }
}

async function resumeImport() {
  const batch = importResult.value
  if (!batch) return
  resuming.value = true
  errorMessage.value = ''
  try {
    let result = batch
    for (let attempt = 0; attempt < 5 && !result.done; attempt += 1) {
      const response = await request(`${ENDPOINT}/import/${result.batch_id}/resume`, { method: 'POST' })
      if (!response.ok) {
        throw new Error('续传请求失败，请稍后重试')
      }
      result = await response.json() as ImportResult
      importResult.value = result
    }
    if (!result.ok) {
      errorMessage.value = result.message ?? '批量导入失败'
    } else if (!result.done) {
      errorMessage.value = result.fatal ?? '导入尚未完成，请再次点击「从失败行继续导入」'
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '续传失败'
  } finally {
    resuming.value = false
  }
}

function openCreate() {
  errorMessage.value = '压力管道登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('压力管道动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '压力管道操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) {
      throw new Error('压力管道列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '压力管道列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.import-panel {
  margin-top: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.import-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.import-summary {
  color: var(--muted);
  font-size: 13px;
}
.import-fatal {
  margin: 0 0 8px;
}
.tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.tag-created { background: #e7f0fe; color: #1f6feb; }
.tag-updated { background: #e6f6ec; color: #1a7f37; }
.tag-skipped { background: #fdecea; color: #b42318; }
.page-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
