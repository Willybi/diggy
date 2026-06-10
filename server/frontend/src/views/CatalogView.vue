<template>
  <div class="catalog-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Catalog</h1>
        <span class="view-sub">{{ total }} tracks</span>
      </div>
      <div class="filters">
        <input v-model="search" class="search-input" placeholder="Artiste ou titre…" @input="onSearch" />
        <button class="chip" :class="{ 'chip--on': notInLib }" @click="toggleChip('notInLib')">Pas dans RB</button>
        <button class="chip" :class="{ 'chip--on': radarMin2 }" @click="toggleChip('radarMin2')">Radar ≥ 2</button>
      </div>
    </header>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!total && !loading" class="state">Aucun résultat.</div>
    <template v-else>
      <div class="table-wrap">
        <table class="track-table">
          <thead>
            <tr>
              <th class="col-play" />
              <th class="col-title sortable" :class="{ 'is-sorted': sortKey === 'title' }" @click="sort('title')">
                Track <span v-if="sortKey === 'title'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-radar sortable" :class="{ 'is-sorted': sortKey === 'nb_radar_playlists' }" @click="sort('nb_radar_playlists')">
                Radar <span v-if="sortKey === 'nb_radar_playlists'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-bpm num sortable" :class="{ 'is-sorted': sortKey === 'bpm' }" @click="sort('bpm')">
                BPM <span v-if="sortKey === 'bpm'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-key num">Key</th>
              <th class="col-duration num sortable" :class="{ 'is-sorted': sortKey === 'duration_ms' }" @click="sort('duration_ms')">
                Durée <span v-if="sortKey === 'duration_ms'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-inlib">In lib</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in items" :key="e.id">
              <td class="col-play">
                <span
                  class="play-btn"
                  :class="{ 'play-btn--disabled': !e.preview_url, 'play-btn--playing': playingId === e.id }"
                  @click="e.preview_url && togglePlay(e)"
                >
                  <svg v-if="playingId !== e.id" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
                  <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
                </span>
              </td>
              <td class="col-title">
                <div class="cell-track">
                  <div class="mini-art">
                    <img v-if="e.has_artwork" :src="`/storage/catalog-artworks/${e.id}.jpg`" :alt="e.title" />
                  </div>
                  <div class="track-info">
                    <span class="track-title">{{ e.title }}</span>
                    <span class="track-artist">{{ e.artist }}</span>
                  </div>
                </div>
              </td>
              <td class="col-radar">
                <span v-if="e.nb_radar_playlists > 0" class="radar-badge">{{ e.nb_radar_playlists }}</span>
                <span v-else class="muted">—</span>
              </td>
              <td class="col-bpm num"><span class="mono">{{ e.bpm ?? '—' }}</span></td>
              <td class="col-key num"><span class="mono key-val">{{ e.key || '—' }}</span></td>
              <td class="col-duration num"><span class="mono">{{ e.duration_ms ? formatDuration(e.duration_ms) : '—' }}</span></td>
              <td class="col-inlib"><InLibBadge :in-lib="e.in_lib" /></td>
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
import { ref, computed, watch, onMounted } from 'vue'
import axios from 'axios'
import InLibBadge from '../components/InLibBadge.vue'

const PAGE_SIZE = 50

const items      = ref([])
const total      = ref(0)
const loading    = ref(false)
const search     = ref('')
const notInLib   = ref(false)
const radarMin2  = ref(false)
const page       = ref(1)
const sortKey    = ref('nb_radar_playlists')
const sortDir    = ref('desc')
const playingId  = ref(null)

let audio = null

function togglePlay(entry) {
  if (playingId.value === entry.id) {
    audio.pause()
    playingId.value = null
    return
  }
  if (audio) audio.pause()
  audio = new Audio(entry.preview_url)
  audio.play()
  playingId.value = entry.id
  audio.addEventListener('ended', () => { playingId.value = null })
}

let searchTimer = null

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function buildParams() {
  const params = { skip: (page.value - 1) * PAGE_SIZE, limit: PAGE_SIZE }
  if (notInLib.value)           params.in_lib = false
  if (radarMin2.value)          params.min_radar_playlists = 2
  if (search.value)             params.search = search.value
  return params
}

async function fetchPage() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/catalog/', { params: buildParams() })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function goTo(p) {
  page.value = p
  fetchPage()
}

function toggleChip(chip) {
  if (chip === 'notInLib') notInLib.value = !notInLib.value
  if (chip === 'radarMin2') radarMin2.value = !radarMin2.value
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

function formatDuration(ms) {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

onMounted(fetchPage)
</script>

<style scoped>
.catalog-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1400px;
}
.view-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
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
.chip {
  padding: 7px 14px;
  border-radius: 999px;
  font: 500 12px/1 var(--font-ui);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.chip--on {
  background: var(--pos-soft);
  color: var(--pos-ink);
  border-color: transparent;
}

/* Table */
.table-wrap { overflow-x: auto; }
.track-table {
  width: 100%;
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
  overflow: hidden;
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
.track-table tbody tr:last-child td { border-bottom: none; }
.sort-indicator { margin-left: 4px; color: var(--accent-ink); }

/* Column widths */
.col-play     { width: 38px; padding: 0 8px !important; }
.col-title    { width: auto; }
.col-radar    { width: 72px; }
.col-bpm      { width: 72px; }
.col-key      { width: 60px; }
.col-duration { width: 72px; }
.col-inlib    { width: 110px; }

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
  color: var(--ink-3);
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
.track-title {
  display: block;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
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

.radar-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 22px; height: 22px; padding: 0 6px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 11px/1 var(--font-mono);
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
