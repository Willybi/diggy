<template>
  <!-- Reclassifier genres -->
  <section class="admin-section">
    <h2 class="section-title">Reclassifier tous les genres</h2>
    <p class="section-sub">
      Efface tous les genres et re-fetche : Deezer (album) d'abord, fallback Beatport. ~5200
      tracks, peut prendre plusieurs heures.
    </p>
    <div class="sync-row">
      <label class="batch-label">
        Planifier à
        <input
          v-model="reclassifyEta"
          type="datetime-local"
          class="batch-input"
          style="width: 180px"
        />
      </label>
      <button class="btn-sync" :disabled="reclassifying" @click="runReclassify">
        {{ reclassifying ? 'Lancé…' : reclassifyEta ? 'Planifier' : 'Lancer maintenant' }}
      </button>
      <span v-if="reclassifyResult" class="enrich-result" :class="reclassifyResult.cls">{{
        reclassifyResult.text
      }}</span>
    </div>
  </section>

  <!-- Mappings genres -->
  <section class="admin-section">
    <div class="section-header">
      <h2 class="section-title">
        Mappings genres
        <span v-if="mappingStats" class="flag-count"
          >{{ mappingStats.unmapped }} / {{ mappingStats.total }} non mappés</span
        >
      </h2>
      <div class="filter-group">
        <button
          class="filter-btn"
          :class="{ active: !mappingShowUnmapped }"
          @click="showAllMappings()"
        >
          Tous
        </button>
        <button
          class="filter-btn"
          :class="{ active: mappingShowUnmapped }"
          @click="showUnmappedOnly()"
        >
          Non mappés
        </button>
      </div>
    </div>
    <p class="section-sub">
      Associe les noms de genres bruts (Beatport/Deezer) aux nœuds de la taxonomie Wikidata.
    </p>

    <div v-if="loadingMappings" class="state">Chargement…</div>
    <div v-else-if="mappings.length === 0" class="state">Aucun mapping.</div>

    <div v-else class="table-wrap">
      <table class="flag-table">
        <thead>
          <tr>
            <th>Nom brut</th>
            <th>Nœud taxonomique</th>
            <th style="width: 260px">Recherche</th>
            <th style="width: 80px" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in mappings" :key="m.id">
            <td>
              <span class="raw-string">{{ m.rawName }}</span>
            </td>
            <td>
              <span v-if="m.nodeLabel" class="token-pill">{{ m.nodeLabel }}</span>
              <span v-else class="muted" style="font-size: 12px; color: var(--ink-3)">—</span>
            </td>
            <td>
              <div class="mapping-search-wrap">
                <input
                  v-model="mappingSearch[m.id]"
                  class="mapping-search-input"
                  placeholder="Chercher un genre…"
                  @input="onMappingSearch(m.id)"
                />
                <div v-if="mappingResults[m.id]?.length" class="mapping-dropdown">
                  <div
                    v-for="n in mappingResults[m.id]"
                    :key="n.id"
                    class="mapping-option"
                    :class="{ selected: mappingSelected[m.id] === n.id }"
                    @click="selectMappingOption(m, n)"
                  >
                    <span class="mapping-option-label">{{ n.label }}</span>
                    <span class="mapping-option-qid mono">{{ n.wikidataId }}</span>
                  </div>
                </div>
              </div>
            </td>
            <td>
              <button
                v-if="mappingSelected[m.id]"
                class="btn-sync"
                style="padding: 5px 12px; font-size: 11px"
                :disabled="savingMapping[m.id]"
                @click="saveMapping(m)"
              >
                {{ savingMapping[m.id] ? '…' : 'Associer' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../../utils/api.js'

const reclassifying = ref(false)
const reclassifyEta = ref('')
const reclassifyResult = ref(null)

const mappings = ref([])
const loadingMappings = ref(false)
const mappingShowUnmapped = ref(true)
const mappingStats = ref(null)
const mappingSearch = reactive({})
const mappingResults = reactive({})
const mappingSelected = reactive({})
const savingMapping = reactive({})
let mappingTimers = {}

function showAllMappings() {
  mappingShowUnmapped.value = false
  fetchMappings()
}

function showUnmappedOnly() {
  mappingShowUnmapped.value = true
  fetchMappings()
}

function selectMappingOption(m, n) {
  mappingSelected[m.id] = n.id
  mappingSearch[m.id] = n.label
  mappingResults[m.id] = []
}

async function runReclassify() {
  reclassifying.value = true
  reclassifyResult.value = null
  try {
    const params = reclassifyEta.value ? `?eta=${new Date(reclassifyEta.value).toISOString()}` : ''
    const { data } = await api.post(`/api/admin/genres/reclassify${params}`)
    const when = reclassifyEta.value ? ` pour ${reclassifyEta.value}` : ''
    reclassifyResult.value = {
      text: `Task planifiée${when} (${data.task_id.slice(0, 8)}…)`,
      cls: 'ok',
    }
  } catch (e) {
    reclassifyResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    reclassifying.value = false
  }
}

async function fetchMappings() {
  loadingMappings.value = true
  try {
    const params = { limit: 200 }
    if (mappingShowUnmapped.value) params.unmapped = true
    const { data } = await api.get('/api/taxonomy/mappings', { params })
    mappings.value = data.items
    for (const m of data.items) {
      if (!(m.id in mappingSearch)) mappingSearch[m.id] = ''
      if (!(m.id in mappingResults)) mappingResults[m.id] = []
      if (!(m.id in mappingSelected)) mappingSelected[m.id] = null
      if (!(m.id in savingMapping)) savingMapping[m.id] = false
    }
  } finally {
    loadingMappings.value = false
  }
}

async function fetchMappingStats() {
  const [all, unmapped] = await Promise.all([
    api.get('/api/taxonomy/mappings', { params: { limit: 1 } }),
    api.get('/api/taxonomy/mappings', { params: { unmapped: true, limit: 1 } }),
  ])
  mappingStats.value = { total: all.data.total, unmapped: unmapped.data.total }
}

function onMappingSearch(mappingId) {
  clearTimeout(mappingTimers[mappingId])
  mappingSelected[mappingId] = null
  const q = (mappingSearch[mappingId] || '').trim()
  if (!q) {
    mappingResults[mappingId] = []
    return
  }
  mappingTimers[mappingId] = setTimeout(async () => {
    const { data } = await api.get('/api/taxonomy/nodes', { params: { q, limit: 8 } })
    mappingResults[mappingId] = data.items
  }, 250)
}

async function saveMapping(m) {
  const nodeId = mappingSelected[m.id]
  if (!nodeId) return
  savingMapping[m.id] = true
  try {
    await api.put(`/api/taxonomy/mappings/${encodeURIComponent(m.rawName)}`, null, {
      params: { node_id: nodeId },
    })
    const node = mappingResults[m.id]?.find((n) => n.id === nodeId)
    m.nodeId = nodeId
    m.nodeLabel = node?.label || mappingSearch[m.id]
    m.nodeWikidataId = node?.wikidataId
    mappingSearch[m.id] = ''
    mappingResults[m.id] = []
    mappingSelected[m.id] = null
    if (mappingShowUnmapped.value) {
      mappings.value = mappings.value.filter((x) => x.id !== m.id)
    }
    await fetchMappingStats()
  } finally {
    savingMapping[m.id] = false
  }
}

onMounted(() => {
  fetchMappings()
  fetchMappingStats()
})
</script>

<style scoped>
.admin-section {
  margin-bottom: 36px;
  padding: 20px 24px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-title {
  font: 600 15px/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-header .section-title {
  margin-bottom: 0;
}
.section-sub {
  font: 400 12px/1.4 var(--font-ui);
  color: var(--ink-3);
  margin-bottom: 14px;
}
.flag-count {
  font: 400 11px/1 var(--font-mono);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: 2px 7px;
  border-radius: 10px;
}
.sync-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.btn-sync {
  padding: 9px 20px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-sync:disabled {
  opacity: 0.5;
  cursor: default;
}
.batch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font: 400 13px/1 var(--font-ui);
  color: var(--ink-3);
}
.batch-input {
  width: 80px;
  padding: 6px 8px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--ink);
  font: 400 13px/1 var(--font-mono);
}
.enrich-result.ok {
  color: var(--pos-ink);
  font-size: 13px;
}
.enrich-result.err {
  color: var(--neg-ink);
  font-size: 13px;
}
.filter-group {
  display: flex;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.filter-btn {
  padding: 6px 12px;
  border: none;
  background: var(--surface);
  color: var(--ink-3);
  font: 500 11px/1 var(--font-ui);
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
  font-size: 13px;
}
.flag-table thead th {
  text-align: left;
  padding: 0 12px 10px;
  font: 500 10px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.flag-table tbody td {
  padding: 10px 12px;
  vertical-align: top;
  border-bottom: 1px solid var(--line);
}
.flag-table tbody tr:last-child td {
  border-bottom: none;
}
.raw-string {
  font: 500 13px/1.3 var(--font-ui);
  color: var(--ink);
}
.token-pill {
  font: 400 11px/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: 3px 7px;
  border-radius: 4px;
  white-space: nowrap;
}
.state {
  font-size: 13px;
  color: var(--ink-3);
  font-style: italic;
  padding: 12px 0;
}
.mono {
  font-family: var(--font-mono);
}
.muted {
  color: var(--ink-3);
}

/* Genre mappings */
.mapping-search-wrap {
  position: relative;
}
.mapping-search-input {
  width: 100%;
  padding: 5px 8px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  font: 400 12px/1 var(--font-ui);
  box-sizing: border-box;
}
.mapping-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 10;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  box-shadow: 0 4px 12px oklch(0 0 0 / 0.15);
  max-height: 200px;
  overflow-y: auto;
  margin-top: 2px;
}
.mapping-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  cursor: pointer;
  transition: background 0.1s;
}
.mapping-option:hover {
  background: var(--surface-2);
}
.mapping-option.selected {
  background: var(--accent-soft);
}
.mapping-option-label {
  font: 400 12px/1.3 var(--font-ui);
  color: var(--ink);
}
.mapping-option-qid {
  font-size: 10px;
  color: var(--ink-3);
}
</style>
