<template>
  <!-- Sync artistes -->
  <section class="admin-section">
    <h2 class="section-title">Sync artistes</h2>
    <p class="section-sub">
      Parse les noms d'artistes du catalog et peuple la table artistes. Idempotent.
    </p>
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

  <!-- Liaison Deezer (artistes) -->
  <section class="admin-section">
    <h2 class="section-title">Liaison Deezer (artistes)</h2>
    <p class="section-sub">
      Cherche sur Deezer les artistes sans deezer_id et les lie sur un match exact.
      Borné par run (budget) et sûr contre les boucles. Idempotent.
    </p>
    <div class="sync-row">
      <button class="btn-sync" :disabled="linkingArtists" @click="runLinkArtists">
        {{ linkingArtists ? 'Liaison en cours…' : 'Lier artistes (Deezer)' }}
      </button>
      <div v-if="linkArtistsResult" class="sync-result">
        <span class="result-item ok">🔗 {{ linkArtistsResult.linked }} liés</span>
        <span class="result-item muted">🔎 {{ linkArtistsResult.searched }} cherchés</span>
        <span v-if="linkArtistsResult.abandoned" class="result-item warn"
          >⌀ {{ linkArtistsResult.abandoned }} abandonnés</span
        >
        <span v-if="linkArtistsResult.errors" class="result-item warn"
          >⚠ {{ linkArtistsResult.errors }} erreurs</span
        >
        <span v-if="linkArtistsResult.dropped_by_budget" class="result-item muted"
          >↷ {{ linkArtistsResult.dropped_by_budget }} en attente</span
        >
      </div>
      <span v-if="linkArtistsError" class="sync-error">{{ linkArtistsError }}</span>
    </div>
  </section>

  <!-- Fetch artworks -->
  <section class="admin-section">
    <h2 class="section-title">Artworks artistes</h2>
    <p class="section-sub">
      Fetche les images Deezer pour tous les artistes avec un deezer_id. Idempotent.
    </p>
    <div class="sync-row">
      <button class="btn-sync" :disabled="fetchingArtworks" @click="runFetchArtworks">
        {{ fetchingArtworks ? 'Fetch en cours…' : 'Fetch artworks' }}
      </button>
      <div v-if="artworksResult" class="sync-result">
        <span class="result-item ok">✓ {{ artworksResult.fetched }} artworks</span>
        <span class="result-item muted">↷ {{ artworksResult.skipped }} skippés</span>
        <span v-if="artworksResult.errors" class="result-item warn"
          >⚠ {{ artworksResult.errors }} erreurs</span
        >
        <span v-if="artworksResult.dropped_by_budget" class="result-item muted"
          >↷ {{ artworksResult.dropped_by_budget }} en attente</span
        >
      </div>
      <span v-if="artworksError" class="sync-error">{{ artworksError }}</span>
    </div>
  </section>

  <!-- Artworks playlists -->
  <section class="admin-section">
    <h2 class="section-title">Artworks playlists</h2>
    <p class="section-sub">
      Fetche les images Deezer pour toutes les playlists sans artwork. Synchrone (~1s/playlist).
    </p>
    <div class="sync-row">
      <button class="btn-sync" :disabled="fetchingPlArtworks" @click="runFetchPlArtworks">
        {{ fetchingPlArtworks ? 'Fetch en cours…' : 'Fetch artworks playlists' }}
      </button>
      <div v-if="plArtworksResult" class="sync-result">
        <span class="result-item ok">✓ {{ plArtworksResult.fetched }} importés</span>
        <span v-if="plArtworksResult.failed" class="result-item warn"
          >⚠ {{ plArtworksResult.failed }} échoués</span
        >
        <span class="result-item muted">/ {{ plArtworksResult.total }} sans artwork</span>
      </div>
      <span v-if="plArtworksError" class="sync-error">{{ plArtworksError }}</span>
    </div>
  </section>

  <!-- Liaison manuelle artiste ↔ Deezer -->
  <section class="admin-section">
    <h2 class="section-title">Lier un artiste à Deezer</h2>
    <p class="section-sub">
      Recherche un artiste dans la DB et l'associe manuellement à un compte Deezer.
    </p>
    <div class="link-form">
      <input
        v-model="linkArtistQuery"
        class="form-input"
        placeholder="Filtrer les artistes sans Deezer…"
        @input="onLinkSearch"
      />
      <input
        v-model="linkDeezerQuery"
        class="form-input"
        placeholder="Recherche sur Deezer…"
        @input="onDeezerSearch"
      />
    </div>
    <div class="link-results">
      <div class="link-col">
        <p class="col-label">Artistes sans deezer_id ({{ noDeezerTotal }})</p>
        <div class="link-list">
          <div
            v-for="a in dbArtistResults"
            :key="a.id"
            class="result-row"
            :class="{ selected: selectedDbArtist?.id === a.id }"
            @click="selectArtistAndSearch(a)"
          >
            <div class="cover-thumb-sm">
              <img v-if="a.has_artwork" :src="`/storage/artist-artworks/${a.id}.jpg`" />
              <span v-else class="fallback-sm">{{ a.name?.[0] }}</span>
            </div>
            <span class="ar-name-sm">{{ a.name }}</span>
            <div class="row-actions" @click.stop>
              <button class="btn-row-action" title="Pas sur Deezer" @click="markNoDeezer(a)">
                ✗ Deezer
              </button>
              <button
                v-if="detectSeparator(a.name)"
                class="btn-row-action flag"
                title="Envoyer vers les flags"
                @click="flagArtist(a)"
              >
                Flagguer
              </button>
              <button
                v-if="hasSpaces(a.name)"
                class="btn-row-action split"
                title="Découper manuellement en plusieurs artistes"
                @click="openManualSplit(a)"
              >
                Splitter
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="link-col">
        <p class="col-label">Résultats Deezer</p>
        <div class="link-list">
          <div
            v-for="h in deezerHits"
            :key="h.deezer_id"
            class="result-row"
            :class="{ selected: selectedDeezerHit?.deezer_id === h.deezer_id }"
            @click="selectedDeezerHit = h"
          >
            <div class="cover-thumb-sm">
              <img v-if="h.picture" :src="h.picture" />
              <span v-else class="fallback-sm">{{ h.name?.[0] }}</span>
            </div>
            <div>
              <span class="ar-name-sm">{{ h.name }}</span>
              <span class="ar-meta mono muted">
                {{ h.nb_fan?.toLocaleString() }} fans ·
                <a
                  :href="`https://www.deezer.com/artist/${h.deezer_id}`"
                  target="_blank"
                  class="dz-link"
                  @click.stop
                  >dz:{{ h.deezer_id }}</a
                >
              </span>
            </div>
          </div>
          <p v-if="linkDeezerQuery && deezerHits.length === 0" class="empty-hint">
            Aucun résultat
          </p>
        </div>
      </div>
    </div>
    <div v-if="selectedDbArtist && selectedDeezerHit" class="link-confirm">
      <span class="link-summary">
        Lier <strong>{{ selectedDbArtist.name }}</strong> → Deezer
        <strong>{{ selectedDeezerHit.name }}</strong> ({{ selectedDeezerHit.deezer_id }})
      </span>
      <button class="btn-confirm-link" :disabled="linking" @click="confirmLink">
        {{ linking ? 'Liaison…' : 'Confirmer' }}
      </button>
      <span v-if="linkSuccess" class="result-item ok">✓ Lié</span>
      <span v-if="linkError" class="sync-error">{{ linkError }}</span>
    </div>

    <!-- Manual split panel -->
    <div v-if="splitArtist" class="split-panel">
      <div class="split-header">
        <span class="split-label">Splitter manuellement :</span>
        <strong>{{ splitArtist.name }}</strong>
        <button class="btn-row-action" @click="cancelSplit">Annuler</button>
      </div>

      <div v-if="splitIndex === null" class="split-tokens">
        <template v-for="(word, i) in splitWords" :key="i">
          <span class="split-word">{{ word }}</span>
          <button
            v-if="i < splitWords.length - 1"
            class="split-sep"
            :title="`Couper ici : « ${splitWords.slice(0, i + 1).join(splitSep || ' ')} » + « ${splitWords.slice(i + 1).join(splitSep || ' ')} »`"
            @click="chooseSplit(i)"
          >
            ·
          </button>
        </template>
      </div>

      <div v-else class="split-preview">
        <span class="split-pill">{{ splitLeft }}</span>
        <span class="split-plus">+</span>
        <span class="split-pill">{{ splitRight }}</span>
      </div>

      <div v-if="splitIndex !== null" class="split-actions">
        <button class="btn-row-action" @click="splitIndex = null">Modifier</button>
        <button class="btn-confirm-link" :disabled="splitting" @click="confirmManualSplit">
          {{ splitting ? 'Split…' : 'Confirmer le split' }}
        </button>
        <span v-if="splitError" class="sync-error">{{ splitError }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import { useTaskPoll } from '../../composables/useTaskPoll.js'

const syncing = ref(false)
const syncResult = ref(null)
const syncError = ref('')
const fetchingArtworks = ref(false)
const artworksResult = ref(null)
const artworksError = ref('')
const linkingArtists = ref(false)
const linkArtistsResult = ref(null)
const linkArtistsError = ref('')
const fetchingPlArtworks = ref(false)
const plArtworksResult = ref(null)
const plArtworksError = ref('')

// Manual link
const linkArtistQuery = ref('')
const linkDeezerQuery = ref('')
const dbArtistResults = ref([])
// True DB total for the current filter (may exceed the page shown in dbArtistResults).
const noDeezerTotal = ref(0)
const deezerHits = ref([])
const selectedDbArtist = ref(null)
const selectedDeezerHit = ref(null)
const linking = ref(false)
const linkSuccess = ref(false)
const linkError = ref('')
let linkDbTimer = null
let linkDeezerTimer = null

function selectArtistAndSearch(a) {
  selectedDbArtist.value = a
  linkDeezerQuery.value = a.name
  onDeezerSearch()
}

// Sync poll: ignores network errors and keeps polling (stopOnError: false).
const syncPoll = useTaskPoll((taskId) => `/api/admin/artists/sync/status/${taskId}`, {
  intervalMs: 2000,
  maxAttempts: 300,
  stopOnError: false,
  onData(data, { stop }) {
    if (data.status === 'done') {
      syncResult.value = data.result
      syncing.value = false
      stop()
    } else if (data.status === 'error') {
      syncError.value = data.error || 'Erreur Celery'
      syncing.value = false
      stop()
    }
  },
  onMaxAttempts() {
    syncError.value = 'Timeout — vérifiez les logs Celery'
    syncing.value = false
  },
})

async function runSync() {
  syncing.value = true
  syncResult.value = null
  syncError.value = ''
  try {
    const { data } = await api.post('/api/admin/artists/sync')
    syncPoll.start(data.task_id)
  } catch (e) {
    syncError.value = e.response?.data?.detail || 'Erreur lors de la sync'
    syncing.value = false
  }
}

const artworksPoll = useTaskPoll((taskId) => `/api/admin/artists/sync/status/${taskId}`, {
  intervalMs: 2000,
  maxAttempts: 150,
  onData(data, { stop }) {
    if (data.status === 'done') {
      artworksResult.value = data.result
      fetchingArtworks.value = false
      stop()
    } else if (data.status === 'error') {
      artworksError.value = data.error || 'Erreur Celery'
      fetchingArtworks.value = false
      stop()
    }
  },
  onError(err) {
    artworksError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    fetchingArtworks.value = false
  },
  onMaxAttempts() {
    fetchingArtworks.value = false
  },
})

async function runFetchArtworks() {
  fetchingArtworks.value = true
  artworksResult.value = null
  artworksError.value = ''
  try {
    const { data } = await api.post('/api/admin/artists/fetch-artworks')
    artworksPoll.start(data.task_id)
  } catch (e) {
    artworksError.value = e.response?.data?.detail || 'Erreur'
    fetchingArtworks.value = false
  }
}

const linkArtistsPoll = useTaskPoll((taskId) => `/api/admin/artists/sync/status/${taskId}`, {
  intervalMs: 2000,
  maxAttempts: 150,
  onData(data, { stop }) {
    if (data.status === 'done') {
      linkArtistsResult.value = data.result
      linkingArtists.value = false
      stop()
    } else if (data.status === 'error') {
      linkArtistsError.value = data.error || 'Erreur Celery'
      linkingArtists.value = false
      stop()
    }
  },
  onError(err) {
    linkArtistsError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    linkingArtists.value = false
  },
  onMaxAttempts() {
    linkingArtists.value = false
  },
})

async function runLinkArtists() {
  linkingArtists.value = true
  linkArtistsResult.value = null
  linkArtistsError.value = ''
  try {
    const { data } = await api.post('/api/admin/artists/link-deezer')
    linkArtistsPoll.start(data.task_id)
  } catch (e) {
    linkArtistsError.value = e.response?.data?.detail || 'Erreur'
    linkingArtists.value = false
  }
}

async function runFetchPlArtworks() {
  fetchingPlArtworks.value = true
  plArtworksResult.value = null
  plArtworksError.value = ''
  try {
    const { data } = await api.post('/api/admin/playlists/fetch-artworks')
    plArtworksResult.value = data
  } catch (e) {
    plArtworksError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    fetchingPlArtworks.value = false
  }
}

async function fetchNoDeezerArtists(q = '') {
  const params = { no_deezer: true, limit: 100 }
  if (q) params.q = q
  const { data } = await api.get('/api/artists/', { params })
  dbArtistResults.value = data.items || data
  noDeezerTotal.value =
    typeof data.total === 'number' ? data.total : dbArtistResults.value.length
}

function onLinkSearch() {
  clearTimeout(linkDbTimer)
  selectedDbArtist.value = null
  linkDbTimer = setTimeout(() => fetchNoDeezerArtists(linkArtistQuery.value.trim()), 300)
}

function onDeezerSearch() {
  clearTimeout(linkDeezerTimer)
  selectedDeezerHit.value = null
  if (!linkDeezerQuery.value.trim()) {
    deezerHits.value = []
    return
  }
  linkDeezerTimer = setTimeout(async () => {
    try {
      const { data } = await api.get('/api/admin/artists/search-deezer', {
        params: { q: linkDeezerQuery.value.trim() },
      })
      deezerHits.value = data
    } catch {
      // 429 / network errors are surfaced by the api interceptor toast.
      deezerHits.value = []
    }
  }, 300)
}

async function confirmLink() {
  if (!selectedDbArtist.value || !selectedDeezerHit.value) return
  linking.value = true
  linkSuccess.value = false
  linkError.value = ''
  try {
    await api.patch(`/api/admin/artists/${selectedDbArtist.value.id}/deezer`, {
      deezer_id: selectedDeezerHit.value.deezer_id,
    })
    linkSuccess.value = true
    const q = linkArtistQuery.value.trim()
    selectedDbArtist.value = null
    selectedDeezerHit.value = null
    linkDeezerQuery.value = ''
    deezerHits.value = []
    await fetchNoDeezerArtists(q)
  } catch (e) {
    linkError.value = e.response?.data?.detail || 'Erreur'
  } finally {
    linking.value = false
  }
}

async function markNoDeezer(artist) {
  try {
    await api.patch(`/api/admin/artists/${artist.id}/no-deezer`)
    dbArtistResults.value = dbArtistResults.value.filter((a) => a.id !== artist.id)
    noDeezerTotal.value = Math.max(0, noDeezerTotal.value - 1)
  } catch {}
}

// Kept in parity with the backend sync detection (tasks/artists.py: FEAT_RE +
// " & " + bare "|"), with more specific variants first so detectSeparator picks
// the longest match. "|" is bare (no surrounding spaces) — source strings use
// both "A | B" and "A|B", and a pipe is never part of a real name. Exception:
// '/' stays FRONT-ONLY — human-review hint, never a backend auto-split ("AC/DC").
const SEPARATORS = [
  '/',
  ' & ',
  '|',
  ', ',
  ' feat. ',
  ' featuring ',
  ' feat ',
  ' ft. ',
  ' ft ',
  ' vs. ',
  ' vs ',
]

function detectSeparator(name) {
  return SEPARATORS.find((sep) => name.includes(sep)) || null
}

// Manual split
const splitArtist = ref(null)
const splitIndex = ref(null)
const splitting = ref(false)
const splitError = ref('')

// When the name carries a recognised separator (" & ", " | ", " feat "…), cut
// on it so the two halves are clean; otherwise fall back to spaces so the admin
// can still pick any word boundary. Rejoin with the same delimiter to
// reconstruct each side losslessly.
const splitSep = computed(() =>
  splitArtist.value ? detectSeparator(splitArtist.value.name) : null,
)

const splitWords = computed(() => {
  if (!splitArtist.value) return []
  return splitArtist.value.name
    .split(splitSep.value || ' ')
    .map((w) => w.trim())
    .filter(Boolean)
})

const splitLeft = computed(() => {
  if (splitIndex.value === null) return ''
  return splitWords.value.slice(0, splitIndex.value + 1).join(splitSep.value || ' ')
})

const splitRight = computed(() => {
  if (splitIndex.value === null) return ''
  return splitWords.value.slice(splitIndex.value + 1).join(splitSep.value || ' ')
})

function hasSpaces(name) {
  return name.trim().includes(' ')
}

function openManualSplit(artist) {
  splitArtist.value = artist
  splitIndex.value = null
  splitError.value = ''
}

function cancelSplit() {
  splitArtist.value = null
  splitIndex.value = null
}

function chooseSplit(index) {
  splitIndex.value = index
}

async function confirmManualSplit() {
  if (!splitArtist.value || splitIndex.value === null) return
  splitting.value = true
  splitError.value = ''
  try {
    const { data: flag } = await api.post('/api/admin/artists/flags/manual', {
      raw_artist_string: splitArtist.value.name,
      tokens: [splitLeft.value, splitRight.value],
      reason: 'manual',
    })
    await api.post(`/api/admin/artists/flags/${flag.id}/resolve`, { action: 'split' })
    dbArtistResults.value = dbArtistResults.value.filter(
      (a) => a.id !== splitArtist.value.id,
    )
    noDeezerTotal.value = Math.max(0, noDeezerTotal.value - 1)
    splitArtist.value = null
    splitIndex.value = null
  } catch (e) {
    splitError.value = e.response?.data?.detail || 'Erreur lors du split'
  } finally {
    splitting.value = false
  }
}

async function flagArtist(artist) {
  const sep = detectSeparator(artist.name)
  if (!sep) return
  const tokens = artist.name
    .split(sep)
    .map((t) => t.trim())
    .filter(Boolean)
  try {
    await api.post('/api/admin/artists/flags/manual', {
      raw_artist_string: artist.name,
      tokens,
      reason: 'manual',
    })
    dbArtistResults.value = dbArtistResults.value.filter((a) => a.id !== artist.id)
    noDeezerTotal.value = Math.max(0, noDeezerTotal.value - 1)
  } catch {}
}

onMounted(() => {
  fetchNoDeezerArtists()
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
.section-title {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: var(--space-15);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.section-sub {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-3);
  margin-bottom: var(--space-4);
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
.sync-result {
  display: flex;
  gap: var(--space-4);
  font: 400 var(--fs-sm)/1 var(--font-mono);
}
.result-item.ok {
  color: var(--pos-ink);
}
.result-item.warn {
  color: var(--warn-ink);
}
.result-item.muted {
  color: var(--ink-3);
}
.sync-error {
  font-size: var(--fs-sm);
  color: var(--neg-ink);
}
.mono {
  font-family: var(--font-mono);
}
.muted {
  color: var(--ink-3);
}

/* Manual link */
.link-form {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}
.link-results {
  display: flex;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.link-col {
  flex: 1;
  min-width: 200px;
}
.col-label {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: var(--space-2);
}
.result-row {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-15) var(--space-25);
  border-radius: var(--r-sm);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.1s;
}
.result-row:hover {
  background: var(--surface-2);
}
.result-row.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.cover-thumb-sm {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--surface-2);
  border: 1px solid var(--line);
  overflow: hidden;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover-thumb-sm img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.fallback-sm {
  font: 600 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-3);
}
.ar-name-sm {
  display: block;
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink);
}
.ar-meta {
  display: block;
  font-size: var(--fs-xs);
  margin-top: var(--space-05);
}
.empty-hint {
  font-size: var(--fs-sm);
  color: var(--ink-3);
  font-style: italic;
  padding: var(--space-2) var(--space-25);
}
.link-list {
  max-height: 320px;
  overflow-y: auto;
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
.row-actions {
  margin-left: auto;
  display: flex;
  gap: var(--space-1);
  opacity: 0;
  transition: opacity 0.1s;
}
.result-row:hover .row-actions {
  opacity: 1;
}
.btn-row-action {
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-row-action:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}
.btn-row-action.flag:hover {
  color: var(--warn-ink);
  border-color: var(--warn-ink);
}
.link-confirm {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  flex-wrap: wrap;
}
.link-summary {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
}
.btn-confirm-link {
  padding: var(--space-15) var(--space-4);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
}
.btn-confirm-link:disabled {
  opacity: 0.5;
  cursor: default;
}

/* Manual split */
.split-panel {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
}
.split-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
}
.split-header strong {
  color: var(--ink);
}
.split-label {
  white-space: nowrap;
}
.split-tokens {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
}
.split-word {
  font: 500 var(--fs-base)/1 var(--font-ui);
  color: var(--ink);
  padding: var(--space-1) 0;
}
.split-sep {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 24px;
  margin: 0 var(--space-05);
  background: var(--accent-soft);
  border: none;
  border-radius: 2px;
  cursor: pointer;
  font: 700 var(--fs-base)/1 var(--font-mono);
  color: var(--accent-ink);
  transition:
    background 0.12s,
    color 0.12s;
}
.split-sep:hover {
  background: var(--accent);
  color: var(--on-accent);
}
.split-preview {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.split-pill {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: var(--space-1) var(--space-25);
  border-radius: 4px;
  white-space: nowrap;
}
.split-plus {
  font: 500 var(--fs-base)/1 var(--font-ui);
  color: var(--ink-3);
}
.split-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-25);
}
.btn-row-action.split:hover {
  color: var(--accent-ink);
  border-color: var(--accent);
}
</style>
