<template>
  <section class="admin-section">
    <div class="section-header">
      <h2 class="section-title">
        Crawl History
        <span v-if="crawlTotal" class="flag-count">{{ crawlTotal }}</span>
      </h2>
      <div class="crawl-filters">
        <select
          v-model="crawlTaskType"
          class="crawl-select"
          @change="setCrawlFilter(crawlFilter)"
        >
          <option value="">Tous les types</option>
          <option v-for="t in crawlTaskTypes" :key="t" :value="t">{{ t }}</option>
        </select>
        <div class="filter-group">
          <button
            v-for="f in crawlFilters"
            :key="f.value"
            class="filter-btn"
            :class="{ active: crawlFilter === f.value }"
            @click="setCrawlFilter(f.value)"
          >
            {{ f.label }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="loadingCrawlLogs" class="state">Chargement...</div>
    <div v-else-if="crawlLogs.length === 0" class="state">Aucun crawl log.</div>

    <div v-else class="table-wrap">
      <table class="flag-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Cible</th>
            <th>Source</th>
            <th>Status</th>
            <th>Duree</th>
            <th>Stats</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in crawlLogs" :key="log.id">
            <td class="mono" style="font-size: var(--fs-xs); white-space: nowrap">
              {{ formatDate(log.started_at) }}
            </td>
            <td>
              <span class="token-pill">{{ log.task_type }}</span>
            </td>
            <td
              class="raw-string"
              style="
                max-width: 200px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
              "
            >
              {{ log.target_label || '-' }}
            </td>
            <td>
              <span v-if="log.source" class="token-pill">{{ log.source }}</span>
              <span v-else class="muted">-</span>
            </td>
            <td>
              <span class="status-badge" :class="log.status">{{ log.status }}</span>
            </td>
            <td class="mono" style="font-size: var(--fs-xs)">
              {{ log.duration_ms != null ? formatDuration(log.duration_ms) : '-' }}
            </td>
            <td
              style="
                font-size: var(--fs-xs);
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-05);
                align-items: center;
              "
            >
              <template v-if="log.stats">
                <span v-for="(v, k) in log.stats" :key="k" class="stat-chip">
                  {{ k }}: {{ v }}
                </span>
              </template>
              <span
                v-if="log.error_message"
                class="sync-error"
                style="font-size: var(--fs-xs)"
                :title="log.error_message"
              >
                {{ log.error_message.slice(0, 60) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="crawlTotalPages > 1" class="crawl-pagination">
      <button :disabled="crawlPage <= 1" @click="prevCrawlPage()">Prev</button>
      <span class="mono" style="font-size: var(--fs-sm)">{{ crawlPage }} / {{ crawlTotalPages }}</span>
      <button :disabled="crawlPage >= crawlTotalPages" @click="nextCrawlPage()">Next</button>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../../utils/api.js'

const crawlLogs = ref([])
const loadingCrawlLogs = ref(false)
const crawlPage = ref(1)
const crawlTotal = ref(0)
const crawlTotalPages = ref(0)
const crawlFilter = ref('')
const crawlTaskType = ref('')
const crawlFilters = [
  { label: 'Tous', value: '' },
  { label: 'Success', value: 'success' },
  { label: 'Error', value: 'error' },
  { label: 'Running', value: 'running' },
]
const crawlTaskTypes = [
  'crawl_radar',
  'crawl_playlist',
  'enrich_catalog',
  'enrich_beatport',
  'reclassify_genres',
  'sync_artists',
  'fetch_artworks',
  'resolve_set_tracks',
  'enrich_set_tracks',
]

function prevCrawlPage() {
  crawlPage.value--
  fetchCrawlLogs()
}

function nextCrawlPage() {
  crawlPage.value++
  fetchCrawlLogs()
}

async function fetchCrawlLogs() {
  loadingCrawlLogs.value = true
  try {
    const params = { page: crawlPage.value, per_page: 20 }
    if (crawlFilter.value) params.status = crawlFilter.value
    if (crawlTaskType.value) params.task_type = crawlTaskType.value
    const { data } = await api.get('/api/admin/crawl-logs', { params })
    crawlLogs.value = data.items
    crawlTotal.value = data.total
    crawlTotalPages.value = Math.ceil(data.total / data.per_page)
  } finally {
    loadingCrawlLogs.value = false
  }
}

function setCrawlFilter(val) {
  crawlFilter.value = val
  crawlPage.value = 1
  fetchCrawlLogs()
}

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m${String(s % 60).padStart(2, '0')}s`
}

onMounted(() => {
  fetchCrawlLogs()
})
</script>

<style scoped>
.admin-section {
  margin-bottom: var(--space-8);
  padding: var(--space-5) var(--space-6);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.section-title {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.flag-count {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: var(--space-05) var(--space-15);
  border-radius: 10px;
}
.filter-group {
  display: flex;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.filter-btn {
  padding: var(--space-15) var(--space-3);
  border: none;
  background: var(--surface);
  color: var(--ink-3);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}
.filter-btn:not(:last-child) {
  border-right: 1px solid var(--line-2);
}
.filter-btn.active {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.table-wrap {
  overflow-x: auto;
}
.flag-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}
.flag-table thead th {
  text-align: left;
  padding: 0 var(--space-3) var(--space-25);
  font: 500 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.flag-table tbody td {
  padding: var(--space-25) var(--space-3);
  vertical-align: top;
  border-bottom: 1px solid var(--line);
}
.flag-table tbody tr:last-child td {
  border-bottom: none;
}
.raw-string {
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
}
.token-pill {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  white-space: nowrap;
}
.status-badge {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  padding: var(--space-05) var(--space-2);
  border-radius: 4px;
}
.status-badge.running {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.status-badge.success {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.status-badge.error {
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.sync-error {
  font-size: var(--fs-sm);
  color: var(--neg-ink);
}
.state {
  /* diverges from canonical .state: smaller font + compact padding (admin panel) */
  font-size: var(--fs-sm);
  padding: var(--space-3) 0;
}
.mono {
  font-family: var(--font-mono);
}
.muted {
  color: var(--ink-3);
}
.stat-chip {
  display: inline-block;
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: var(--space-05) var(--space-15);
  border-radius: 3px;
  margin: var(--space-05) var(--space-05);
  white-space: nowrap;
}
.crawl-filters {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.crawl-select {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 400 var(--fs-xs)/1 var(--font-mono);
  cursor: pointer;
}
.crawl-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.crawl-pagination button {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
}
.crawl-pagination button:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>
