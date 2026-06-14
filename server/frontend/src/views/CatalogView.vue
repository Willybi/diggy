<template>
  <div class="catalog-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Catalog</h1>
        <span class="view-sub">
          {{ inLib ? `${total} tracks · in lib` : `${total} tracks · ${nLib} in lib` }}
        </span>
      </div>
      <div class="filters">
        <input v-model="search" class="search-input" placeholder="Artiste ou titre…" @input="onSearch" />
        <button class="chip" :class="{ 'chip--on': notInLib }" @click="toggleNotInLib">Pas dans RB</button>
        <button class="chip" :class="{ 'chip--on-radar': radarMin2 }" @click="toggleRadarMin2">Radar ≥ 2</button>
        <button class="chip" :class="{ 'chip--on': inLib }" @click="toggleInLib">In lib</button>
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
              <th class="col-style sortable" :class="{ 'is-sorted': sortKey === 'style' }" @click="sort('style')">
                Style <span v-if="sortKey === 'style'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-bpm num sortable" :class="{ 'is-sorted': sortKey === 'bpm' }" @click="sort('bpm')">
                BPM <span v-if="sortKey === 'bpm'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-key num sortable" :class="{ 'is-sorted': sortKey === 'key' }" @click="sort('key')">
                Key <span v-if="sortKey === 'key'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-duration num sortable" :class="{ 'is-sorted': sortKey === 'duration_ms' }" @click="sort('duration_ms')">
                Durée <span v-if="sortKey === 'duration_ms'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-rating num sortable" :class="{ 'is-sorted': sortKey === 'rating' }" @click="sort('rating')">
                Rating <span v-if="sortKey === 'rating'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-radar sortable" :class="{ 'is-sorted': sortKey === 'nb_radar_playlists' }" @click="sort('nb_radar_playlists')">
                Radar <span v-if="sortKey === 'nb_radar_playlists'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-inlib">In lib</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in items" :key="e.id" :class="{ 'is-playing': playingId === e.id }">
              <td class="col-play">
                <span
                  class="play-btn"
                  :class="{
                    'play-btn--disabled': !e.has_preview || (inLib && !e.in_lib),
                    'play-btn--playing': playingId === e.id,
                    'play-btn--hidden': inLib && !e.in_lib,
                  }"
                  @click="e.has_preview && !(inLib && !e.in_lib) && togglePlay(e.id, e.id)"
                >
                  <svg v-if="playingId !== e.id" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
                  <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
                </span>
              </td>
              <td class="col-title">
                <div class="cell-track">
                  <div class="mini-art">
                    <img v-if="e.has_artwork"
                      :src="e.lib_track_id ? `/storage/artworks/${e.lib_track_id}.jpg` : `/storage/catalog-artworks/${e.id}.jpg`"
                      :alt="e.title"
                    />
                  </div>
                  <div class="track-info">
                    <RouterLink :to="`/catalog/${e.id}`" class="track-link">
                      <span class="track-title" :class="{ 'track-title--playing': playingId === e.id }">{{ e.title }}</span>
                    </RouterLink>
                    <span class="track-artist">{{ e.artist }}</span>
                  </div>
                </div>
              </td>
              <td class="col-style">
                <StyleTag v-if="e.style" :name="e.style" />
              </td>
              <td class="col-bpm num"><span class="mono">{{ e.bpm != null ? Math.round(e.bpm) : '—' }}</span></td>
              <td class="col-key num"><span class="mono key-val">{{ e.key || '—' }}</span></td>
              <td class="col-duration num"><span class="mono">{{ e.duration_ms > 0 ? formatDuration(e.duration_ms) : '—' }}</span></td>
              <td class="col-rating num">
                <span v-if="e.rating" class="rating">
                  <span v-for="n in 5" :key="n" class="star" :class="{ 'is-on': n <= e.rating }">★</span>
                </span>
                <span v-else class="muted">—</span>
              </td>
              <td class="col-radar">
                <ScorePill v-if="e.nb_radar_playlists > 0" :score="Math.min(e.nb_radar_playlists * 2, 10)" />
                <span v-else class="muted">—</span>
              </td>
              <td class="col-inlib">
                <LibDot :in-lib="e.in_lib" />
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
import { useRoute, RouterLink } from 'vue-router'
import axios from 'axios'
import ScorePill from '../components/ScorePill.vue'
import LibDot from '../components/LibDot.vue'
import StyleTag from '../components/StyleTag.vue'
import { storeToRefs } from 'pinia'
import { useAudioPlayer } from '../stores/audioPlayer'

const PAGE_SIZE = 50

const route = useRoute()
const player = useAudioPlayer()
const { playingId } = storeToRefs(player)
const { toggle: togglePlay } = player

const items    = ref([])
const total    = ref(0)
const nLib     = ref(0)
const loading  = ref(false)
const search   = ref('')
const notInLib = ref(false)
const radarMin2 = ref(false)
const page     = ref(1)
const sortKey  = ref('nb_radar_playlists')
const sortDir  = ref('desc')

// inLib : persistant via sessionStorage + query param
const savedInLib = sessionStorage.getItem('catalog_inlib')
const inLib = ref(route.query.inlib === 'true' || savedInLib === 'true')

function setInLib(val) {
  inLib.value = val
  sessionStorage.setItem('catalog_inlib', String(val))
}

let searchTimer = null

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function buildParams() {
  const params = { skip: (page.value - 1) * PAGE_SIZE, limit: PAGE_SIZE }
  if (inLib.value)    params.in_lib = true
  if (notInLib.value) params.in_lib = false
  if (radarMin2.value) params.min_radar_playlists = 2
  if (search.value)   params.search = search.value
  if (sortKey.value)  params.sort = sortKey.value
  if (sortDir.value)  params.order = sortDir.value
  return params
}

async function fetchPage() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/catalog/', { params: buildParams() })
    items.value = data.items
    total.value = data.total
    if (data.total_in_lib != null) nLib.value = data.total_in_lib
  } finally {
    loading.value = false
  }
}

// Fetch nLib séparément si l'API ne le retourne pas encore
async function fetchNLib() {
  if (nLib.value > 0) return
  try {
    const { data } = await axios.get('/api/catalog/', { params: { in_lib: true, limit: 1 } })
    nLib.value = data.total
  } catch {}
}

function goTo(p) {
  page.value = p
  fetchPage()
}

function toggleInLib() {
  setInLib(!inLib.value)
  if (inLib.value) notInLib.value = false
  page.value = 1
  fetchPage()
}

function toggleNotInLib() {
  notInLib.value = !notInLib.value
  if (notInLib.value) setInLib(false)
  page.value = 1
  fetchPage()
}

function toggleRadarMin2() {
  radarMin2.value = !radarMin2.value
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
  if (!ms || ms <= 0) return '—'
  const s = Math.floor(ms / 1000)
  if (s === 0) return '—'
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

onMounted(() => {
  fetchPage()
  fetchNLib()
})
</script>

<style scoped>
.catalog-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1400px;
  margin: 0 auto;
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
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.chip--on {
  background: var(--pos-soft);
  color: var(--pos-ink);
  border-color: transparent;
}
.chip--on-radar {
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-color: transparent;
}

/* Table */
.table-wrap { overflow-x: auto; }
.track-table {
  width: 100%;
  min-width: 832px;
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
.track-table tbody tr.is-playing td { background: var(--accent-wash); }
.track-table tbody tr.is-playing:hover td { background: var(--accent-soft); }
.track-table tbody tr:last-child td { border-bottom: none; }
.sort-indicator { margin-left: 4px; color: var(--accent-ink); }

/* Column widths — toutes les data cols ont une largeur fixe, titre prend le reste */
.col-play     { width: 38px; padding: 0 8px !important; }
.col-title    { width: auto; min-width: 180px; }
.col-style    { width: 124px; }
.col-bpm      { width: 60px; }
.col-key      { width: 52px; }
.col-duration { width: 62px; }
.col-rating   { width: 80px; }
.col-radar    { width: 132px; }
.col-inlib    { width: 56px; text-align: center; }

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
.play-btn--hidden {
  opacity: 0 !important;
  pointer-events: none;
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

/* Rating */
.rating { display: inline-flex; gap: 1px; }
.star { font-size: 13px; color: var(--line-2); line-height: 1; }
.star.is-on { color: var(--accent); }

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
