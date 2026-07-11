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
              <span v-else class="muted" style="font-size: var(--fs-sm); color: var(--ink-3)">—</span>
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
                style="padding: var(--space-1) var(--space-3); font-size: var(--fs-xs)"
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
    // `data.total` is the full matching count (independent of the page limit):
    // the unmapped total in "unmapped" mode, the grand total otherwise.
    return data.total
  } finally {
    loadingMappings.value = false
  }
}

// Badge counts. When `known` supplies one side (derived from the main mappings
// fetch), only the missing side is queried — 1 call instead of 2.
async function fetchMappingStats(known = null) {
  try {
    if (known && 'total' in known) {
      const unmapped = await api.get('/api/taxonomy/mappings', {
        params: { unmapped: true, limit: 1 },
      })
      mappingStats.value = { total: known.total, unmapped: unmapped.data.total }
    } else if (known && 'unmapped' in known) {
      const all = await api.get('/api/taxonomy/mappings', { params: { limit: 1 } })
      mappingStats.value = { total: all.data.total, unmapped: known.unmapped }
    } else {
      const [all, unmapped] = await Promise.all([
        api.get('/api/taxonomy/mappings', { params: { limit: 1 } }),
        api.get('/api/taxonomy/mappings', { params: { unmapped: true, limit: 1 } }),
      ])
      mappingStats.value = { total: all.data.total, unmapped: unmapped.data.total }
    }
  } catch {
    // silent — the badge is non-critical
  }
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

onMounted(async () => {
  const total = await fetchMappings()
  if (typeof total === 'number') {
    await fetchMappingStats(mappingShowUnmapped.value ? { unmapped: total } : { total })
  } else {
    await fetchMappingStats()
  }
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
  margin-bottom: var(--space-15);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.section-header .section-title {
  margin-bottom: 0;
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
.sync-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.btn-sync {
  padding: var(--space-2) var(--space-5);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 var(--fs-sm)/1 var(--font-ui);
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
  gap: var(--space-2);
  font: 400 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-3);
}
.batch-input {
  width: 80px;
  padding: var(--space-15) var(--space-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--ink);
  font: 400 var(--fs-sm)/1 var(--font-mono);
}
.enrich-result.ok {
  color: var(--pos-ink);
  font-size: var(--fs-sm);
}
.enrich-result.err {
  color: var(--neg-ink);
  font-size: var(--fs-sm);
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

/* Genre mappings */
.mapping-search-wrap {
  position: relative;
}
.mapping-search-input {
  width: 100%;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  font: 400 var(--fs-sm)/1 var(--font-ui);
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
  margin-top: var(--space-05);
}
.mapping-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-15) var(--space-25);
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
  font: 400 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
}
.mapping-option-qid {
  font-size: var(--fs-xs);
  color: var(--ink-3);
}
</style>
