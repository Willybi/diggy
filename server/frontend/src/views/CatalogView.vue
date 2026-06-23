<template>
  <div class="catalog-view">
    <header class="page-head">
      <div class="titles">
        <h1>Catalog</h1>
        <div class="sub">
          {{ inLib ? `${total} tracks · in lib` : `${total} tracks · ${nLib} in lib` }}
        </div>
      </div>
      <div class="head-tools">
        <label class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2" stroke-linecap="round"/></svg>
          <input v-model="search" type="text" placeholder="Artiste ou titre…" @input="onSearch" />
        </label>
        <button class="chip" :class="{ on: notInLib }" @click="toggleNotInLib">
          <span class="sw"></span>Pas dans RB
        </button>
        <button class="chip" :class="{ on: radarMin2 }" @click="toggleRadarMin2">
          <span class="sw"></span>Radar ≥ 2
        </button>
        <button class="chip" :class="{ on: inLib }" @click="toggleInLib">
          <span class="sw"></span>In lib
        </button>
      </div>
    </header>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!total && !loading" class="state">Aucun résultat</div>
    <template v-else>
      <div class="table-wrap">
        <table class="tt">
          <colgroup>
            <col class="w-play">
            <col class="w-track">
            <col class="w-style col-style">
            <col class="w-bpm">
            <col class="w-key">
            <col class="w-dur col-dur">
            <col class="w-rating col-rating">
            <col class="w-radar col-radar">
            <col class="w-lib">
          </colgroup>
          <thead>
            <tr>
              <th class="c-play"></th>
              <th class="sortable" :class="{ 'is-sorted': sortKey === 'title' }" @click="sort('title')">
                Track <span v-if="sortKey === 'title'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-style sortable" :class="{ 'is-sorted': sortKey === 'style' }" @click="sort('style')">
                Style <span v-if="sortKey === 'style'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num sortable" :class="{ 'is-sorted': sortKey === 'bpm' }" @click="sort('bpm')">
                BPM <span v-if="sortKey === 'bpm'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num sortable" :class="{ 'is-sorted': sortKey === 'key' }" @click="sort('key')">
                Key <span v-if="sortKey === 'key'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num sortable col-dur" :class="{ 'is-sorted': sortKey === 'duration_ms' }" @click="sort('duration_ms')">
                Durée <span v-if="sortKey === 'duration_ms'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-rating sortable" :class="{ 'is-sorted': sortKey === 'rating' }" @click="sort('rating')">
                Rating <span v-if="sortKey === 'rating'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-radar sortable" :class="{ 'is-sorted': sortKey === 'nb_radar_playlists' }" @click="sort('nb_radar_playlists')">
                Radar <span v-if="sortKey === 'nb_radar_playlists'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="end">In&nbsp;lib</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in items" :key="e.id" :class="{ playing: player.isCurrent(e.id) }">
              <td class="c-play">
                <span
                  class="pbtn"
                  :class="{
                    'pbtn--disabled': !e.has_preview || (inLib && !e.in_lib),
                    'pbtn--playing': player.isCurrent(e.id),
                    'pbtn--hidden': inLib && !e.in_lib,
                  }"
                  @click="e.has_preview && !(inLib && !e.in_lib) && player.play({ id: e.id, catalog_id: e.id, title: e.title, artist: e.artist, bpm: e.bpm, key: e.key })"
                >
                  <svg v-if="!(player.isCurrent(e.id) && player.playing)" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
                  <svg v-else viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5" width="3.4" height="14" rx="1"/><rect x="13.6" y="5" width="3.4" height="14" rx="1"/></svg>
                </span>
              </td>
              <td>
                <div class="td-track">
                  <span class="aw">
                    <img v-if="e.has_artwork"
                      :src="e.lib_track_id ? `/storage/artworks/${e.lib_track_id}.jpg` : `/storage/catalog-artworks/${e.id}.jpg`"
                      :alt="e.title"
                    />
                  </span>
                  <span class="tx">
                    <RouterLink :to="`/catalog/${e.id}`" class="tt-title-link">
                      <div class="tt-title">{{ e.title }}</div>
                    </RouterLink>
                    <div class="tt-art">{{ e.artist }}</div>
                  </span>
                </div>
              </td>
              <td class="col-style">
                <RouterLink v-if="e.genre" :to="`/style/${encodeURIComponent(e.genre)}`" style="text-decoration:none">
                  <StyleTag :name="e.genre" />
                </RouterLink>
                <StyleTag v-else-if="e.style" :name="e.style" />
              </td>
              <td class="num"><span :class="e.bpm != null ? 'td-bpm' : 'td-empty'">{{ e.bpm != null ? Math.round(e.bpm) : '—' }}</span></td>
              <td class="num"><span class="td-key">{{ e.key || '—' }}</span></td>
              <td class="num col-dur"><span class="td-dur">{{ e.duration_ms > 0 ? fmtMs(e.duration_ms) : '—' }}</span></td>
              <td class="col-rating">
                <span v-if="e.rating" class="rating">
                  <svg v-for="n in 5" :key="n" :class="{ off: n > e.rating }" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3.2l2.6 5.5 6 .7-4.4 4.1 1.2 5.9L12 16.9 6.6 19.4l1.2-5.9L3.4 9.4l6-.7z"/></svg>
                </span>
                <span v-else class="td-empty">—</span>
              </td>
              <td class="col-radar">
                <ScorePill v-if="e.nb_radar_playlists > 0" :score="Math.min(e.nb_radar_playlists * 2, 10)" />
                <span v-else class="td-empty">—</span>
              </td>
              <td class="end">
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
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs } from '../utils/format'

const PAGE_SIZE = 50

const route = useRoute()
const player = useAudioPlayer()

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
  }, 250)
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

onMounted(() => {
  fetchPage()
  fetchNLib()
})
</script>

<style scoped>
/* ============ PAGE ============ */
.catalog-view {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* ============ PAGE HEAD ============ */
.page-head {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 26px 30px 18px;
  flex-wrap: wrap;
}
.titles h1 {
  margin: 0;
  font: 600 28px/1 var(--font-ui);
  letter-spacing: -.3px;
  color: var(--ink);
}
.sub {
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

/* ============ SEARCH ============ */
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 0 12px;
  height: 38px;
  min-width: 230px;
}
.search svg {
  width: 16px;
  height: 16px;
  color: var(--ink-3);
  flex: none;
}
.search input {
  border: 0;
  background: transparent;
  outline: none;
  width: 100%;
  font: 400 14px var(--font-ui);
  color: var(--ink);
}
.search input::placeholder {
  color: var(--ink-3);
}

/* ============ CHIPS ============ */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 38px;
  padding: 0 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.chip:hover {
  border-color: var(--ink-3);
  color: var(--ink);
}
.chip.on {
  background: var(--accent-soft);
  border-color: transparent;
  color: var(--accent-ink);
}
.sw {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ink-3);
  box-shadow: 0 0 0 3px var(--surface-2);
}
.chip.on .sw {
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft-2);
}

/* ============ TABLE ============ */
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
table.tt col.w-play   { width: 44px; }
table.tt col.w-track  { width: auto; }
table.tt col.w-style  { width: 168px; }
table.tt col.w-bpm    { width: 74px; }
table.tt col.w-key    { width: 66px; }
table.tt col.w-dur    { width: 84px; }
table.tt col.w-rating { width: 104px; }
table.tt col.w-radar  { width: 132px; }
table.tt col.w-lib    { width: 70px; }

table.tt thead th {
  position: sticky;
  top: 0;
  font: 600 10.5px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 14px 11px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.num,
table.tt td.num { text-align: center; }
table.tt th.end,
table.tt td.end { text-align: right; }
table.tt th.sortable { cursor: pointer; }
table.tt th.sortable:hover { color: var(--ink-2); }
table.tt th.is-sorted { color: var(--accent-ink); }
.arr { color: var(--accent-ink); margin-left: 4px; }

table.tt tbody tr {
  border-bottom: 1px solid var(--line);
  height: var(--row-h);
}
table.tt tbody tr:hover { background: var(--surface-2); }
table.tt tbody tr.playing { background: var(--accent-wash); }
table.tt tbody tr.playing:hover { background: var(--accent-soft); }
table.tt td {
  padding: 0 14px;
  vertical-align: middle;
}

/* ============ PLAY BTN ============ */
.c-play { width: 44px; }
.pbtn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  opacity: 0;
  transition: opacity .12s;
}
tr:hover .pbtn { opacity: 1; }
.pbtn svg { width: 13px; height: 13px; }
.pbtn--playing {
  opacity: 1 !important;
  background: var(--accent-soft);
  border-color: transparent;
  color: var(--accent-ink);
}
.pbtn--disabled {
  opacity: 0.2 !important;
  cursor: default;
  color: var(--ink-3);
}
.pbtn--hidden {
  opacity: 0 !important;
  pointer-events: none;
}

/* ============ TRACK CELL ============ */
.td-track {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.aw {
  width: 38px;
  height: 38px;
  border-radius: var(--r-xs);
  flex: none;
  background: var(--surface-3);
  background-image: repeating-linear-gradient(135deg, transparent 0 5px, oklch(0.50 0.01 70 / .05) 5px 6px);
  overflow: hidden;
}
.aw img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.tx {
  min-width: 0;
  flex: 1;
}
.tt-title-link {
  text-decoration: none;
  color: inherit;
  display: block;
  min-width: 0;
}
.tt-title {
  font-size: 14.5px;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color .1s;
}
.tt-title-link:hover .tt-title { color: var(--accent-ink); }
tr.playing .tt-title { color: var(--accent-ink); }
.tt-art {
  font-size: 12.5px;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============ DATA CELLS ============ */
.td-bpm { font: 500 13px var(--font-mono); color: var(--ink-2); }
.td-key { font: 500 13px var(--font-mono); color: var(--accent-ink); }
.td-dur { font: 500 13px var(--font-mono); color: var(--ink-2); }
.td-empty { font: 500 13px var(--font-mono); color: var(--ink-3); }

/* ============ RATING ============ */
.rating {
  display: inline-flex;
  gap: 2px;
  color: var(--accent);
}
.rating svg { width: 14px; height: 14px; }
.rating .off { color: var(--line-2); }

/* ============ PAGINATION ============ */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 0 30px 30px;
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

/* ============ STATES ============ */
.state {
  font: 400 14px var(--font-mono);
  color: var(--ink-3);
  text-align: center;
  padding: 60px 0;
}

/* ============ RESPONSIVE (container queries sur .app-container) ============ */
@container (max-width: 1160px) {
  .col-dur { display: none; }
}
@container (max-width: 1010px) {
  .col-rating { display: none; }
}
@container (max-width: 760px) {
  .col-radar { display: none; }
  .head-tools { width: 100%; margin-left: 0; }
  .search { flex: 1; min-width: 0; }
}
@container (max-width: 620px) {
  .col-style { display: none; }
  .page-head { padding: 20px 18px 14px; }
  .table-wrap { padding: 4px 14px 22px; }
  .pagination { padding: 0 14px 22px; }
}
</style>
