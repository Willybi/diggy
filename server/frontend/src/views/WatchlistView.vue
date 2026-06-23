<template>
  <div class="playlists-view">
    <div class="page-head">
      <div class="titles">
        <h1>Playlists</h1>
        <div class="sub">Playlists surveillées par le Radar</div>
      </div>
      <div class="head-tools">
        <div class="filterseg">
          <button :class="{ on: mode === 'followed' }" @click="mode = 'followed'">Suivies</button>
          <button :class="{ on: mode === 'browse' }" @click="mode = 'browse'">Toutes</button>
        </div>
        <button
          class="btn-add"
          :class="{ cancel: showForm }"
          @click="toggleForm"
        >
          <span v-if="!showForm" class="plus">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14" stroke-linecap="round"/></svg>
          </span>
          <span class="addlbl">{{ showForm ? 'Annuler' : 'Ajouter' }}</span>
        </button>
      </div>
    </div>

    <div v-if="showForm" class="addform">
      <div class="addcard">
        <div class="addrow">
          <input
            v-model="inputValue"
            type="text"
            placeholder="URL Deezer, Tidal ou Spotify (ex : https://open.spotify.com/playlist/…)"
            @keydown.enter="addPlaylist"
            @input="formError = ''"
            autofocus
          />
          <button class="btn-go" :disabled="adding" @click="addPlaylist">
            {{ adding ? 'Ajout…' : 'Suivre' }}
          </button>
        </div>
        <span v-if="formError" class="form-error">{{ formError }}</span>
      </div>
    </div>

    <div v-if="loading" class="state">Chargement…</div>

    <div v-else-if="displayList.length === 0 && !showForm" class="state">
      <template v-if="mode === 'followed'">
        Aucune playlist suivie.
      </template>
      <template v-else>
        Aucune playlist dans le système.
      </template>
    </div>

    <div v-else-if="displayList.length > 0" class="table-wrap">
      <table class="tt">
        <colgroup>
          <col class="w-pl">
          <col class="w-creator col-creator">
          <col class="w-tracks col-tracks">
          <col class="w-crawl col-crawl">
          <col class="w-actions">
        </colgroup>
        <thead>
          <tr>
            <th>Playlist</th>
            <th class="col-creator">Créateur</th>
            <th class="num col-tracks">Tracks</th>
            <th class="col-crawl">Dernier crawl</th>
            <th class="end"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="pl in displayList" :key="pl.id">
            <td>
              <div class="pl-cell">
                <span class="aw">
                  <img v-if="pl.has_artwork" :src="`/storage/playlist-artworks/${pl.id}.jpg`" :alt="pl.title" />
                </span>
                <div class="pl-meta">
                  <div class="pl-top">
                    <RouterLink :to="`/playlists/${pl.id}`" class="pl-name">{{ pl.title || pl.external_id }}</RouterLink>
                    <span class="src-badge" :class="srcClass(pl.source)">{{ (pl.source || '').toUpperCase() }}</span>
                  </div>
                  <span class="pl-id">{{ pl.external_id }}</span>
                </div>
              </div>
            </td>
            <td class="col-creator">
              <span v-if="pl.owner" class="td-creator">{{ pl.owner }}</span>
              <span v-else class="td-empty">—</span>
            </td>
            <td class="num col-tracks">
              <span v-if="pl.track_count != null" class="td-num">{{ pl.track_count }}</span>
              <span v-else class="td-empty">—</span>
            </td>
            <td class="col-crawl">
              <span v-if="crawlStatus[pl.id] === 'running'" class="crawl-badge running">Crawl en cours</span>
              <span v-else-if="crawlStatus[pl.id] === 'queued'" class="crawl-badge queued">En file d'attente</span>
              <span v-else class="td-date">{{ formatCrawled(pl.last_crawled_at) }}</span>
            </td>
            <td class="end">
              <div class="actions">
                <template v-if="pl.followed">
                  <button
                    class="btn-crawl"
                    :disabled="!!crawlStatus[pl.id] || isCooldown(pl)"
                    :title="crawlStatus[pl.id] ? 'Crawl en cours' : isCooldown(pl) ? 'Déjà crawlé dans les 12 dernières heures' : 'Lancer un crawl maintenant'"
                    @click.stop="triggerCrawl(pl)"
                  >{{ crawlStatus[pl.id] ? 'Crawl…' : isCooldown(pl) ? 'Déjà crawlé' : 'Crawl now' }}</button>
                  <button class="btn-follow following" @click.stop="unfollow(pl.id)">Ne plus suivre</button>
                </template>
                <template v-else>
                  <button
                    class="btn-follow"
                    :disabled="following[pl.id]"
                    @click.stop="followPlaylist(pl.id)"
                  >{{ following[pl.id] ? 'Suivi…' : 'Suivre' }}</button>
                </template>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import axios from 'axios'

const COOLDOWN_MS = 12 * 3600 * 1000

const playlists = ref([])
const browsePlaylists = ref([])
const loading = ref(false)
const showForm = ref(false)
const inputValue = ref('')
const formError = ref('')
const adding = ref(false)
const mode = ref('followed')
const crawlStatus = reactive({})  // pl.id → 'queued' | 'running' | null
const following = reactive({})
const pollTimers = {}

const displayList = computed(() => {
  if (mode.value === 'followed')
    return playlists.value.map(p => ({ ...p, followed: true }))
  return browsePlaylists.value
})

function srcClass(source) {
  const s = (source || '').toLowerCase()
  if (s === 'deezer') return 'deezer'
  if (s === 'tidal') return 'tidal'
  if (s === 'spotify') return 'spotify'
  return 'tidal'
}

function isCooldown(pl) {
  if (!pl.last_crawled_at) return false
  return Date.now() - new Date(pl.last_crawled_at).getTime() < COOLDOWN_MS
}

function toggleForm() {
  showForm.value = !showForm.value
  if (!showForm.value) {
    inputValue.value = ''
    formError.value = ''
  }
}

function parsePlaylistInput(input) {
  const s = input.trim()
  let match = s.match(/deezer\.com\/.*playlist\/(\d+)/)
  if (match) return { external_id: match[1], source: 'deezer' }
  match = s.match(/tidal\.com\/(?:browse\/)?playlist\/([a-f0-9-]+)/i)
  if (match) return { external_id: match[1], source: 'tidal' }
  match = s.match(/open\.spotify\.com\/playlist\/([a-zA-Z0-9]+)/)
  if (match) return { external_id: match[1], source: 'spotify' }
  if (/^\d+$/.test(s)) return { external_id: s, source: 'deezer' }
  if (/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(s))
    return { external_id: s, source: 'tidal' }
  return null
}

async function fetchPlaylists() {
  loading.value = true
  try {
    const [followed, all] = await Promise.all([
      axios.get('/api/watchlist/'),
      axios.get('/api/watchlist/browse'),
    ])
    playlists.value = followed.data
    browsePlaylists.value = all.data
  } finally {
    loading.value = false
  }
}

async function addPlaylist() {
  formError.value = ''
  const parsed = parsePlaylistInput(inputValue.value)
  if (!parsed) {
    formError.value = 'URL ou ID invalide (Deezer, Tidal ou Spotify)'
    return
  }
  adding.value = true
  try {
    const { data } = await axios.post('/api/watchlist/', parsed)
    inputValue.value = ''
    showForm.value = false
    await fetchPlaylists()
    startPolling(data.id)
  } catch (e) {
    if (e.response?.status === 409) {
      formError.value = 'Playlist déjà suivie'
    } else {
      formError.value = 'Erreur lors de l\'ajout'
    }
  } finally {
    adding.value = false
  }
}

async function unfollow(id) {
  await axios.delete(`/api/watchlist/${id}`)
  await fetchPlaylists()
}

async function followPlaylist(id) {
  following[id] = true
  try {
    await axios.post(`/api/watchlist/${id}/follow`)
    await fetchPlaylists()
    startPolling(id)
  } catch (e) {
    if (e.response?.status === 409) {
      await fetchPlaylists()
    }
  } finally {
    following[id] = false
  }
}

async function triggerCrawl(pl) {
  crawlStatus[pl.id] = 'queued'
  try {
    await axios.post(`/api/watchlist/${pl.id}/crawl`)
    startPolling(pl.id)
  } catch (e) {
    if (e.response?.status === 429) {
      await fetchPlaylists()
    }
    delete crawlStatus[pl.id]
  }
}

function startPolling(playlistId) {
  stopPolling(playlistId)
  if (!crawlStatus[playlistId]) crawlStatus[playlistId] = 'queued'
  pollTimers[playlistId] = setInterval(async () => {
    try {
      const { data } = await axios.get(`/api/watchlist/${playlistId}/crawl-status`)
      if (!data.status || data.status === 'done') {
        stopPolling(playlistId)
        delete crawlStatus[playlistId]
        await fetchPlaylists()
      } else {
        crawlStatus[playlistId] = data.status
      }
    } catch {
      stopPolling(playlistId)
      delete crawlStatus[playlistId]
    }
  }, 3000)
}

function startPollingIfActive(pl) {
  if (pl.current_task_id) {
    crawlStatus[pl.id] = 'queued'
    startPolling(pl.id)
  }
}

function stopPolling(playlistId) {
  if (pollTimers[playlistId]) {
    clearInterval(pollTimers[playlistId])
    delete pollTimers[playlistId]
  }
}

function formatCrawled(iso) {
  if (!iso) return 'jamais'
  const d = new Date(iso)
  const now = new Date()
  const diffDays = Math.floor((now - d) / 86400000)
  if (diffDays === 0) return "aujourd'hui"
  if (diffDays === 1) return 'il y a 1 j'
  return `il y a ${diffDays} j`
}

onMounted(async () => {
  await fetchPlaylists()
  // Auto-detect playlists with active crawls
  for (const pl of [...playlists.value, ...browsePlaylists.value]) {
    startPollingIfActive(pl)
  }
})
onUnmounted(() => Object.keys(pollTimers).forEach(stopPolling))
</script>

<style scoped>
.playlists-view {
  container-type: inline-size;
}

.page-head {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 26px 30px 18px;
  flex-wrap: wrap;
}
.page-head .titles h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.3px;
}
.page-head .sub {
  margin-top: 5px;
  font: 500 13px/1 var(--font-mono);
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

/* filtre segmenté */
.filterseg {
  display: flex;
  gap: 2px;
  background: var(--surface-2);
  padding: 3px;
  border-radius: var(--r-sm);
}
.filterseg button {
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  padding: 8px 14px;
  border-radius: var(--r-xs);
  cursor: pointer;
}
.filterseg button:hover { color: var(--ink); }
.filterseg button.on {
  background: var(--accent-soft);
  color: var(--accent-ink);
}

/* bouton ajouter */
.btn-add {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 38px;
  padding: 0 16px;
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 13.5px var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-add:hover { background: var(--accent-hover); }
.btn-add svg { width: 15px; height: 15px; }
.btn-add.cancel {
  background: var(--surface);
  color: var(--ink-2);
  border-color: var(--line-2);
}
.btn-add.cancel .plus { display: none; }

/* formulaire d'ajout */
.addform {
  padding: 0 30px 6px;
}
.addcard {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  padding: 18px;
  margin-bottom: 8px;
}
.addrow {
  display: flex;
  gap: 10px;
}
.addrow input {
  flex: 1;
  min-width: 0;
  height: 42px;
  padding: 0 14px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  font: 400 14px var(--font-ui);
  color: var(--ink);
  outline: none;
}
.addrow input::placeholder { color: var(--ink-3); }
.addrow input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.btn-go {
  height: 42px;
  padding: 0 20px;
  border: 0;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--on-accent);
  font: 600 13.5px var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-go:hover { background: var(--accent-hover); }
.btn-go:disabled { opacity: 0.5; cursor: default; }
.form-error {
  display: block;
  margin-top: 10px;
  font: 400 12px/1 var(--font-mono);
  color: var(--neg-ink);
}

/* table */
.table-wrap {
  padding: 4px 30px 30px;
  overflow-x: auto;
}
table.tt {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 440px;
}
table.tt col.w-pl      { width: auto; }
table.tt col.w-creator { width: 180px; }
table.tt col.w-tracks  { width: 84px; }
table.tt col.w-crawl   { width: 128px; }
table.tt col.w-actions { width: 220px; }

table.tt thead th {
  position: sticky;
  top: 0;
  font: 600 10.5px/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 14px 11px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.num, table.tt td.num { text-align: center; }
table.tt th.end, table.tt td.end { text-align: right; }
table.tt tbody tr {
  border-bottom: 1px solid var(--line);
  height: var(--row-h);
}
table.tt tbody tr:hover { background: var(--surface-2); }
table.tt td { padding: 0 14px; vertical-align: middle; }

/* cellule playlist */
.pl-cell {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
}
.aw {
  width: 40px;
  height: 40px;
  border-radius: var(--r-xs);
  flex: none;
  background: var(--surface-3);
  overflow: hidden;
}
.aw img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.pl-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pl-top {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.pl-name {
  font: 500 14px var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-decoration: none;
}
.pl-name:hover { color: var(--accent-ink); }
.pl-id {
  font: 500 11px var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}

/* badge source */
.src-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 7px;
  border-radius: 4px;
  font: 600 10px/1 var(--font-mono);
  letter-spacing: 0.06em;
  white-space: nowrap;
  flex: none;
}
.src-badge.deezer  { background: var(--accent-soft); color: var(--accent-ink); }
.src-badge.tidal   { background: var(--surface-3); color: var(--ink-2); border: 1px solid var(--line-2); }
.src-badge.spotify { background: var(--pos-soft); color: var(--pos-ink); }

/* créateur */
.td-creator { font: 400 13px var(--font-ui); color: var(--ink-2); }

/* numbers + dates */
.td-num { font: 600 13px var(--font-mono); color: var(--ink); }
.td-date { font: 500 12.5px var(--font-mono); color: var(--ink-2); white-space: nowrap; }
.td-empty { font: 500 13px var(--font-mono); color: var(--ink-3); }

/* actions */
.actions {
  display: inline-flex;
  gap: 8px;
  justify-content: flex-end;
  align-items: center;
}
.btn-crawl {
  height: 32px;
  padding: 0 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 12.5px var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-crawl:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent-ink);
}
.btn-crawl:disabled { opacity: 0.45; cursor: default; }

.btn-follow {
  height: 32px;
  padding: 0 16px;
  border-radius: 999px;
  cursor: pointer;
  white-space: nowrap;
  font: 600 12.5px var(--font-ui);
  border: 1px solid transparent;
  background: var(--accent);
  color: var(--on-accent);
}
.btn-follow:hover { background: var(--accent-hover); }
.btn-follow:disabled { opacity: 0.5; cursor: default; }
.btn-follow.following {
  background: transparent;
  color: var(--ink-3);
  border-color: var(--line-2);
}
.btn-follow.following:hover {
  color: var(--neg-ink);
  border-color: var(--neg);
  background: var(--neg-soft);
}

/* crawl status badges */
.crawl-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font: 500 11px/1 var(--font-mono);
  white-space: nowrap;
}
.crawl-badge::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.crawl-badge.running {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.crawl-badge.running::before {
  background: var(--accent-ink);
  animation: pulse-dot 1.2s ease-in-out infinite;
}
.crawl-badge.queued {
  background: var(--surface-3);
  color: var(--ink-2);
}
.crawl-badge.queued::before {
  background: var(--ink-3);
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.state {
  padding: 60px 30px;
  color: var(--ink-3);
  font: 400 14px var(--font-ui);
  text-align: center;
}

/* ── responsive (container queries) ── */
@container (max-width: 1040px) { .col-crawl { display: none; } }
@container (max-width: 820px) {
  .col-creator { display: none; }
  .head-tools { width: 100%; margin-left: 0; }
}
@container (max-width: 640px) {
  .col-tracks { display: none; }
  .page-head, .addform, .table-wrap { padding-left: 18px; padding-right: 18px; }
}
</style>
