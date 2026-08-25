<template>
  <section class="admin-section">
    <div class="section-header">
      <h2 class="section-title">
        Flags artistes
        <span v-if="total" class="flag-count">{{ total }}</span>
      </h2>
      <div class="filter-group">
        <button
          v-for="s in ['pending', 'validated', 'skipped']"
          :key="s"
          class="filter-btn"
          :class="{ active: filterStatus === s }"
          @click="setFilter(s)"
        >
          {{ s }}
        </button>
      </div>
    </div>

    <div v-if="loadingFlags" class="state">Chargement…</div>
    <div v-else-if="flags.length === 0" class="state">Aucun flag {{ filterStatus }}.</div>

    <div v-else class="table-wrap">
      <table class="flag-table">
        <thead>
          <tr>
            <th class="col-raw">String brute</th>
            <th class="col-reason">Raison</th>
            <th class="col-tokens">Tokens détectés</th>
            <th class="col-deezer">Deezer</th>
            <th class="col-action" />
          </tr>
        </thead>
        <tbody>
          <template v-for="flag in flags" :key="flag.id">
            <tr :class="{ resolved: flag.status !== 'pending' }">
              <td class="col-raw" data-label="String brute">
                <span class="raw-string">{{ flag.raw_artist_string }}</span>
              </td>
              <td class="col-reason" data-label="Raison">
                <span class="reason-badge" :class="flag.reason">{{ flag.reason }}</span>
              </td>
              <td class="col-tokens" data-label="Tokens détectés">
                <div class="token-list">
                  <span v-for="t in flag.tokens" :key="t" class="token-pill">{{ t }}</span>
                </div>
              </td>
              <td class="col-deezer" data-label="Deezer">
                <div class="deezer-list">
                  <span
                    v-for="name in flag.tokens"
                    :key="name"
                    class="deezer-entry"
                    :class="{
                      found: dz(name)?.status === 'found',
                      missing: dz(name)?.status === 'missing',
                    }"
                  >
                    <span class="deezer-name">{{ name }}</span>
                    <span v-if="dz(name)?.status === 'searching'" class="dz-spin" />
                    <a
                      v-else-if="dz(name)?.status === 'found'"
                      :href="`https://www.deezer.com/artist/${dz(name).hit.deezer_id}`"
                      target="_blank"
                      class="deezer-id mono dz-link"
                      :title="`${dz(name).hit.name} · ${dz(name).hit.nb_fan?.toLocaleString()} fans`"
                      >✓ {{ dz(name).hit.nb_fan?.toLocaleString() }}</a
                    >
                    <span v-else-if="dz(name)?.status === 'missing'" class="deezer-id mono">✗</span>
                    <span v-else class="deezer-id mono muted">—</span>
                  </span>
                </div>
              </td>
              <td class="col-action">
                <template v-if="flag.status === 'pending'">
                  <div class="action-btns">
                    <button
                      class="btn-split"
                      :disabled="resolving[flag.id]"
                      :class="{ open: editingFlagId === flag.id }"
                      title="Éditer les segments puis splitter"
                      @click="toggleEditor(flag)"
                    >
                      Splitter…
                    </button>
                    <button
                      class="btn-keep"
                      :disabled="resolving[flag.id]"
                      :title="`Créer: ${flag.raw_artist_string}`"
                      @click="resolve(flag.id, 'keep')"
                    >
                      Garder
                    </button>
                    <button
                      class="btn-skip"
                      :disabled="resolving[flag.id]"
                      @click="resolve(flag.id, 'skip')"
                    >
                      Ignorer
                    </button>
                  </div>
                </template>
                <template v-else>
                  <span class="status-badge" :class="flag.status">{{ flag.status }}</span>
                </template>
              </td>
            </tr>
            <tr v-if="editingFlagId === flag.id" class="editor-row">
              <td :colspan="5">
                <ArtistSegmentSplitter
                  :key="flag.id"
                  :raw="flag.raw_artist_string"
                  :pending="!!resolving[flag.id]"
                  :error="editError"
                  @confirm="onSplitConfirm(flag, $event)"
                  @cancel="closeEditor"
                />
              </td>
            </tr>
          </template>
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
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import api from '../../utils/api.js'
import { foldArtistName } from '../../utils/artistSplit.js'
import ArtistSegmentSplitter from './ArtistSegmentSplitter.vue'

const PER_PAGE = 25

const flags = ref([])
const total = ref(0)
const page = ref(1)
const loadingFlags = ref(false)
const filterStatus = ref('pending')
const resolving = reactive({})
const editingFlagId = ref(null)
const editError = ref('')

const totalPages = computed(() => Math.ceil(total.value / PER_PAGE))

async function fetchFlags() {
  loadingFlags.value = true
  try {
    const { data } = await api.get('/api/admin/artists/flags', {
      params: { status: filterStatus.value, page: page.value, per_page: PER_PAGE },
    })
    flags.value = data.items
    total.value = data.total
    queueDeezer(flags.value.flatMap((f) => f.tokens || []))
  } finally {
    loadingFlags.value = false
  }
}

async function setFilter(s) {
  filterStatus.value = s
  page.value = 1
  await fetchFlags()
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  fetchFlags()
}

function nextPage() {
  if (page.value >= totalPages.value) return
  page.value++
  fetchFlags()
}

// ── Live Deezer signal per token (display only) ───────────────────────────────
// The flag.deezer_ids snapshot is only filled by the sync_artists worker; flags
// created manually or by the auto_split backfill carry an empty map. So we search
// Deezer live for every token on the page (reusing the admin search endpoint the
// splitter uses) and show ✓/✗ so the admin decides "split or keep" with eyes open.
// Cached by token text (searched at most once across pages) and processed
// sequentially to stay gentle on the admin Deezer rate bucket.
const DEEZER_DEBOUNCE_MS = 400
const deezerByText = ref({})
const deezerQueue = new Set()
let deezerTimer = null

const dz = (text) => deezerByText.value[text]

function queueDeezer(texts) {
  let queued = false
  for (const raw of texts) {
    const text = (raw || '').trim()
    if (!text || deezerByText.value[text]) continue
    deezerByText.value[text] = { status: 'searching', hit: null }
    deezerQueue.add(text)
    queued = true
  }
  if (!queued) return
  clearTimeout(deezerTimer)
  deezerTimer = setTimeout(flushDeezerQueue, DEEZER_DEBOUNCE_MS)
}

async function flushDeezerQueue() {
  const texts = [...deezerQueue]
  deezerQueue.clear()
  // Sequential: 25 flags × ~2 tokens fired at once would trip the 429 bucket.
  for (const text of texts) {
    await searchDeezer(text)
  }
}

// "Found" = a hit whose name folds equal to the token (Deezer returns fuzzy hits
// for anything, so a non-empty list alone proves nothing — same rule as the splitter).
async function searchDeezer(text) {
  try {
    const { data } = await api.get('/api/admin/artists/search-deezer', { params: { q: text } })
    const hit = (data || []).find((h) => foldArtistName(h.name) === foldArtistName(text)) || null
    deezerByText.value[text] = { status: hit ? 'found' : 'missing', hit }
  } catch {
    // 429 / network errors are toasted by the api interceptor; leave the entry so
    // a false ✗ never shows — a neutral "—" reads as "not checked".
    deezerByText.value[text] = { status: 'error', hit: null }
  }
}

onUnmounted(() => clearTimeout(deezerTimer))

function applyResolved(flagId, data) {
  const idx = flags.value.findIndex((f) => f.id === flagId)
  if (idx !== -1) flags.value[idx] = data
  if (filterStatus.value === 'pending') {
    flags.value = flags.value.filter((f) => f.status === 'pending')
    total.value = Math.max(0, total.value - 1)
  }
}

async function resolve(flagId, action) {
  resolving[flagId] = true
  try {
    const { data } = await api.post(`/api/admin/artists/flags/${flagId}/resolve`, { action })
    applyResolved(flagId, data)
  } finally {
    resolving[flagId] = false
  }
}

function toggleEditor(flag) {
  editError.value = ''
  editingFlagId.value = editingFlagId.value === flag.id ? null : flag.id
}

function closeEditor() {
  editingFlagId.value = null
}

// Upsert the flag with the EDITED tokens (keeping its original `reason` so its
// category is preserved and any already-found deezer_ids are retained by the
// backend upsert), then resolve it as a split. raw_artist_string stays verbatim.
async function onSplitConfirm(flag, tokens) {
  if (!tokens.length) return
  resolving[flag.id] = true
  editError.value = ''
  try {
    await api.post('/api/admin/artists/flags/manual', {
      raw_artist_string: flag.raw_artist_string,
      tokens,
      reason: flag.reason,
    })
    const { data } = await api.post(`/api/admin/artists/flags/${flag.id}/resolve`, {
      action: 'split',
    })
    editingFlagId.value = null
    applyResolved(flag.id, data)
  } catch (e) {
    editError.value = e.response?.data?.detail || 'Erreur lors du split'
  } finally {
    resolving[flag.id] = false
  }
}

onMounted(() => {
  fetchFlags()
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
.flag-table tbody tr.resolved td {
  opacity: 0.5;
}
.col-raw {
  min-width: 180px;
}
.col-reason {
  width: 160px;
}
.col-tokens {
  width: 200px;
}
.col-deezer {
  width: 220px;
}
.col-action {
  width: 200px;
  text-align: right;
}
.raw-string {
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
}
.reason-badge {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  white-space: nowrap;
}
.reason-badge.comma_unresolved {
  background: var(--warn-soft);
  color: var(--warn-ink);
}
.reason-badge.ampersand_ambiguous {
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.reason-badge.ampersand_unknown,
.reason-badge.auto_split,
.reason-badge.manual {
  background: var(--surface-2);
  color: var(--ink-3);
}
.token-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.token-pill {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  white-space: nowrap;
}
.deezer-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.deezer-entry {
  display: flex;
  gap: var(--space-15);
  align-items: baseline;
}
.deezer-name {
  font-size: var(--fs-xs);
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100px;
}
.deezer-id {
  font-size: var(--fs-xs);
}
.deezer-entry.found .deezer-id {
  color: var(--pos-ink);
}
.deezer-entry.missing .deezer-id {
  color: var(--neg-ink);
}
.dz-spin {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--line-2);
  border-top-color: var(--accent);
  animation: spin 0.7s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .dz-spin {
    animation: none;
  }
}
.action-btns {
  display: flex;
  gap: var(--space-1);
  justify-content: flex-end;
  flex-wrap: wrap;
}
.btn-split,
.btn-keep,
.btn-skip {
  padding: var(--space-1) var(--space-25);
  border-radius: var(--r-sm);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.12s;
}
.btn-split:disabled,
.btn-keep:disabled,
.btn-skip:disabled {
  opacity: 0.4;
  cursor: default;
}
.btn-split {
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.btn-split:hover:not(:disabled),
.btn-split.open {
  background: var(--accent);
  color: var(--on-accent);
}
.btn-keep {
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
}
.btn-keep:hover:not(:disabled) {
  background: var(--surface-2);
}
.btn-skip {
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
}
.btn-skip:hover:not(:disabled) {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}
.status-badge {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  padding: var(--space-05) var(--space-2);
  border-radius: 4px;
}
.status-badge.validated {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.status-badge.skipped {
  background: var(--surface-2);
  color: var(--ink-3);
}
.editor-row td {
  padding: var(--space-2) var(--space-3) var(--space-3);
  background: var(--surface-2);
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
.dz-link {
  color: var(--accent-ink);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}
.dz-link:hover {
  text-decoration: underline;
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

/* ============ RESPONSIVE — table→cartes (palier aligné sur ExplorerView) ============ */
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
  .col-raw,
  .col-reason,
  .col-tokens,
  .col-deezer,
  .col-action {
    width: auto;
    min-width: 0;
  }
  .raw-string {
    font-size: var(--fs-base);
  }
  .deezer-name {
    max-width: none;
  }
  .col-action {
    margin-top: var(--space-1);
    text-align: left;
  }
  .action-btns {
    flex-direction: column;
    gap: var(--space-15);
  }
  .btn-split,
  .btn-keep,
  .btn-skip {
    width: 100%;
    padding: var(--space-2) var(--space-25);
  }
  .flag-table tbody tr.editor-row {
    margin-top: var(--space-1);
    background: var(--surface-2);
  }
  .flag-table tbody tr.editor-row td {
    padding: 0;
    background: transparent;
  }
}
</style>
