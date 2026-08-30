<template>
  <!-- Archétype A (D4) : reclassifier tous les genres — une région, un job. -->
  <section class="aj-region">
    <div class="aj-head">
      <h2 class="aj-title">Jobs genres <span class="aj-count">1</span></h2>
      <span class="aj-eyebrow">Reclassification</span>
    </div>
    <div class="aj-row">
      <div class="aj-body">
        <h3 class="aj-job-title">Reclassifier tous les genres</h3>
        <p class="aj-job-desc">
          Efface tous les genres et re-fetche : Deezer (album) d'abord, fallback Beatport.
          <span class="aj-num">~5 200</span> tracks, peut prendre plusieurs heures.
        </p>
        <div v-if="reclassifyResult" class="aj-result">
          <span v-if="reclassifyResult.ok" class="aj-pair aj-pair--success">
            <AdminIcon name="check" :size="13" />
            <span class="aj-lbl">{{ reclassifyLabel }}</span>
            <span class="aj-task-id">{{ reclassifyResult.taskId.slice(0, 8) }}…</span>
          </span>
          <span v-else class="aj-fail">
            <AdminIcon name="alert-triangle" :size="13" />
            <span class="aj-fail-word">Échec</span>
            <span class="aj-fail-msg">{{ reclassifyResult.message }}</span>
          </span>
        </div>
      </div>
      <div class="aj-action">
        <label class="aj-field">
          <span class="aj-field-label">Planifier à</span>
          <input v-model="reclassifyEta" type="datetime-local" class="aj-input" />
        </label>
        <button class="btn btn--sm btn--accent" :disabled="reclassifying" @click="runReclassify">
          {{ reclassifying ? 'En cours…' : reclassifyEta ? 'Planifier' : 'Lancer maintenant' }}
        </button>
      </div>
    </div>
  </section>

  <!-- Archétype B (D1) : mappings genres au socle .at-* + recherche de node inline (D9). -->
  <section class="gm-wrap">
    <div class="at-region">
      <div class="at-head">
        <h2 class="at-title">
          Mappings genres
          <span v-if="mappingStats" class="at-count"
            >{{ mappingStats.unmapped }} / {{ mappingStats.total }} non mappés</span
          >
        </h2>
        <div class="at-seg">
          <button
            class="at-seg-b"
            :class="{ active: !mappingShowUnmapped }"
            @click="showAllMappings()"
          >
            Tous
          </button>
          <button
            class="at-seg-b"
            :class="{ active: mappingShowUnmapped }"
            @click="showUnmappedOnly()"
          >
            Non mappés
          </button>
        </div>
      </div>
      <p class="gm-caption">
        Associe les noms de genres bruts (Beatport/Deezer) aux nœuds de la taxonomie Wikidata.
      </p>

      <div v-if="loadingMappings" class="at-empty">Chargement…</div>
      <div v-else-if="mappings.length === 0" class="at-empty">Aucun mapping.</div>

      <div v-else class="at-scroll">
        <table class="at-table">
          <thead>
            <tr>
              <th>Nom brut</th>
              <th>Nœud taxonomie</th>
              <th>Statut</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in mappings" :key="m.id">
              <td data-label="Nom brut" data-lead>
                <span class="at-id">{{ m.rawName }}</span>
              </td>
              <td data-label="Nœud taxonomie" data-stack>
                <div class="gm-node">
                  <span v-if="m.nodeLabel" class="gm-node-label">{{ m.nodeLabel }}</span>
                  <span v-else class="gm-node-empty">—</span>
                  <span v-if="m.nodeWikidataId" class="gm-node-qid">{{ m.nodeWikidataId }}</span>
                </div>
              </td>
              <td data-label="Statut">
                <span class="at-pill" :class="m.nodeLabel ? 'at-pill--ok' : 'at-pill--neutral'">{{
                  m.nodeLabel ? 'Mappé' : 'Non mappé'
                }}</span>
              </td>
              <td data-act>
                <button
                  class="btn btn--sm gm-search-btn"
                  :class="{ 'is-open': activeSearchId === m.id }"
                  @click="toggleSearch(m)"
                >
                  <AdminIcon name="search" :size="15" />
                  Chercher un node
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Recherche de node inline (D9) : dépliée sous la table, --surface-2 + filet haut. -->
      <div v-if="activeMapping" class="gm-search">
        <span class="gm-search-eyebrow">
          Chercher un node · <span class="gm-search-raw">{{ activeMapping.rawName }}</span>
        </span>
        <input
          v-model="mappingSearch[activeMapping.id]"
          class="gm-search-input"
          placeholder="Chercher un node…"
          @input="onMappingSearch(activeMapping.id)"
        />
        <div v-if="mappingResults[activeMapping.id]?.length" class="gm-hits">
          <button
            v-for="n in mappingResults[activeMapping.id]"
            :key="n.id"
            type="button"
            class="gm-hit"
            :class="{ selected: mappingSelected[activeMapping.id] === n.id }"
            @click="selectMappingOption(activeMapping, n)"
          >
            <span class="gm-hit-label">{{ n.label }}</span>
            <span class="gm-hit-qid">{{ n.wikidataId }}</span>
          </button>
        </div>
        <div class="gm-search-actions">
          <button class="btn btn--sm" @click="closeSearch">Annuler</button>
          <button
            class="btn btn--sm btn--accent"
            :disabled="!mappingSelected[activeMapping.id] || savingMapping[activeMapping.id]"
            @click="saveMapping(activeMapping)"
          >
            {{ savingMapping[activeMapping.id] ? '…' : 'Associer' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import AdminIcon from './AdminIcon.vue'

const reclassifying = ref(false)
const reclassifyEta = ref('')
// { ok: true, taskId, when } on success · { ok: false, message } on error.
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

// Recherche de node inline (D9) : un seul panneau sous la table, rattaché à la
// rangée dont l'action « Chercher un node » est ouverte.
const activeSearchId = ref(null)
const activeMapping = computed(
  () => mappings.value.find((m) => m.id === activeSearchId.value) || null,
)

// Ligne de résultat du job de reclassify (D3, canal succès) : le job renvoie un
// task_id sans polling → confirmation simple, jamais de suivi de tâche.
const reclassifyLabel = computed(() => {
  if (!reclassifyResult.value?.ok) return ''
  const when = reclassifyResult.value.when
  return when ? `Tâche planifiée · ${when}` : 'Tâche planifiée'
})

function showAllMappings() {
  mappingShowUnmapped.value = false
  activeSearchId.value = null
  fetchMappings()
}

function showUnmappedOnly() {
  mappingShowUnmapped.value = true
  activeSearchId.value = null
  fetchMappings()
}

function toggleSearch(m) {
  activeSearchId.value = activeSearchId.value === m.id ? null : m.id
}

function closeSearch() {
  activeSearchId.value = null
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
    reclassifyResult.value = { ok: true, taskId: data.task_id, when: reclassifyEta.value }
  } catch (e) {
    reclassifyResult.value = { ok: false, message: e.response?.data?.detail || 'Erreur' }
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
    activeSearchId.value = null
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
.aj-region,
.gm-wrap {
  container-type: inline-size;
}

/* ── Archétype A — région de job (D4) : carte à bordure, sans ombre. ── */
.aj-region {
  margin-bottom: var(--space-8);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.aj-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
.aj-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.aj-count {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--r-pill);
  background: var(--surface-3);
  color: var(--ink-2);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.04em;
}
.aj-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.aj-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  padding: var(--space-4);
}
.aj-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.aj-job-title {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.aj-job-desc {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
  text-wrap: pretty;
  max-width: 76ch;
}
/* Nombres de la description en mono (grille d'audit). */
.aj-num {
  font-family: var(--font-mono);
  color: var(--ink);
}

/* Champ + bouton, colonne d'action à droite. */
.aj-action {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 190px;
}
.aj-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.aj-field-label {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.aj-input {
  height: 38px;
  padding: 0 var(--space-2);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink);
  font: 400 var(--fs-input)/1 var(--font-mono);
}
.aj-input:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}

/* Ligne de résultat (D3) : paire icône + label, canal succès / erreur. */
.aj-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-15);
}
.aj-pair {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
.aj-pair--success {
  color: var(--pos-ink);
}
.aj-lbl {
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-3);
}
.aj-task-id {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.aj-fail {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--neg-ink);
}
.aj-fail-word {
  font: 600 var(--fs-xs)/1 var(--font-ui);
}
.aj-fail-msg {
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-2);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  max-width: 340px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Archétype B — mappings genres (socle .at-*). ── */
.gm-wrap {
  margin-bottom: var(--space-8);
}
/* Intro de la région : sous l'en-tête, au-dessus de la table. */
.gm-caption {
  padding: var(--space-2) var(--space-4);
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
}

/* Cellule node : label + wikidataId empilés (colonne [data-stack]). */
.gm-node {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
  min-width: 0;
}
.gm-node-label {
  font: 500 var(--fs-table-sm)/1.35 var(--font-ui);
  color: var(--ink);
}
.gm-node-empty {
  font: 400 var(--fs-table-sm)/1.35 var(--font-ui);
  color: var(--ink-3);
}
.gm-node-qid {
  font: 400 var(--fs-nano)/1.3 var(--font-mono);
  color: var(--ink-3);
}

/* Bouton d'action de rangée : neutre, icône + libellé. */
.gm-search-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  white-space: nowrap;
}

/* Recherche de node inline (D9) : bloc --surface-2 + filet haut sous la table. */
.gm-search {
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2);
  border-top: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.gm-search-eyebrow {
  font: 600 var(--fs-nano)/1.3 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.gm-search-raw {
  color: var(--ink);
  text-transform: none;
}
.gm-search-input {
  width: 100%;
  max-width: 420px;
  height: 38px;
  padding: 0 var(--space-3);
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink);
  font: 400 var(--fs-input)/1 var(--font-ui);
}
.gm-search-input:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}
.gm-hits {
  display: flex;
  flex-direction: column;
  max-width: 420px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface);
  overflow: hidden;
}
.gm-hit {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-15) var(--space-25);
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.1s;
}
.gm-hit + .gm-hit {
  border-top: 1px solid var(--line);
}
.gm-hit:hover {
  background: var(--surface-2);
}
.gm-hit.selected {
  background: var(--accent-soft);
}
.gm-hit-label {
  font: 500 var(--fs-base)/1.3 var(--font-ui);
  color: var(--ink);
}
.gm-hit-qid {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
  flex: none;
}
.gm-search-actions {
  display: flex;
  gap: var(--space-2);
}

/* ── Responsive — palier unique 859 px (D14/D18). ── */
@container (max-width: 859px) {
  .aj-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .aj-row {
    flex-direction: column;
    gap: var(--space-3);
  }
  .aj-action {
    width: 100%;
    min-width: 0;
  }
  .aj-action .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  .aj-input {
    height: var(--touch-min);
  }
  .aj-fail-msg {
    max-width: none;
  }

  .gm-search-input {
    height: var(--touch-min);
    max-width: none;
  }
  .gm-hits {
    max-width: none;
  }
  .gm-hit {
    min-height: var(--touch-min);
  }
  .gm-search-actions .btn {
    flex: 1;
    min-height: var(--touch-min);
    justify-content: center;
  }
}
</style>
