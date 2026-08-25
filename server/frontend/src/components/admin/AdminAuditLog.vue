<template>
  <section class="admin-section">
    <div class="section-header">
      <h2 class="section-title">
        Journal d'audit
        <span v-if="total" class="flag-count">{{ total }}</span>
      </h2>
    </div>
    <p class="section-sub">
      Qui a fait quoi, et quand — actions admin sensibles, les plus récentes d'abord.
    </p>

    <div v-if="loading" class="state">Chargement...</div>
    <div v-else-if="error" class="state state--error">{{ error }}</div>
    <div v-else-if="items.length === 0" class="state">Aucune entrée d'audit.</div>

    <div v-else class="table-wrap">
      <table class="flag-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Auteur</th>
            <th>Action</th>
            <th>Cible</th>
            <th>Détails</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in items" :key="entry.id">
            <td class="log-date mono" data-label="Date">
              {{ formatDate(entry.created_at) }}
            </td>
            <td class="log-author" data-label="Auteur">
              {{ entry.user_email || '—' }}
            </td>
            <td data-label="Action">
              <span class="token-pill">{{ entry.action }}</span>
            </td>
            <td class="log-target" data-label="Cible">
              <span v-if="entry.target_type" class="mono"
                >{{ entry.target_type
                }}<template v-if="entry.target_id != null"> #{{ entry.target_id }}</template></span
              >
              <span v-else class="muted">—</span>
            </td>
            <td class="log-details" data-label="Détails">
              <details v-if="hasDetails(entry.details)">
                <summary>{{ detailsPreview(entry.details) }}</summary>
                <pre class="details-json">{{ formatDetails(entry.details) }}</pre>
              </details>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="crawl-pagination">
      <button :disabled="page <= 1" @click="prevPage()">Précédent</button>
      <span class="mono" style="font-size: var(--fs-sm)">{{ page }} / {{ totalPages }}</span>
      <button :disabled="page >= totalPages" @click="nextPage()">Suivant</button>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../utils/api.js'

const PER_PAGE = 20

const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')

const totalPages = computed(() => Math.ceil(total.value / PER_PAGE))

async function fetchPage() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/admin/audit-log', {
      params: { page: page.value, per_page: PER_PAGE },
    })
    items.value = data.items
    total.value = data.total
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erreur de chargement du journal'
    items.value = []
  } finally {
    loading.value = false
  }
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  fetchPage()
}

function nextPage() {
  if (page.value >= totalPages.value) return
  page.value++
  fetchPage()
}

function hasDetails(details) {
  return details && typeof details === 'object' && Object.keys(details).length > 0
}

function formatDetails(details) {
  return JSON.stringify(details, null, 2)
}

function detailsPreview(details) {
  const compact = JSON.stringify(details)
  return compact.length > 60 ? compact.slice(0, 60) + '…' : compact
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(() => {
  fetchPage()
})
</script>

<style scoped>
.admin-section {
  container-type: inline-size;
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
  margin-bottom: var(--space-2);
}
.section-title {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.section-sub {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-3);
  margin-bottom: var(--space-4);
}
.flag-count {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: var(--space-05) var(--space-15);
  border-radius: 10px;
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
.token-pill {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  white-space: nowrap;
}
.log-date {
  font-size: var(--fs-xs);
  white-space: nowrap;
}
.log-author {
  font: 400 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
}
.log-target {
  font-size: var(--fs-xs);
}
.log-details {
  max-width: 320px;
}
.log-details summary {
  cursor: pointer;
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-3);
}
.details-json {
  margin-top: var(--space-1);
  padding: var(--space-2);
  background: var(--surface-2);
  border-radius: var(--r-sm);
  font: 400 var(--fs-xs)/1.4 var(--font-mono);
  color: var(--ink-2);
  white-space: pre-wrap;
  word-break: break-word;
}
.state {
  font-size: var(--fs-sm);
  padding: var(--space-3) 0;
}
.state--error {
  color: var(--neg-ink);
}
.mono {
  font-family: var(--font-mono);
}
.muted {
  color: var(--ink-3);
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

/* ============ RESPONSIVE — table → cartes (palier 859) ============ */
@container (max-width: 859px) {
  .table-wrap {
    overflow-x: visible;
  }
  .flag-table,
  .flag-table tbody {
    display: block;
  }
  .flag-table thead {
    display: none;
  }
  .flag-table tbody tr {
    display: flex;
    flex-direction: column;
    gap: var(--space-25);
    padding: var(--space-3);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    background: var(--surface);
  }
  .flag-table tbody tr + tr {
    margin-top: var(--space-25);
  }
  .flag-table tbody td {
    display: block;
    padding: 0;
    border-bottom: none;
  }
  .flag-table tbody td[data-label]::before {
    content: attr(data-label);
    display: block;
    margin-bottom: var(--space-1);
    font: 500 var(--fs-xs)/1 var(--font-mono);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .log-details {
    max-width: none;
  }
}
</style>
