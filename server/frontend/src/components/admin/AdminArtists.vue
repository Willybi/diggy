<template>
  <!-- Archétype A (D4) : les 4 jobs artistes groupés dans UNE région. -->
  <section class="aj-region">
    <div class="aj-head">
      <h2 class="aj-title">Jobs artistes <span class="aj-count">4</span></h2>
      <span class="aj-eyebrow">Idempotents</span>
    </div>
    <div v-for="job in jobs" :key="job.key" class="aj-row">
      <div class="aj-body">
        <h3 class="aj-job-title">{{ job.title }}</h3>
        <p class="aj-job-desc">{{ job.desc }}</p>
        <p v-if="job.running" class="aj-running">
          <AdminIcon name="arc" :size="13" /> Job en cours…
        </p>
        <div v-else-if="job.pairs.length || job.error" class="aj-result">
          <span
            v-for="(p, i) in job.pairs"
            :key="i"
            class="aj-pair"
            :class="`aj-pair--${p.channel}`"
          >
            <AdminIcon :name="channelIcon(p.channel)" :size="13" />
            <span class="aj-num">{{ fmtInt(p.value) }}</span>
            <span class="aj-lbl">{{ p.label }}</span>
          </span>
          <span v-if="job.error" class="aj-fail">
            <AdminIcon name="alert-triangle" :size="13" />
            <span class="aj-fail-word">Échec</span>
            <span class="aj-fail-msg">{{ job.error }}</span>
          </span>
        </div>
      </div>
      <div class="aj-action">
        <button class="btn btn--sm btn--accent" :disabled="job.running" @click="job.run()">
          {{ job.running ? 'En cours…' : job.label }}
        </button>
      </div>
    </div>
  </section>

  <!-- Archétype D (D12) : lier un artiste à Deezer — recherche + double liste. -->
  <section class="dl-section">
    <div class="dl-head">
      <h2 class="dl-heading">Lier un artiste à Deezer</h2>
      <p class="dl-sub">
        Recherche un artiste dans la DB et l'associe manuellement à un compte Deezer.
      </p>
    </div>

    <div class="dl-grid">
      <!-- Colonne gauche : artistes sans deezer_id -->
      <div class="dl-col">
        <div class="dl-col-head">
          <span class="dl-eyebrow">Artistes sans deezer_id</span>
          <div class="at-seg">
            <button
              class="at-seg-b"
              :class="{ active: viewMode === 'active' }"
              @click="setView('active')"
            >
              Actifs ({{ activeCount }})
            </button>
            <button
              class="at-seg-b"
              :class="{ active: viewMode === 'dormant' }"
              @click="setView('dormant')"
            >
              Dormants ({{ dormantCount }})
            </button>
          </div>
        </div>
        <input
          v-model="linkArtistQuery"
          class="dl-input"
          placeholder="Filtrer les artistes sans Deezer…"
          @input="onLinkSearch"
        />
        <div class="dl-list">
          <div
            v-for="a in dbArtistResults"
            :key="a.id"
            class="dl-row"
            :class="{ 'is-selected': selectedDbArtist?.id === a.id }"
            @click="selectArtistAndSearch(a)"
          >
            <div class="dl-thumb">
              <img v-if="a.has_artwork" :src="`/storage/artist-artworks/${a.id}.jpg`" alt="" />
              <span v-else class="dl-fallback">{{ a.name?.[0] }}</span>
            </div>
            <span class="dl-name">{{ stripDisambiguationNumber(a.name) }}</span>
            <span class="dl-id">#{{ a.id }}</span>
            <div class="dl-actions" @click.stop>
              <button class="dl-act" title="Marquer sans Deezer" @click="markNoDeezer(a)">
                <AdminIcon name="link-off" :size="15" />
              </button>
              <button
                v-if="detectSeparator(a.name)"
                class="dl-act"
                title="Envoyer vers les flags"
                @click="flagArtist(a)"
              >
                <AdminIcon name="flag" :size="15" />
              </button>
              <button
                v-if="hasSpaces(a.name) || detectSeparator(a.name)"
                class="dl-act"
                title="Découper manuellement en plusieurs artistes"
                @click="openManualSplit(a)"
              >
                <AdminIcon name="split" :size="15" />
              </button>
            </div>
          </div>
          <p v-if="dbArtistResults.length === 0" class="dl-empty">Aucun artiste sans deezer_id.</p>
        </div>
      </div>

      <!-- Colonne droite : résultats Deezer -->
      <div class="dl-col">
        <div class="dl-col-head">
          <span class="dl-eyebrow">Résultats Deezer</span>
          <span class="dl-hits">{{ deezerHits.length }} hits</span>
        </div>
        <input
          v-model="linkDeezerQuery"
          class="dl-input"
          placeholder="Recherche sur Deezer…"
          @input="onDeezerSearch"
        />
        <div class="dl-list">
          <div
            v-for="h in deezerHits"
            :key="h.deezer_id"
            class="dl-row"
            :class="{ 'is-selected': selectedDeezerHit?.deezer_id === h.deezer_id }"
          >
            <div class="dl-thumb">
              <img v-if="h.picture" :src="h.picture" alt="" />
              <span v-else class="dl-fallback">{{ h.name?.[0] }}</span>
            </div>
            <div class="dl-main">
              <span class="dl-name">{{ h.name }}</span>
              <span class="dl-meta">
                {{ h.nb_fan?.toLocaleString('fr-FR') }} fans ·
                <a
                  :href="`https://www.deezer.com/artist/${h.deezer_id}`"
                  target="_blank"
                  class="dl-dz"
                  @click.stop
                  >dz:{{ h.deezer_id }}</a
                >
              </span>
            </div>
            <button class="btn btn--sm dl-choose" @click="selectedDeezerHit = h">Choisir</button>
          </div>
          <p v-if="linkDeezerQuery && deezerHits.length === 0" class="dl-empty">Aucun résultat.</p>
        </div>
      </div>
    </div>

    <!-- Carte de confirmation (D12) : bordée accent, geste à valider. -->
    <div v-if="selectedDbArtist && selectedDeezerHit" class="dl-confirm">
      <span class="dl-confirm-eyebrow">Confirmation</span>
      <p class="dl-confirm-text">
        Lier
        <strong>{{ stripDisambiguationNumber(selectedDbArtist.name) }}</strong>
        <span class="dl-mono">#{{ selectedDbArtist.id }}</span>
        à Deezer
        <strong>{{ selectedDeezerHit.name }}</strong>
        <span class="dl-mono">{{ selectedDeezerHit.deezer_id }}</span>
      </p>
      <div class="dl-confirm-actions">
        <button class="btn btn--sm" @click="cancelLink">Annuler</button>
        <button class="btn btn--sm btn--accent" :disabled="linking" @click="confirmLink">
          {{ linking ? 'Liaison…' : 'Confirmer' }}
        </button>
      </div>
      <span v-if="linkError" class="dl-err">{{ linkError }}</span>
    </div>

    <!-- Panneau de découpe embarqué (N-ary split + delete, composant partagé). -->
    <div v-if="splitArtist" class="dl-split">
      <ArtistSegmentSplitter
        :key="splitArtist.id"
        :raw="splitArtist.name"
        :pending="splitting"
        :error="splitError"
        @confirm="confirmManualSplit"
        @cancel="cancelSplit"
      />
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import { useTaskPoll } from '../../composables/useTaskPoll.js'
import { detectSeparator, splitUnits, stripDisambiguationNumber } from '../../utils/artistSplit.js'
import ArtistSegmentSplitter from './ArtistSegmentSplitter.vue'
import AdminIcon from './AdminIcon.vue'

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
// Two toggle views of the unlinked pool: 'active' (actionable, default) and
// 'dormant' (abandoned + unsplittable, browsable to confirm absence via link-off).
// Both counts come from the API response (global, q-independent).
const viewMode = ref('active')
const activeCount = ref(0)
const dormantCount = ref(0)
const deezerHits = ref([])
const selectedDbArtist = ref(null)
const selectedDeezerHit = ref(null)
const linking = ref(false)
const linkSuccess = ref(false)
const linkError = ref('')
let linkDbTimer = null
let linkDeezerTimer = null

// ── Ligne de résultat de job (D3) : paires icône/nombre/label, 3 canaux ──
// success (check, --pos-ink) · neutral (skip, --ink-2) · error (alert-triangle,
// --neg-ink). Les compteurs à 0 (ou absents) sont MASQUÉS (comptZero, défaut).
const CHANNEL_ICON = { success: 'check', neutral: 'skip', error: 'alert-triangle' }
function channelIcon(ch) {
  return CHANNEL_ICON[ch]
}
function fmtInt(n) {
  return Number(n).toLocaleString('fr-FR')
}
function buildPairs(defs) {
  return defs.filter((d) => d.value != null && d.value !== 0)
}

// Descripteur des 4 jobs de la région (D4) : titre, description, état courant,
// paires de résultat et déclencheur. La logique (refs, handlers, polls) est
// inchangée — ce computed n'est qu'une projection d'affichage.
const jobs = computed(() => [
  {
    key: 'sync',
    title: 'Sync artistes',
    desc: "Parse les noms d'artistes du catalog et peuple la table artistes. Idempotent.",
    running: syncing.value,
    label: 'Lancer la sync',
    error: syncError.value,
    run: runSync,
    pairs: syncResult.value
      ? buildPairs([
          { value: syncResult.value.created, label: 'créés', channel: 'success' },
          { value: syncResult.value.flagged, label: 'flags', channel: 'neutral' },
          { value: syncResult.value.skipped, label: 'skippés', channel: 'neutral' },
        ])
      : [],
  },
  {
    key: 'link',
    title: 'Liaison Deezer (artistes)',
    desc: 'Cherche sur Deezer les artistes sans deezer_id et les lie sur un match exact. Borné par run (budget) et sûr contre les boucles. Idempotent.',
    running: linkingArtists.value,
    label: 'Lier artistes (Deezer)',
    error: linkArtistsError.value,
    run: runLinkArtists,
    pairs: linkArtistsResult.value
      ? buildPairs([
          { value: linkArtistsResult.value.linked, label: 'liés', channel: 'success' },
          { value: linkArtistsResult.value.searched, label: 'cherchés', channel: 'neutral' },
          { value: linkArtistsResult.value.abandoned, label: 'abandonnés', channel: 'neutral' },
          {
            value: linkArtistsResult.value.dropped_by_budget,
            label: 'en attente',
            channel: 'neutral',
          },
          { value: linkArtistsResult.value.errors, label: 'erreurs', channel: 'error' },
        ])
      : [],
  },
  {
    key: 'artworks',
    title: 'Artworks artistes',
    desc: 'Fetche les images Deezer pour tous les artistes avec un deezer_id. Idempotent.',
    running: fetchingArtworks.value,
    label: 'Fetch artworks',
    error: artworksError.value,
    run: runFetchArtworks,
    pairs: artworksResult.value
      ? buildPairs([
          { value: artworksResult.value.fetched, label: 'artworks', channel: 'success' },
          { value: artworksResult.value.skipped, label: 'skippés', channel: 'neutral' },
          {
            value: artworksResult.value.dropped_by_budget,
            label: 'en attente',
            channel: 'neutral',
          },
          { value: artworksResult.value.errors, label: 'erreurs', channel: 'error' },
        ])
      : [],
  },
  {
    key: 'pl-artworks',
    title: 'Artworks playlists',
    desc: 'Fetche les images Deezer pour toutes les playlists sans artwork. Synchrone (~1s/playlist).',
    running: fetchingPlArtworks.value,
    label: 'Fetch artworks playlists',
    error: plArtworksError.value,
    run: runFetchPlArtworks,
    pairs: plArtworksResult.value
      ? buildPairs([
          { value: plArtworksResult.value.fetched, label: 'importés', channel: 'success' },
          { value: plArtworksResult.value.total, label: 'sans artwork', channel: 'neutral' },
          { value: plArtworksResult.value.failed, label: 'échoués', channel: 'error' },
        ])
      : [],
  },
])

function selectArtistAndSearch(a) {
  selectedDbArtist.value = a
  // Strip the Discogs "(N)" disambiguation counter to build the Deezer query
  // (Deezer knows "Willow", not "Willow (18)"). The stored name is untouched
  // until a confirmed link renames it to the canonical Deezer name. Shared with
  // the display strip (utils/artistSplit.stripDisambiguationNumber).
  linkDeezerQuery.value = stripDisambiguationNumber(a.name)
  onDeezerSearch()
}

function cancelLink() {
  selectedDbArtist.value = null
  selectedDeezerHit.value = null
}

// Sync poll: ignores network errors and keeps polling (stopOnError: false).
const syncPoll = useTaskPoll((taskId) => `/api/admin/tasks/${taskId}`, {
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

const artworksPoll = useTaskPoll((taskId) => `/api/admin/tasks/${taskId}`, {
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

const linkArtistsPoll = useTaskPoll((taskId) => `/api/admin/tasks/${taskId}`, {
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
  if (viewMode.value === 'dormant') params.dormant = true
  if (q) params.q = q
  const { data } = await api.get('/api/artists/', { params })
  dbArtistResults.value = data.items || data
  noDeezerTotal.value = typeof data.total === 'number' ? data.total : dbArtistResults.value.length
  activeCount.value = typeof data.active_count === 'number' ? data.active_count : 0
  dormantCount.value = typeof data.dormant_count === 'number' ? data.dormant_count : 0
}

function setView(mode) {
  if (viewMode.value === mode) return
  viewMode.value = mode
  selectedDbArtist.value = null
  fetchNoDeezerArtists(linkArtistQuery.value.trim())
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

// Manual split. SEPARATORS + detectSeparator live in utils/artistSplit.js (shared
// with ArtistSegmentSplitter, kept in parity with the backend auto-split
// detection). detectSeparator here only gates the flag/split row buttons and the
// blind flagArtist tokenisation.
const splitArtist = ref(null)
const splitting = ref(false)
const splitError = ref('')

function hasSpaces(name) {
  return name.trim().includes(' ')
}

function openManualSplit(artist) {
  splitArtist.value = artist
  splitError.value = ''
}

function cancelSplit() {
  splitArtist.value = null
}

// Kept segments come from ArtistSegmentSplitter; raw_artist_string stays the full
// original name (it drives the backend relink + cleanup), only `tokens` varies.
async function confirmManualSplit(tokens) {
  if (!splitArtist.value || !tokens.length) return
  splitting.value = true
  splitError.value = ''
  try {
    const { data: flag } = await api.post('/api/admin/artists/flags/manual', {
      raw_artist_string: splitArtist.value.name,
      tokens,
      reason: 'manual',
    })
    await api.post(`/api/admin/artists/flags/${flag.id}/resolve`, { action: 'split' })
    dbArtistResults.value = dbArtistResults.value.filter((a) => a.id !== splitArtist.value.id)
    noDeezerTotal.value = Math.max(0, noDeezerTotal.value - 1)
    splitArtist.value = null
  } catch (e) {
    splitError.value = e.response?.data?.detail || 'Erreur lors du split'
  } finally {
    splitting.value = false
  }
}

async function flagArtist(artist) {
  const sep = detectSeparator(artist.name)
  if (!sep) return
  // Split via the shared helper so the cut is case-insensitive, matching
  // detectSeparator (a raw String.split would miss an upper-cased " AND ").
  const tokens = splitUnits(artist.name, sep)
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
.aj-region,
.dl-section {
  container-type: inline-size;
}

/* ── Archétype A — région de jobs groupés (D4) : carte à bordure, sans ombre. ── */
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
.aj-row + .aj-row {
  border-top: 1px solid var(--line);
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
.aj-action {
  flex: none;
}

/* Job en cours (A7) : arc en rotation, mono --accent-ink — seul mouvement. */
.aj-running {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  margin-top: var(--space-1);
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--accent-ink);
}

/* Ligne de résultat (D3) : paires icône + nombre mono + label. */
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
.aj-pair--neutral {
  color: var(--ink-2);
}
.aj-pair--error {
  color: var(--neg-ink);
}
.aj-num {
  font: 600 var(--fs-xs)/1 var(--font-mono);
}
.aj-lbl {
  font: 400 var(--fs-xs)/1 var(--font-ui);
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

/* ── Archétype D — recherche + double liste (D12). ── */
.dl-section {
  margin-bottom: var(--space-8);
  padding: var(--space-5) var(--space-6);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.dl-head {
  margin-bottom: var(--space-4);
}
.dl-heading {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.dl-sub {
  margin-top: var(--space-1);
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
}
.dl-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}
.dl-col {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.dl-col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.dl-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.dl-hits {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.dl-input {
  width: 100%;
  height: 38px;
  padding: 0 var(--space-3);
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  font: 400 var(--fs-input)/1 var(--font-ui);
  color: var(--ink);
}
.dl-input:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}
.dl-list {
  max-height: 360px;
  overflow-y: auto;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.dl-row {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  min-height: 44px;
  padding: var(--space-1) var(--space-25);
  cursor: pointer;
  border-bottom: 1px solid var(--line);
}
.dl-row:last-child {
  border-bottom: 0;
}
.dl-row:hover {
  background: var(--surface-2);
}
.dl-row.is-selected {
  background: var(--accent-soft);
}
.dl-thumb {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--surface-3);
  border: 1px solid var(--line);
  overflow: hidden;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dl-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.dl-fallback {
  font: 600 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-3);
}
.dl-name {
  font: 500 var(--fs-base)/1.2 var(--font-ui);
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dl-id {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
  flex: none;
}
.dl-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.dl-meta {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.dl-dz {
  color: var(--accent-ink);
  text-decoration: none;
}
.dl-dz:hover {
  text-decoration: underline;
}
.dl-actions {
  margin-left: auto;
  display: flex;
  gap: var(--space-1);
  opacity: 0;
  transition: opacity 0.1s;
}
.dl-row:hover .dl-actions,
.dl-row:focus-within .dl-actions {
  opacity: 1;
}
.dl-act {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  border-radius: var(--r-xs);
  color: var(--ink-3);
  cursor: pointer;
  transition:
    color 0.12s,
    border-color 0.12s;
}
.dl-act:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}
.dl-choose {
  margin-left: auto;
  flex: none;
}
/* État vide (D12) : ligne nue, comme .at-empty/.sf-empty. La bordure arrondie
   vient du conteneur .dl-list (pas de .dl-empty) — quand la liste ne porte que
   l'état vide, on retire son cadre pour ne pas simuler un input désactivé. */
.dl-list:has(> .dl-empty) {
  border: none;
}
.dl-empty {
  padding: var(--space-4);
  font-size: var(--fs-sm);
  color: var(--ink-3);
}

/* Carte de confirmation (D12) : bordée accent, geste à valider (pas un succès). */
.dl-confirm {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2);
  border: 1px solid var(--accent);
  border-radius: var(--r-sm);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.dl-confirm-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent-ink);
}
.dl-confirm-text {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
}
.dl-confirm-text strong {
  color: var(--ink);
  font-weight: 600;
}
.dl-mono {
  font-family: var(--font-mono);
  color: var(--ink-3);
}
.dl-confirm-actions {
  display: flex;
  gap: var(--space-2);
}
.dl-err {
  font-size: var(--fs-sm);
  color: var(--neg-ink);
}

.dl-split {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Responsive — palier unique 859 px (D18). ── */
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
  }
  .aj-action .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  .aj-fail-msg {
    max-width: none;
  }

  .dl-grid {
    grid-template-columns: 1fr;
  }
  .dl-input {
    height: var(--touch-min);
  }
  /* Tactile : pas de survol → actions toujours visibles et 44 px. */
  .dl-actions {
    opacity: 1;
  }
  .dl-act {
    width: var(--touch-min);
    height: var(--touch-min);
  }
  .dl-choose {
    min-height: var(--touch-min);
  }
  .dl-confirm-actions {
    width: 100%;
  }
  .dl-confirm-actions .btn {
    flex: 1;
    min-height: var(--touch-min);
    justify-content: center;
  }
}
</style>
