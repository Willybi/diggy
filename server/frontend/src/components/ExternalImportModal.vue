<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal-box">
      <div class="modal-head">
        <h2 class="modal-title">Ajouter un track</h2>
        <button class="close-btn" type="button" aria-label="Fermer" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
          </svg>
        </button>
      </div>

      <SearchBox
        v-model="query"
        placeholder="Rechercher un track (Deezer, TIDAL)…"
        @update:modelValue="onQuery"
      />

      <div class="results-body">
        <!-- invite -->
        <div v-if="phase === 'idle'" class="state">
          Recherchez un track à ajouter à votre catalog.
        </div>

        <!-- loading -->
        <div v-else-if="phase === 'loading'" class="state">
          <div class="spinner"></div>
          <p class="state-label">Recherche…</p>
        </div>

        <!-- error -->
        <div v-else-if="phase === 'error'" class="state state--error">
          {{ errorMsg }}
        </div>

        <!-- empty -->
        <div v-else-if="phase === 'empty'" class="state">Aucun résultat pour « {{ query }} ».</div>

        <!-- results -->
        <ul v-else class="rlist">
          <li v-for="item in results" :key="resultKey(item)" class="rrow">
            <span class="art">
              <img
                v-if="item.artwork_url && !failedArt.has(resultKey(item))"
                :src="item.artwork_url"
                alt=""
                loading="lazy"
                @error="onArtError(item)"
              />
              <span v-else class="art-ini">{{ initials(item) }}</span>
            </span>

            <span class="tx">
              <span class="title" :title="item.title">{{ item.title }}</span>
              <span class="artist" :title="item.artist || ''">{{ item.artist || '—' }}</span>
            </span>

            <SourceBadge :source="item.source" />

            <span class="action">
              <!-- already in catalog (server) or freshly imported -->
              <RouterLink
                v-if="targetCatalogId(item)"
                class="in-catalog"
                :to="`/catalog/${targetCatalogId(item)}`"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                  <path d="M5 12l5 5 9-11" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
                Dans le catalog
              </RouterLink>

              <!-- import error on this row -->
              <span v-else-if="stateOf(item) === 'error'" class="row-error">
                <span class="row-error-msg">{{ importError[resultKey(item)] }}</span>
                <button class="btn-import" type="button" @click="importItem(item)">Réessayer</button>
              </span>

              <!-- importable -->
              <button
                v-else
                class="btn-import"
                type="button"
                :disabled="stateOf(item) === 'importing'"
                @click="importItem(item)"
              >
                <span v-if="stateOf(item) === 'importing'" class="btn-spinner"></span>
                <span v-else>Importer</span>
              </button>
            </span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { RouterLink } from 'vue-router'
import api from '../utils/api.js'
import SearchBox from './SearchBox.vue'
import SourceBadge from './SourceBadge.vue'

const emit = defineEmits(['close', 'imported'])

const query = ref('')
const phase = ref('idle') // idle | loading | error | empty | results
const results = ref([])
const errorMsg = ref('')

const failedArt = reactive(new Set())
// Per-row import lifecycle, keyed by resultKey.
const rowState = reactive({}) // key -> 'importing' | 'done' | 'error'
const importedId = reactive({}) // key -> catalog_id after a successful import
const importError = reactive({}) // key -> message

let searchToken = 0

function resultKey(item) {
  return `${item.source}:${item.external_id}`
}

function stateOf(item) {
  return rowState[resultKey(item)] || 'idle'
}

// A row shows "in catalog" if the server already knew it, or we just imported it.
function targetCatalogId(item) {
  return item.catalog_id || importedId[resultKey(item)] || null
}

function initials(item) {
  const base = item.artist || item.title || '?'
  return base.trim().charAt(0).toUpperCase() || '?'
}

function onArtError(item) {
  failedArt.add(resultKey(item))
}

async function onQuery(q) {
  query.value = q
  const trimmed = (q || '').trim()
  if (!trimmed) {
    phase.value = 'idle'
    results.value = []
    return
  }

  const token = ++searchToken
  phase.value = 'loading'
  try {
    const { data } = await api.get('/api/search/external', { params: { q: trimmed } })
    if (token !== searchToken) return // a newer search superseded this one
    results.value = data.items || []
    phase.value = results.value.length ? 'results' : 'empty'
  } catch {
    if (token !== searchToken) return
    errorMsg.value = 'La recherche a échoué, réessayez.'
    phase.value = 'error'
  }
}

async function importItem(item) {
  const key = resultKey(item)
  rowState[key] = 'importing'
  delete importError[key]

  const body = item.source === 'deezer' ? { deezer_id: item.external_id } : { tidal_id: item.external_id }

  try {
    const { data } = await api.post('/api/catalog/import', body)
    importedId[key] = data.catalog_id
    rowState[key] = 'done'
    // Emit on each success so the parent can refresh its listing.
    emit('imported', data)
  } catch (err) {
    rowState[key] = 'error'
    importError[key] =
      err.response?.status === 404 ? 'Track introuvable sur la source' : 'Import échoué'
  }
}
</script>

<style scoped>
/* ============ OVERLAY ============ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: var(--space-6);
}

/* ============ BOX ============ */
.modal-box {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 560px;
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.modal-title {
  margin: 0;
  font: 600 var(--fs-md)/1.2 var(--font-ui);
  color: var(--ink);
}

.close-btn {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  color: var(--ink-3);
  display: grid;
  place-items: center;
  flex: none;
}
.close-btn:hover {
  color: var(--ink);
}
.close-btn svg {
  width: 18px;
  height: 18px;
}

/* ============ RESULTS BODY ============ */
.results-body {
  min-height: 240px;
  max-height: 56vh;
  overflow-y: auto;
}

.rlist {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.rrow {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-25);
  border-radius: var(--r-sm);
}
.rrow:hover {
  background: var(--surface-2);
}

/* ============ ARTWORK ============ */
.art {
  width: 44px;
  height: 44px;
  border-radius: var(--r-xs);
  flex: none;
  background: var(--surface-3);
  overflow: hidden;
  display: grid;
  place-items: center;
}
.art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.art-ini {
  font: 600 var(--fs-base) var(--font-ui);
  color: var(--ink-3);
}

/* ============ TEXT ============ */
.tx {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.title {
  font: 500 var(--fs-table) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.artist {
  font: 400 var(--fs-table-sm) var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============ ACTION ZONE ============ */
.action {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 116px;
}

.btn-import {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 90px;
  height: 34px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
}
.btn-import:hover:not(:disabled) {
  background: var(--accent-hover);
}
.btn-import:disabled {
  opacity: 0.7;
  cursor: default;
}

.in-catalog {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  text-decoration: none;
  font: 600 var(--fs-sm)/1 var(--font-ui);
  color: var(--pos-ink);
}
.in-catalog:hover {
  text-decoration: underline;
}
.in-catalog svg {
  width: 15px;
  height: 15px;
  flex: none;
}

.row-error {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.row-error-msg {
  font: 500 var(--fs-xs) var(--font-ui);
  color: var(--neg-ink);
  white-space: nowrap;
}

/* ============ SPINNERS ============ */
.spinner {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 3px solid var(--line-2);
  border-top-color: var(--accent);
  animation: spin 0.75s linear infinite;
}
.btn-spinner {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 2px solid var(--on-accent);
  border-top-color: transparent;
  animation: spin 0.7s linear infinite;
}

/* ============ STATES ============ */
.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: 240px;
  text-align: center;
  font: 400 var(--fs-base)/1.5 var(--font-ui);
  color: var(--ink-3);
}
.state--error {
  color: var(--neg-ink);
}
.state-label {
  margin: 0;
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
}

/* ============ MOBILE ============ */
@media (max-width: 640px) {
  .modal-overlay {
    padding: 0;
  }
  .modal-box {
    max-width: 100%;
    height: 100%;
    border-radius: 0;
    padding: var(--space-5) var(--page-px-mobile);
  }
  .results-body {
    max-height: none;
    flex: 1;
  }
}
</style>
