<template>
  <div class="radar-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Radar</h1>
        <span class="view-sub">{{ total }} tracks</span>
      </div>
      <div class="filters">
        <input v-model="search" class="search-input" placeholder="Artiste ou titre…" @input="onSearch" />
        <select v-model="playlistFilter" class="select-filter" @change="onFilterChange">
          <option :value="null">Toutes les playlists</option>
          <option v-for="pl in playlists" :key="pl.id" :value="pl.id">{{ pl.title || pl.external_id }}</option>
        </select>
      </div>
    </header>

    <div class="tabs">
      <button v-for="tab in tabs" :key="tab.key"
        class="tab" :class="{ 'tab--active': activeTab === tab.key }"
        @click="setTab(tab.key)"
      >
        {{ tab.label }}
        <span v-if="counts[tab.key] != null" class="tab-count">{{ counts[tab.key] }}</span>
      </button>
    </div>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!total && !loading" class="state">Aucun track dans ce filtre.</div>
    <template v-else>
      <div class="table-wrap">
        <table class="track-table">
          <thead>
            <tr>
              <th class="col-play" />
              <th class="col-title sortable" :class="{ 'is-sorted': sortKey === 'title' }" @click="sort('title')">
                Track <span v-if="sortKey === 'title'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-genre">Genre</th>
              <th class="col-bpm num sortable" :class="{ 'is-sorted': sortKey === 'bpm' }" @click="sort('bpm')">
                BPM <span v-if="sortKey === 'bpm'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-key num">Key</th>
              <th class="col-duration num">Durée</th>
              <th class="col-playlist">Playlist</th>
              <th class="col-date sortable" :class="{ 'is-sorted': sortKey === 'detected_at' }" @click="sort('detected_at')">
                Détecté <span v-if="sortKey === 'detected_at'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-inlib">In lib</th>
              <th class="col-actions">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in items" :key="t.catalog_id" :class="{ 'is-playing': playingId === t.catalog_id }">
              <td class="col-play">
                <span
                  class="play-btn"
                  :class="{
                    'play-btn--disabled': !t.has_preview,
                    'play-btn--playing': playingId === t.catalog_id,
                  }"
                  @click="t.has_preview && togglePlay(t.catalog_id, t.catalog_id)"
                >
                  <svg v-if="playingId !== t.catalog_id" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
                  <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
                </span>
              </td>
              <td class="col-title">
                <div class="cell-track">
                  <div class="mini-art">
                    <img v-if="t.has_artwork" :src="`/storage/catalog-artworks/${t.catalog_id}.jpg`" :alt="t.title" />
                  </div>
                  <div class="track-info">
                    <RouterLink :to="`/catalog/${t.catalog_id}`" class="track-link">
                      <span class="track-title" :class="{ 'track-title--playing': playingId === t.catalog_id }">{{ t.title }}</span>
                    </RouterLink>
                    <span class="track-artist">{{ t.artist }}</span>
                  </div>
                </div>
              </td>
              <td class="col-genre"><span class="mono muted">{{ t.genre || '—' }}</span></td>
              <td class="col-bpm num"><span class="mono">{{ t.bpm != null ? Math.round(t.bpm) : '—' }}</span></td>
              <td class="col-key num"><span class="mono key-val">{{ t.key || '—' }}</span></td>
              <td class="col-duration num"><span class="mono">{{ t.duration_ms > 0 ? fmtMs(t.duration_ms) : '—' }}</span></td>
              <td class="col-playlist"><span class="playlist-tag" v-if="t.playlist_title">{{ t.playlist_title }}</span></td>
              <td class="col-date"><span class="mono muted">{{ formatDate(t.detected_at) }}</span></td>
              <td class="col-inlib">
                <LibDot :in-lib="t.in_lib" />
              </td>
              <td class="col-actions">
                <div class="action-group">
                  <button
                    v-for="a in stateActions"
                    :key="a.value"
                    class="action-btn"
                    :class="{ 'action-btn--active': t.status === a.value }"
                    :title="a.label"
                    @click="setState(t, a.value)"
                  >{{ a.icon }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="pagination">
        <button class="page-btn" :disabled="page === 1" @click="goTo(page - 1)">←</button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="page === totalPages" @click="goTo(page + 1)">→</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import axios from 'axios'
import LibDot from '../components/LibDot.vue'
import { storeToRefs } from 'pinia'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs } from '../utils/format'

const PAGE_SIZE = 50

const player = useAudioPlayer()
const { playingId } = storeToRefs(player)
const { toggle: togglePlay } = player

const items    = ref([])
const total    = ref(0)
const loading  = ref(false)
const search   = ref('')
const page     = ref(1)
const sortKey  = ref('detected_at')
const sortDir  = ref('desc')
const activeTab = ref(null)  // null = all
const counts   = ref({})
const playlists = ref([])
const playlistFilter = ref(null)

let searchTimer = null
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const tabs = [
  { key: null,      label: 'Tous' },
  { key: 'new',     label: 'New' },
  { key: 'seen',    label: 'Seen' },
  { key: 'added',   label: 'Added' },
  { key: 'ignored', label: 'Ignored' },
]

const stateActions = [
  { value: 'seen',    label: 'Vu',     icon: '👁' },
  { value: 'added',   label: 'Ajouté', icon: '✓' },
  { value: 'ignored', label: 'Ignoré', icon: '✕' },
]

function buildParams() {
  const params = { skip: (page.value - 1) * PAGE_SIZE, limit: PAGE_SIZE }
  if (activeTab.value) params.status = activeTab.value
  if (playlistFilter.value) params.playlist_id = playlistFilter.value
  if (search.value) params.search = search.value
  if (sortKey.value) params.sort = sortKey.value
  if (sortDir.value) params.order = sortDir.value
  return params
}

async function fetchPage() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/radar/full', { params: buildParams() })
    items.value = data.items
    total.value = data.total
    counts.value = data.counts || {}
  } finally {
    loading.value = false
  }
}

async function fetchPlaylists() {
  try {
    const { data } = await axios.get('/api/watchlist/')
    playlists.value = data
  } catch {}
}

function goTo(p) {
  page.value = p
  fetchPage()
}

function setTab(key) {
  activeTab.value = key
  page.value = 1
  fetchPage()
}

function onFilterChange() {
  page.value = 1
  fetchPage()
}

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    fetchPage()
  }, 300)
}

function sort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
  page.value = 1
  fetchPage()
}

async function setState(track, status) {
  if (track.status === status) {
    status = 'new' // toggle off → back to new
  }
  try {
    await axios.patch(`/api/radar/${track.catalog_id}/state`, { status })
    track.status = status
    // Update counts locally
    fetchPage()
  } catch {}
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  return `${day}/${month}`
}

onMounted(() => {
  fetchPage()
  fetchPlaylists()
})
</script>

<style scoped>
.radar-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1400px;
  margin: 0 auto;
}
.view-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.view-title {
  font: 600 22px/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}
.view-sub {
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
  margin-top: 4px;
  display: block;
}
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.search-input {
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 8px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
  min-width: 180px;
}
.search-input::placeholder { color: var(--ink-3); }
.select-filter {
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 7px 12px;
  font: 500 12px/1 var(--font-ui);
  color: var(--ink-2);
  cursor: pointer;
  outline: none;
}

/* Tabs */
.tabs {
  display: flex;
  gap: 2px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 0;
}
.tab {
  padding: 9px 16px;
  font: 500 12.5px/1 var(--font-ui);
  color: var(--ink-3);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tab:hover { color: var(--ink-2); }
.tab--active {
  color: var(--accent-ink);
  border-bottom-color: var(--accent);
}
.tab-count {
  font: 400 10.5px/1 var(--font-mono);
  color: var(--ink-3);
  background: var(--surface-2);
  padding: 2px 6px;
  border-radius: 8px;
}
.tab--active .tab-count {
  background: var(--accent-soft);
  color: var(--accent-ink);
}

/* Table */
.table-wrap { overflow-x: auto; }
.track-table {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
  font-size: 13.5px;
  table-layout: fixed;
}
.track-table thead th {
  text-align: left;
  padding: 0 14px 12px;
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
.track-table thead th.sortable { cursor: pointer; }
.track-table thead th.sortable:hover { color: var(--ink-2); }
.track-table thead th.is-sorted { color: var(--accent-ink); }
.track-table thead th.num { text-align: right; }
.track-table tbody td {
  height: var(--row-h);
  padding: 0 14px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
  overflow: hidden;
}
.track-table tbody tr:hover td { background: var(--surface-2); }
.track-table tbody tr.is-playing td { background: var(--accent-wash); }
.track-table tbody tr:last-child td { border-bottom: none; }
.sort-indicator { margin-left: 4px; color: var(--accent-ink); }

/* Column widths */
.col-play     { width: 38px; padding: 0 8px !important; }
.col-title    { width: auto; min-width: 180px; }
.col-genre    { width: 100px; }
.col-bpm      { width: 56px; }
.col-key      { width: 48px; }
.col-duration { width: 58px; }
.col-playlist { width: 120px; }
.col-date     { width: 64px; }
.col-inlib    { width: 48px; text-align: center; }
.col-actions  { width: 100px; }

/* Play btn */
.play-btn {
  width: 26px; height: 26px;
  border-radius: 50%;
  border: 1px solid var(--line-2);
  background: var(--surface);
  display: grid; place-items: center;
  color: var(--ink-2);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s, background 0.12s, color 0.12s;
}
.play-btn svg { width: 13px; height: 13px; }
.track-table tbody tr:hover .play-btn { opacity: 1; }
.play-btn--playing {
  opacity: 1 !important;
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-color: transparent;
}
.play-btn--disabled {
  opacity: 0.2 !important;
  cursor: default;
}

/* Track cell */
.cell-track { display: flex; align-items: center; gap: 12px; min-width: 0; }
.mini-art {
  width: 38px; height: 38px;
  flex: none;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  overflow: hidden;
  background: repeating-linear-gradient(135deg, var(--surface-2) 0 5px, var(--surface-3) 5px 10px);
}
.mini-art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.track-info { min-width: 0; flex: 1; }
.track-link {
  text-decoration: none;
  color: inherit;
  display: block;
  min-width: 0;
}
.track-link:hover .track-title { color: var(--accent-ink); }
.track-title {
  display: block;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.1s;
}
.track-title--playing { color: var(--accent-ink); }
.track-artist {
  display: block;
  font-size: 12px;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Cells */
.num { text-align: right; }
.mono { font-family: var(--font-mono); color: var(--ink-2); }
.key-val { color: var(--accent-ink); font-weight: 500; }
.muted { color: var(--ink-3); }

.playlist-tag {
  font: 400 11px/1 var(--font-mono);
  color: var(--ink-3);
  background: var(--surface-2);
  padding: 3px 7px;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  max-width: 100%;
}

/* Action buttons */
.action-group {
  display: flex;
  gap: 4px;
}
.action-btn {
  width: 26px; height: 26px;
  border-radius: var(--r-xs);
  border: 1px solid var(--line-2);
  background: var(--surface);
  cursor: pointer;
  font-size: 12px;
  display: grid;
  place-items: center;
  transition: background 0.12s, border-color 0.12s;
  opacity: 0.5;
}
.action-btn:hover {
  opacity: 1;
  background: var(--surface-2);
}
.action-btn--active {
  opacity: 1;
  background: var(--accent-soft);
  border-color: var(--accent);
}

/* Pagination */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 20px;
}
.page-btn {
  padding: 6px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
}
.page-btn:hover:not(:disabled) { background: var(--surface-2); }
.page-btn:disabled { opacity: 0.35; cursor: default; }
.page-info {
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
  min-width: 60px;
  text-align: center;
}
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>
