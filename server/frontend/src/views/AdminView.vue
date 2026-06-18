<template>
  <div class="admin-view">
    <header class="view-header">
      <h1 class="view-title">Admin</h1>
    </header>

    <!-- Sync artistes -->
    <section class="admin-section">
      <h2 class="section-title">Sync artistes</h2>
      <p class="section-sub">Parse les noms d'artistes du catalog et peuple la table artistes. Idempotent.</p>
      <div class="sync-row">
        <button class="btn-sync" :disabled="syncing" @click="runSync">
          {{ syncing ? 'Sync en cours… (peut prendre ~5-10 min)' : 'Lancer la sync' }}
        </button>
        <div v-if="syncResult" class="sync-result">
          <span class="result-item ok">✓ {{ syncResult.created }} créés</span>
          <span class="result-item warn">⚠ {{ syncResult.flagged }} flags</span>
          <span class="result-item muted">↷ {{ syncResult.skipped }} skippés</span>
        </div>
        <span v-if="syncError" class="sync-error">{{ syncError }}</span>
      </div>
    </section>

    <!-- Fetch artworks -->
    <section class="admin-section">
      <h2 class="section-title">Artworks artistes</h2>
      <p class="section-sub">Fetche les images Deezer pour tous les artistes avec un deezer_id. Idempotent.</p>
      <div class="sync-row">
        <button class="btn-sync" :disabled="fetchingArtworks" @click="runFetchArtworks">
          {{ fetchingArtworks ? 'Fetch en cours…' : 'Fetch artworks' }}
        </button>
        <div v-if="artworksResult" class="sync-result">
          <span class="result-item ok">✓ {{ artworksResult.fetched }} artworks</span>
          <span v-if="artworksResult.linked != null" class="result-item ok">🔗 {{ artworksResult.linked }} liés Deezer</span>
          <span class="result-item muted">↷ {{ artworksResult.skipped }} skippés</span>
        </div>
        <span v-if="artworksError" class="sync-error">{{ artworksError }}</span>
      </div>
    </section>

    <!-- Liaison manuelle artiste ↔ Deezer -->
    <section class="admin-section">
      <h2 class="section-title">Lier un artiste à Deezer</h2>
      <p class="section-sub">Recherche un artiste dans la DB et l'associe manuellement à un compte Deezer.</p>
      <div class="link-form">
        <input v-model="linkArtistQuery" class="form-input" placeholder="Filtrer les artistes sans Deezer…" @input="onLinkSearch" />
        <input v-model="linkDeezerQuery" class="form-input" placeholder="Recherche sur Deezer…" @input="onDeezerSearch" />
      </div>
      <div class="link-results">
        <div class="link-col">
          <p class="col-label">Artistes sans deezer_id ({{ dbArtistResults.length }})</p>
          <div class="link-list">
            <div v-for="a in dbArtistResults" :key="a.id"
              class="result-row" :class="{ selected: selectedDbArtist?.id === a.id }"
              @click="selectedDbArtist = a; linkDeezerQuery = a.name; onDeezerSearch()"
            >
              <div class="cover-thumb-sm">
                <img v-if="a.has_artwork" :src="`/storage/artist-artworks/${a.id}.jpg`" />
                <span v-else class="fallback-sm">{{ a.name[0] }}</span>
              </div>
              <span class="ar-name-sm">{{ a.name }}</span>
            </div>
          </div>
        </div>
        <div class="link-col">
          <p class="col-label">Résultats Deezer</p>
          <div class="link-list">
            <div v-for="h in deezerHits" :key="h.deezer_id"
              class="result-row" :class="{ selected: selectedDeezerHit?.deezer_id === h.deezer_id }"
              @click="selectedDeezerHit = h"
            >
              <div class="cover-thumb-sm">
                <img v-if="h.picture" :src="h.picture" />
                <span v-else class="fallback-sm">{{ h.name[0] }}</span>
              </div>
              <div>
                <span class="ar-name-sm">{{ h.name }}</span>
                <span class="ar-meta mono muted">
                  {{ h.nb_fan?.toLocaleString() }} fans ·
                  <a :href="`https://www.deezer.com/artist/${h.deezer_id}`" target="_blank" class="dz-link" @click.stop>dz:{{ h.deezer_id }}</a>
                </span>
              </div>
            </div>
            <p v-if="linkDeezerQuery && deezerHits.length === 0" class="empty-hint">Aucun résultat</p>
          </div>
        </div>
      </div>
      <div v-if="selectedDbArtist && selectedDeezerHit" class="link-confirm">
        <span class="link-summary">
          Lier <strong>{{ selectedDbArtist.name }}</strong> → Deezer <strong>{{ selectedDeezerHit.name }}</strong> ({{ selectedDeezerHit.deezer_id }})
        </span>
        <button class="btn-confirm-link" :disabled="linking" @click="confirmLink">
          {{ linking ? 'Liaison…' : 'Confirmer' }}
        </button>
        <span v-if="linkSuccess" class="result-item ok">✓ Lié</span>
        <span v-if="linkError" class="sync-error">{{ linkError }}</span>
      </div>
    </section>

    <!-- Flags à valider -->
    <section class="admin-section">
      <div class="section-header">
        <h2 class="section-title">
          Flags artistes
          <span v-if="flags.length" class="flag-count">{{ flags.length }}</span>
        </h2>
        <div class="filter-group">
          <button
            v-for="s in ['pending', 'validated', 'skipped']"
            :key="s"
            class="filter-btn"
            :class="{ active: filterStatus === s }"
            @click="setFilter(s)"
          >{{ s }}</button>
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
            <tr v-for="flag in flags" :key="flag.id" :class="{ resolved: flag.status !== 'pending' }">
              <td class="col-raw">
                <span class="raw-string">{{ flag.raw_artist_string }}</span>
              </td>
              <td class="col-reason">
                <span class="reason-badge" :class="flag.reason">{{ flag.reason }}</span>
              </td>
              <td class="col-tokens">
                <div class="token-list">
                  <span v-for="t in flag.tokens" :key="t" class="token-pill">{{ t }}</span>
                </div>
              </td>
              <td class="col-deezer">
                <div class="deezer-list">
                  <span
                    v-for="(did, name) in flag.deezer_ids"
                    :key="name"
                    class="deezer-entry"
                    :class="{ found: !!did, missing: !did }"
                  >
                    <span class="deezer-name">{{ name }}</span>
                    <a v-if="did" :href="`https://www.deezer.com/artist/${did}`" target="_blank" class="deezer-id mono dz-link">{{ did }}</a>
                    <span v-else class="deezer-id mono">✗</span>
                  </span>
                </div>
              </td>
              <td class="col-action">
                <template v-if="flag.status === 'pending'">
                  <div class="action-btns">
                    <button
                      class="btn-split"
                      :disabled="resolving[flag.id]"
                      :title="`Créer: ${flag.tokens.join(', ')}`"
                      @click="resolve(flag.id, 'split')"
                    >Splitter</button>
                    <button
                      class="btn-keep"
                      :disabled="resolving[flag.id]"
                      :title="`Créer: ${flag.raw_artist_string}`"
                      @click="resolve(flag.id, 'keep')"
                    >Garder</button>
                    <button
                      class="btn-skip"
                      :disabled="resolving[flag.id]"
                      @click="resolve(flag.id, 'skip')"
                    >Ignorer</button>
                  </div>
                </template>
                <template v-else>
                  <span class="status-badge" :class="flag.status">{{ flag.status }}</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import axios from 'axios'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const syncing = ref(false)
const syncResult = ref(null)
const syncError = ref('')
let pollTimer = null
const flags = ref([])
const loadingFlags = ref(false)
const filterStatus = ref('pending')
const resolving = reactive({})
const fetchingArtworks = ref(false)
const artworksResult = ref(null)
const artworksError = ref('')

// Manual link
const linkArtistQuery = ref('')
const linkDeezerQuery = ref('')
const dbArtistResults = ref([])
const deezerHits = ref([])
const selectedDbArtist = ref(null)
const selectedDeezerHit = ref(null)
const linking = ref(false)
const linkSuccess = ref(false)
const linkError = ref('')
let linkDbTimer = null
let linkDeezerTimer = null

function authHeaders() {
  return auth.token ? { Authorization: `Bearer ${auth.token}` } : {}
}

async function runSync() {
  syncing.value = true
  syncResult.value = null
  syncError.value = ''
  try {
    const { data } = await axios.post('/api/admin/artists/sync', {}, { headers: authHeaders() })
    pollStatus(data.task_id)
  } catch (e) {
    syncError.value = e.response?.data?.detail || 'Erreur lors de la sync'
    syncing.value = false
  }
}

function pollStatus(taskId) {
  let attempts = 0
  const maxAttempts = 300 // 10min max (2s * 300)
  pollTimer = setInterval(async () => {
    attempts++
    if (attempts >= maxAttempts) {
      clearInterval(pollTimer)
      syncError.value = 'Timeout — vérifiez les logs Celery'
      syncing.value = false
      return
    }
    try {
      const { data } = await axios.get(`/api/admin/artists/sync/status/${taskId}`, { headers: authHeaders() })
      if (data.status === 'done') {
        clearInterval(pollTimer)
        syncResult.value = data.result
        syncing.value = false
        await fetchFlags()
      } else if (data.status === 'error') {
        clearInterval(pollTimer)
        syncError.value = data.error || 'Erreur Celery'
        syncing.value = false
      }
    } catch {}
  }, 2000)
}

async function fetchFlags() {
  loadingFlags.value = true
  try {
    const { data } = await axios.get('/api/admin/artists/flags', {
      params: { status: filterStatus.value },
      headers: authHeaders(),
    })
    flags.value = data
  } finally {
    loadingFlags.value = false
  }
}

async function setFilter(s) {
  filterStatus.value = s
  await fetchFlags()
}

async function resolve(flagId, action) {
  resolving[flagId] = true
  try {
    const { data } = await axios.post(
      `/api/admin/artists/flags/${flagId}/resolve`,
      { action },
      { headers: authHeaders() },
    )
    // Update in-place
    const idx = flags.value.findIndex(f => f.id === flagId)
    if (idx !== -1) flags.value[idx] = data
    // If viewing pending, remove resolved ones
    if (filterStatus.value === 'pending') {
      flags.value = flags.value.filter(f => f.status === 'pending')
    }
  } finally {
    resolving[flagId] = false
  }
}

async function runFetchArtworks() {
  fetchingArtworks.value = true
  artworksResult.value = null
  artworksError.value = ''
  try {
    const { data } = await axios.post('/api/admin/artists/fetch-artworks', {}, { headers: authHeaders() })
    pollArtworksStatus(data.task_id)
  } catch (e) {
    artworksError.value = e.response?.data?.detail || 'Erreur'
    fetchingArtworks.value = false
  }
}

function pollArtworksStatus(taskId) {
  let attempts = 0
  const timer = setInterval(async () => {
    attempts++
    if (attempts >= 150) { clearInterval(timer); fetchingArtworks.value = false; return }
    try {
      const { data } = await axios.get(`/api/admin/artists/sync/status/${taskId}`, { headers: authHeaders() })
      if (data.status === 'done') {
        clearInterval(timer)
        artworksResult.value = data.result
        fetchingArtworks.value = false
      } else if (data.status === 'error') {
        clearInterval(timer)
        artworksError.value = data.error || 'Erreur Celery'
        fetchingArtworks.value = false
      }
    } catch {}
  }, 2000)
}

async function fetchNoDeezerArtists(q = '') {
  const params = { no_deezer: true, limit: 100 }
  if (q) params.q = q
  const { data } = await axios.get('/api/artists/', { params })
  dbArtistResults.value = data
}

function onLinkSearch() {
  clearTimeout(linkDbTimer)
  selectedDbArtist.value = null
  linkDbTimer = setTimeout(() => fetchNoDeezerArtists(linkArtistQuery.value.trim()), 300)
}

function onDeezerSearch() {
  clearTimeout(linkDeezerTimer)
  selectedDeezerHit.value = null
  if (!linkDeezerQuery.value.trim()) { deezerHits.value = []; return }
  linkDeezerTimer = setTimeout(async () => {
    const { data } = await axios.get('/api/admin/artists/search-deezer', {
      params: { q: linkDeezerQuery.value.trim() },
      headers: authHeaders(),
    })
    deezerHits.value = data
  }, 300)
}

async function confirmLink() {
  if (!selectedDbArtist.value || !selectedDeezerHit.value) return
  linking.value = true
  linkSuccess.value = false
  linkError.value = ''
  try {
    await axios.patch(
      `/api/admin/artists/${selectedDbArtist.value.id}/deezer`,
      { deezer_id: selectedDeezerHit.value.deezer_id },
      { headers: authHeaders() },
    )
    linkSuccess.value = true
    // Reset
    selectedDbArtist.value = null
    selectedDeezerHit.value = null
    linkArtistQuery.value = ''
    linkDeezerQuery.value = ''
    dbArtistResults.value = []
    deezerHits.value = []
  } catch (e) {
    linkError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    linking.value = false
  }
}

onMounted(() => {
  fetchFlags()
  fetchNoDeezerArtists()
})
</script>

<style scoped>
.admin-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1100px;
  margin: 0 auto;
}
.view-header { margin-bottom: 24px; }
.view-title {
  font: 600 22px/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}

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
.section-header .section-title { margin-bottom: 0; }
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

/* Sync */
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
.btn-sync:disabled { opacity: 0.5; cursor: default; }
.sync-result {
  display: flex;
  gap: 14px;
  font: 400 13px/1 var(--font-mono);
}
.result-item.ok { color: var(--pos-ink, #27ae60); }
.result-item.warn { color: var(--warn-ink, #e67e22); }
.result-item.muted { color: var(--ink-3); }
.sync-error { font-size: 13px; color: var(--neg-ink, #c0392b); }

/* Filter */
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
  transition: background 0.12s, color 0.12s;
}
.filter-btn:not(:last-child) { border-right: 1px solid var(--line-2); }
.filter-btn.active { background: var(--accent-soft); color: var(--accent-ink); }

/* Table */
.table-wrap { overflow-x: auto; }
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
.flag-table tbody tr:last-child td { border-bottom: none; }
.flag-table tbody tr.resolved td { opacity: 0.5; }

.col-raw    { min-width: 180px; }
.col-reason { width: 160px; }
.col-tokens { width: 200px; }
.col-deezer { width: 220px; }
.col-action { width: 200px; text-align: right; }

.raw-string {
  font: 500 13px/1.3 var(--font-ui);
  color: var(--ink);
}

.reason-badge {
  font: 500 11px/1 var(--font-mono);
  padding: 3px 7px;
  border-radius: 4px;
  white-space: nowrap;
}
.reason-badge.comma_unresolved { background: var(--warn-soft, #fef3cd); color: var(--warn-ink, #856404); }
.reason-badge.ampersand_ambiguous { background: var(--neg-soft, #fde); color: var(--neg-ink, #c0392b); }
.reason-badge.ampersand_unknown { background: var(--surface-2); color: var(--ink-3); }

.token-list { display: flex; flex-wrap: wrap; gap: 4px; }
.token-pill {
  font: 400 11px/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: 3px 7px;
  border-radius: 4px;
  white-space: nowrap;
}

.deezer-list { display: flex; flex-direction: column; gap: 3px; }
.deezer-entry { display: flex; gap: 6px; align-items: baseline; }
.deezer-name { font-size: 11px; color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100px; }
.deezer-id { font-size: 10px; }
.deezer-entry.found .deezer-id { color: var(--pos-ink, #27ae60); }
.deezer-entry.missing .deezer-id { color: var(--neg-ink, #c0392b); }

.action-btns { display: flex; gap: 5px; justify-content: flex-end; flex-wrap: wrap; }
.btn-split, .btn-keep, .btn-skip {
  padding: 5px 10px;
  border-radius: var(--r-sm);
  font: 500 11px/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.12s;
}
.btn-split:disabled, .btn-keep:disabled, .btn-skip:disabled { opacity: 0.4; cursor: default; }
.btn-split { border: 1px solid var(--accent); background: var(--accent-soft); color: var(--accent-ink); }
.btn-split:hover:not(:disabled) { background: var(--accent); color: var(--on-accent); }
.btn-keep { border: 1px solid var(--line-2); background: var(--surface); color: var(--ink-2); }
.btn-keep:hover:not(:disabled) { background: var(--surface-2); }
.btn-skip { border: 1px solid var(--line-2); background: var(--surface); color: var(--ink-3); }
.btn-skip:hover:not(:disabled) { color: var(--neg-ink, #c0392b); border-color: var(--neg-ink, #c0392b); }

.status-badge {
  font: 500 11px/1 var(--font-mono);
  padding: 3px 8px;
  border-radius: 4px;
}
.status-badge.validated { background: var(--pos-soft, #d4edda); color: var(--pos-ink, #27ae60); }
.status-badge.skipped { background: var(--surface-2); color: var(--ink-3); }

.state { font-size: 13px; color: var(--ink-3); font-style: italic; padding: 12px 0; }
.mono { font-family: var(--font-mono); }

/* Manual link */
.link-form {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.link-results {
  display: flex;
  gap: 16px;
  margin-bottom: 14px;
}
.link-col {
  flex: 1;
  min-width: 200px;
}
.col-label {
  font: 500 10px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: 8px;
}
.result-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: var(--r-sm);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.1s;
}
.result-row:hover { background: var(--surface-2); }
.result-row.selected { border-color: var(--accent); background: var(--accent-soft); }
.cover-thumb-sm {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--surface-2);
  border: 1px solid var(--line);
  overflow: hidden;
  flex: none;
  display: flex; align-items: center; justify-content: center;
}
.cover-thumb-sm img { width: 100%; height: 100%; object-fit: cover; }
.fallback-sm { font: 600 13px/1 var(--font-ui); color: var(--ink-3); }
.ar-name-sm { display: block; font: 500 13px/1 var(--font-ui); color: var(--ink); }
.ar-meta { display: block; font-size: 11px; margin-top: 2px; }
.empty-hint { font-size: 12px; color: var(--ink-3); font-style: italic; padding: 8px 10px; }
.link-list {
  max-height: 320px;
  overflow-y: auto;
}
.dz-link {
  color: var(--accent-ink);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 11px;
}
.dz-link:hover { text-decoration: underline; }
.link-confirm {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--surface-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  flex-wrap: wrap;
}
.link-summary { font: 400 13px/1.4 var(--font-ui); color: var(--ink-2); }
.btn-confirm-link {
  padding: 7px 16px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
}
.btn-confirm-link:disabled { opacity: 0.5; cursor: default; }
</style>
