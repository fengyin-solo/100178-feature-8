<template>
  <section class="page" data-module="pressurepipe">
    <header class="page-head">
      <div>
        <h2>压力管道管理</h2>
        <p class="page-desc">维护压力管道台账，支持按模板成批录入管道级别、输送介质与下次检验日，逐行校验、问题行可单独下载修正后续跑。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="downloadTemplate">下载录入模板</button>
        <button class="btn primary" type="button" @click="triggerImport">批量录入</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,text/csv"
          class="hidden-file"
          @change="handleFileChange"
        />
        <button class="btn" type="button" @click="exportRows">按当前条件导出清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div v-if="importResult" class="import-panel">
      <div class="import-summary">
        <strong>本次录入结果：</strong>
        <span>共解析 {{ importResult.total }} 行，新增 {{ importResult.created }} 条，更新 {{ importResult.updated }} 条，跳过 {{ importResult.skipped }} 条。</span>
        <span v-if="importResult.skipped" class="error-text">下列行未写入，修正后重新导入同一文件即可从问题行续跑，已写入的管道不会重复。</span>
        <button v-if="importResult.errors.length" class="btn ghost" type="button" @click="downloadErrorRows">下载问题行清单</button>
      </div>
      <table v-if="importResult.errors.length" class="data-table error-table">
        <thead>
          <tr>
            <th>文件行号</th>
            <th>管道编号</th>
            <th>未写入原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in importResult.errors" :key="item.line">
            <td>{{ item.line }}</td>
            <td>{{ item['管道编号'] || '—' }}</td>
            <td class="error-text">{{ item.reasons.join('；') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field.key" class="filter-item">
        <span>{{ field.label }}</span>
        <input v-model="filters[field.key]" :placeholder="`按${field.label}检索`" />
      </label>
      <label class="filter-item">
        <span>管道状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="option in statuses" :key="option" :value="option">{{ option }}</option>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无压力管道数据，可下载模板后批量录入</td>
        </tr>
      </tbody>
    </table>

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

interface ImportErrorItem {
  line: number
  '管道编号': string
  reasons: string[]
  raw: Record<string, string>
}

interface ImportResultPayload {
  total: number
  created: number
  updated: number
  skipped: number
  errors: ImportErrorItem[]
}

const ENDPOINT = '/api/pressurepipe'
const columns = ['管道编号', '管道名称', '管道级别', '公称直径', '输送介质', '敷设方式', '下次检验日', '管道状态']
const errorColumns = ['管道编号', '管道名称', '管道级别', '公称直径', '输送介质', '敷设方式', '下次检验日']
const actions = ['办理投用', '安排检修', '停用管道']
const statuses = ['待投用', '在用运行', '隔离检修', '已停用']
const stats = [{ label: '在用管道', value: 0 }, { label: '隔离检修', value: 0 }, { label: '管道总长', value: 0 }]
// 筛选键与后端查询参数一一对应，导出时复用同一份条件，保证清单对得上。
const filterFields = [
  { key: 'keyword', label: '管道编号' },
  { key: 'level', label: '管道级别' },
  { key: 'medium', label: '输送介质' },
] as const

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const importResult = ref<ImportResultPayload | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const filters = ref<Record<string, string>>({ keyword: '', level: '', medium: '', status: '' })

function currentQuery(): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value.trim()) {
      params.set(key, value.trim())
    }
  }
  return params.toString()
}

function resetFilters() {
  filters.value = { keyword: '', level: '', medium: '', status: '' }
  void reload()
}

function downloadTemplate() {
  window.open(`${ENDPOINT}/template`, '_blank')
}

function exportRows() {
  const query = currentQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function triggerImport() {
  errorMessage.value = ''
  fileInput.value?.click()
}

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function saveCsv(filename: string, content: string) {
  const blob = new Blob([`﻿${content}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function downloadErrorRows() {
  const result = importResult.value
  if (!result || !result.errors.length) {
    return
  }
  const lines = [['文件行号', ...errorColumns, '未写入原因'].map(csvCell).join(',')]
  for (const item of result.errors) {
    lines.push([
      item.line,
      ...errorColumns.map((column) => item.raw[column] ?? ''),
      item.reasons.join('；'),
    ].map(csvCell).join(','))
  }
  saveCsv('pressurepipe-import-errors.csv', lines.join('\r\n'))
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  errorMessage.value = ''
  importResult.value = null
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(payload?.detail || `批量录入失败（接口返回 ${response.status}）`)
    }
    importResult.value = (await response.json()) as ImportResultPayload
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量录入失败'
  }
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
  const query = currentQuery()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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
.hidden-file {
  display: none;
}

.import-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.import-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  font-size: 13px;
}

.error-table {
  margin-top: 4px;
}

.filter-item select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
</style>
