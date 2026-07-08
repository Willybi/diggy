<template>
  <div class="playlists-view">
    <div class="page-head">
      <div class="titles">
        <h1>Playlists</h1>
        <div class="sub">
          {{ browsePlaylists.length }} playlist{{ browsePlaylists.length !== 1 ? 's' : '' }}
          <span v-if="mode !== 'all'" class="muted"
            >· {{ filteredList.length }}
            {{
              mode === 'liked' ? 'likées' : mode === 'disliked' ? 'dislikées' : 'à explorer'
            }}</span
          >
        </div>
      </div>
      <div class="head-tools">
        <SegFilter
          v-model="mode"
          :options="[
            { value: 'all', label: 'Toutes' },
            { value: 'liked', label: 'Liked', cls: 'liked' },
            { value: 'disliked', label: 'Disliked', cls: 'disliked' },
            { value: 'unrated', label: 'À explorer' },
          ]"
        />
        <button class="btn-add" :class="{ cancel: showForm }" @click="toggleForm">
          <span v-if="!showForm" class="plus">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M12 5v14M5 12h14" stroke-linecap="round" />
            </svg>
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
      Aucune playlist trouvée.
    </div>

    <div v-else-if="displayList.length > 0" class="table-wrap">
      <table class="tt">
        <colgroup>
          <col class="w-pl" />
          <col class="w-creator col-creator" />
          <col class="w-tracks col-tracks" />
          <col class="w-crawl col-crawl" />
          <col class="w-avis" />
        </colgroup>
        <thead>
          <tr>
            <th class="sortable" @click="toggleSort('title')">
              Playlist
              <span v-if="sortKey === 'title'" class="arr">{{
                sortDir === 'asc' ? '↑' : '↓'
              }}</span>
            </th>
            <th class="col-creator sortable" @click="toggleSort('creator')">
              Créateur
              <span v-if="sortKey === 'creator'" class="arr">{{
                sortDir === 'asc' ? '↑' : '↓'
              }}</span>
            </th>
            <th class="num col-tracks sortable" @click="toggleSort('tracks')">
              Tracks
              <span v-if="sortKey === 'tracks'" class="arr">{{
                sortDir === 'asc' ? '↑' : '↓'
              }}</span>
            </th>
            <th class="col-crawl sortable" @click="toggleSort('crawl')">
              Dernier crawl
              <span v-if="sortKey === 'crawl'" class="arr">{{
                sortDir === 'asc' ? '↑' : '↓'
              }}</span>
            </th>
            <th class="end sortable" @click="toggleSort('avis')">
              Avis
              <span v-if="sortKey === 'avis'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="pl in displayList"
            :key="pl.id"
            :class="{
              liked: opinions.get('playlist', pl.id) === 'liked',
              disliked: opinions.get('playlist', pl.id) === 'disliked',
            }"
          >
            <td>
              <RouterLink :to="`/playlists/${pl.id}`" class="pl-cell">
                <span class="aw">
                  <img
                    v-if="pl.has_artwork"
                    :src="`/storage/playlist-artworks/${pl.id}.jpg`"
                    :alt="pl.title"
                  />
                </span>
                <div class="pl-meta">
                  <div class="pl-top">
                    <span class="pl-name">{{ pl.title || pl.external_id }}</span>
                    <SourceBadge :source="pl.source || 'deezer'" />
                  </div>
                  <span class="pl-id">{{ pl.external_id }}</span>
                </div>
              </RouterLink>
            </td>
            <td class="col-creator">
              <span v-if="pl.owner" class="td-creator">{{ pl.owner }}</span>
              <span v-else class="td-empty">—</span>
            </td>
            <td class="num col-tracks">
              <span v-if="pl.track_count != null" class="td-num">{{ pl.track_count }}</span>
              <span v-else class="td-empty">—</span>
            </td>
            <td class="col-crawl" @click.stop>
              <span v-if="crawlStatus[pl.id] === 'running'" class="crawl running"
                ><span class="cdot"></span><span class="clbl">En cours</span></span
              >
              <span v-else-if="crawlStatus[pl.id] === 'queued'" class="crawl queued"
                ><span class="cdot"></span><span class="clbl">En attente</span></span
              >
              <span v-else-if="crawlStatus[pl.id] === 'done'" class="crawl done"
                ><span class="cdot"></span><span class="clbl">Crawlé</span></span
              >
              <template v-else>
                <span class="td-date">{{ formatCrawled(pl.last_crawled_at) }}</span>
                <button v-if="!isCooldown(pl)" class="btn-crawl" @click="triggerCrawl(pl)">
                  Crawl
                </button>
              </template>
            </td>
            <td class="end td-avis" @click.stop>
              <LikeDislike
                :model-value="opinions.get('playlist', pl.id)"
                @update:model-value="(v) => setOpinion(pl.id, v)"
              />
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="totalPages > 1" class="pagination">
        <button :disabled="page <= 1" @click="page--">&lsaquo;</button>
        <span class="pg-info">{{ page }} / {{ totalPages }}</span>
        <button :disabled="page >= totalPages" @click="page++">&rsaquo;</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, reactive } from 'vue'
import api from '../utils/api.js'
import { useOpinionsStore } from '../stores/opinions.js'
import LikeDislike from '../components/LikeDislike.vue'
import SourceBadge from '../components/SourceBadge.vue'
import SegFilter from '../components/SegFilter.vue'

const opinions = useOpinionsStore()
const COOLDOWN_MS = 12 * 3600 * 1000

const browsePlaylists = ref([])
const loading = ref(false)
const showForm = ref(false)
const inputValue = ref('')
const formError = ref('')
const adding = ref(false)
const mode = ref('all')
const crawlStatus = reactive({}) // pl.id → 'queued' | 'running' | null
const page = ref(1)
const perPage = 25

// Sort
const sortKey = ref('title')
const sortDir = ref('asc')

watch([mode, sortKey, sortDir], () => {
  page.value = 1
})

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'title' || key === 'creator' ? 'asc' : 'desc'
  }
}

function sortValue(p, key) {
  if (key === 'title') return (p.title || p.external_id || '').toLowerCase()
  if (key === 'creator') return (p.owner || '').toLowerCase()
  if (key === 'tracks') return p.track_count ?? -1
  if (key === 'crawl') return p.last_crawled_at || ''
  if (key === 'avis') {
    const op = opinions.get('playlist', p.id)
    if (op === 'liked') return 2
    if (op === 'disliked') return 1
    return 0
  }
  return 0
}
const pollTimers = {}

const filteredList = computed(() => {
  let list
  if (mode.value === 'liked') {
    list = browsePlaylists.value.filter((p) => opinions.get('playlist', p.id) === 'liked')
  } else if (mode.value === 'disliked') {
    list = browsePlaylists.value.filter((p) => opinions.get('playlist', p.id) === 'disliked')
  } else if (mode.value === 'unrated') {
    list = browsePlaylists.value.filter((p) => !opinions.get('playlist', p.id))
  } else {
    list = [...browsePlaylists.value]
  }
  const dir = sortDir.value === 'asc' ? 1 : -1
  const key = sortKey.value
  list.sort((a, b) => {
    const va = sortValue(a, key)
    const vb = sortValue(b, key)
    if (va < vb) return -1 * dir
    if (va > vb) return 1 * dir
    return 0
  })
  return list
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredList.value.length / perPage)))

const displayList = computed(() => {
  const start = (page.value - 1) * perPage
  return filteredList.value.slice(start, start + perPage)
})

function isCooldown(pl) {
  if (!pl.last_crawled_at) return false
  return Date.now() - new Date(pl.last_crawled_at).getTime() < COOLDOWN_MS
}

async function triggerCrawl(pl) {
  crawlStatus[pl.id] = 'queued'
  try {
    await api.post(`/api/watchlist/${pl.id}/crawl`)
    startPolling(pl.id)
  } catch (e) {
    if (e.response?.status === 429) {
      await fetchPlaylists()
    }
    delete crawlStatus[pl.id]
  }
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
    const { data } = await api.get('/api/watchlist/browse')
    browsePlaylists.value = data.items
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
    const { data } = await api.post('/api/watchlist/', parsed)
    inputValue.value = ''
    showForm.value = false
    await fetchPlaylists()
    startPolling(data.id)
  } catch (e) {
    if (e.response?.status === 409) {
      formError.value = 'Playlist déjà suivie'
    } else {
      formError.value = "Erreur lors de l'ajout"
    }
  } finally {
    adding.value = false
  }
}

function startPolling(playlistId) {
  stopPolling(playlistId)
  if (!crawlStatus[playlistId]) crawlStatus[playlistId] = 'queued'
  pollTimers[playlistId] = setInterval(async () => {
    try {
      const { data } = await api.get(`/api/watchlist/${playlistId}/crawl-status`)
      if (data.status === 'done') {
        stopPolling(playlistId)
        crawlStatus[playlistId] = 'done'
        await fetchPlaylists()
        setTimeout(() => {
          delete crawlStatus[playlistId]
        }, 3000)
      } else if (!data.status) {
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
  }, 4000)
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

async function setOpinion(plId, val) {
  await opinions.set('playlist', plId, val)
  await fetchPlaylists()
}

onMounted(async () => {
  await fetchPlaylists()
  for (const pl of browsePlaylists.value) {
    startPollingIfActive(pl)
  }
})
onUnmounted(() => Object.keys(pollTimers).forEach(stopPolling))
</script>

<style scoped>
.playlists-view {
  container-type: inline-size;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

.page-head .titles h1 {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -0.3px;
}
.page-head .sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.sub .muted {
  color: var(--ink-3);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* bouton ajouter */
.btn-add {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-add:hover {
  background: var(--accent-hover);
}
.btn-add svg {
  width: 15px;
  height: 15px;
}
.btn-add.cancel {
  background: var(--surface);
  color: var(--ink-2);
  border-color: var(--line-2);
}
.btn-add.cancel .plus {
  display: none;
}

/* formulaire d'ajout */
.addform {
  padding: 0 var(--page-px) var(--space-15);
}
.addcard {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  padding: var(--space-5);
  margin-bottom: var(--space-2);
}
.addrow {
  display: flex;
  gap: var(--space-25);
}
.addrow input {
  flex: 1;
  min-width: 0;
  height: 42px;
  padding: 0 var(--space-4);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
  outline: none;
}
.addrow input::placeholder {
  color: var(--ink-3);
}
.addrow input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.btn-go {
  height: 42px;
  padding: 0 var(--space-5);
  border: 0;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-go:hover {
  background: var(--accent-hover);
}
.btn-go:disabled {
  opacity: 0.5;
  cursor: default;
}
.form-error {
  display: block;
  margin-top: var(--space-25);
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--neg-ink);
}

/* table */
.table-wrap {
  padding: var(--space-1) var(--page-px) var(--space-8);
  overflow-x: auto;
}
table.tt {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 440px;
}
table.tt col.w-pl {
  width: auto;
}
table.tt col.w-creator {
  width: 180px;
}
table.tt col.w-tracks {
  width: 84px;
}
table.tt col.w-crawl {
  width: 140px;
}
table.tt col.w-avis {
  width: 100px;
}

table.tt thead th {
  position: sticky;
  top: 0;
  font: 600 var(--fs-label)/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 var(--space-3) var(--space-25);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.sortable {
  cursor: pointer;
}
table.tt th.sortable:hover {
  color: var(--ink-2);
}
table.tt th .arr {
  color: var(--accent-ink);
  margin-left: var(--space-1);
}
table.tt th.num,
table.tt td.num {
  text-align: center;
}
table.tt th.end,
table.tt td.end {
  text-align: right;
}
table.tt tbody tr {
  border-bottom: 1px solid var(--line);
  height: var(--row-h);
}
table.tt tbody tr:hover {
  background: var(--surface-2);
}
table.tt td {
  padding: 0 var(--space-3);
  vertical-align: middle;
}

/* cellule playlist */
.pl-cell {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  text-decoration: none;
  color: inherit;
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
  gap: var(--space-1);
}
.pl-top {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.pl-name {
  font: 500 var(--fs-base) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pl-cell:hover .pl-name {
  color: var(--accent-ink);
}
.pl-id {
  font: 500 var(--fs-xs) var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}

/* créateur */
.td-creator {
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-2);
}

/* numbers + dates */
.td-num {
  font: 600 var(--fs-sm) var(--font-mono);
  color: var(--ink);
}
.td-date {
  font: 500 var(--fs-table-sm) var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
}
.td-empty {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-3);
}

/* ── avis: hover-reveal LikeDislike ── */
.td-avis :deep(.ld-btn) {
  opacity: 0;
  transition: opacity 0.14s;
}
table.tt tbody tr:hover .td-avis :deep(.ld-btn) {
  opacity: 1;
}
.td-avis :deep(.ld[data-state='liked'] .ld-btn.like),
.td-avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  opacity: 1;
}

/* ── row avis states ── */
table.tt tbody tr.liked {
  background: var(--pos-wash);
}
table.tt tbody tr.liked:hover {
  background: var(--pos-wash-2);
}
table.tt tbody tr.disliked td:not(.td-avis) {
  opacity: 0.42;
}
table.tt tbody tr.disliked:hover td:not(.td-avis) {
  opacity: 0.7;
}

/* crawl button */
.btn-crawl {
  height: 24px;
  padding: 0 var(--space-25);
  border-radius: var(--r-xs);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 var(--fs-xs) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  margin-left: var(--space-2);
}
.btn-crawl:hover {
  border-color: var(--accent);
  color: var(--accent-ink);
}

/* crawl status chips (inline dot + label) */
.crawl {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  white-space: nowrap;
}
.crawl .cdot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.crawl .clbl {
  font: 600 var(--fs-sm)/1 var(--font-ui);
}
.crawl.running .cdot {
  background: var(--accent);
}
.crawl.running .clbl {
  color: var(--ink);
}
.crawl.queued .cdot {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--ink-3);
}
.crawl.queued .clbl {
  color: var(--ink-3);
}
.crawl.done .cdot {
  background: var(--pos);
}
.crawl.done .clbl {
  color: var(--pos-ink);
}
@keyframes crawlring {
  0% {
    box-shadow: 0 0 0 0 color-mix(in oklch, var(--accent) 60%, transparent);
  }
  70% {
    box-shadow: 0 0 0 6px transparent;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
  }
}
@media (prefers-reduced-motion: no-preference) {
  .crawl.running .cdot {
    animation: crawlring 1.5s ease-out infinite;
  }
}

/* pagination */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-5) 0 var(--space-1);
}
.pagination button {
  width: 32px;
  height: 32px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 600 var(--fs-title)/1 var(--font-ui);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.pagination button:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent-ink);
}
.pagination button:disabled {
  opacity: 0.3;
  cursor: default;
}
.pg-info {
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}

.state {
  padding: var(--space-15x) var(--page-px);
  color: var(--ink-3);
  font: 400 var(--fs-base) var(--font-ui);
  text-align: center;
}

/* ── responsive (container queries) ── */
@container (max-width: 1040px) {
  .col-crawl {
    display: none;
  }
}
@container (max-width: 820px) {
  .col-creator {
    display: none;
  }
  .head-tools {
    width: 100%;
    margin-left: 0;
  }
}
@container (max-width: 640px) {
  .col-tracks {
    display: none;
  }
  .page-head,
  .addform,
  .table-wrap {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .addrow {
    flex-direction: column;
  }
  .btn-go {
    width: 100%;
  }
  /* Touch: always show avis buttons */
  .td-avis :deep(.ld-btn) {
    opacity: 1;
  }
}
</style>
