<template>
  <div class="catalog-view" :data-mode="mode">
    <header class="page-head">
      <div class="titles">
        <h1>{{ mode === 'radar' ? 'Radar' : 'Catalog' }}</h1>
        <div class="sub" v-if="mode === 'catalog'">
          {{ inLib ? `${total} tracks · in lib` : `${total} tracks · ${nLib} in lib` }}
        </div>
        <div class="sub" v-else>{{ total }} détectées</div>
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
        <div class="viewseg">
          <button :class="{ on: mode === 'catalog' }" @click="switchMode('catalog')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            Catalog
          </button>
          <button :class="{ on: mode === 'radar' }" @click="switchMode('radar')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/></svg>
            Radar
          </button>
        </div>
      </div>
    </header>

    <!-- Sub-bar: fixed height, content changes per mode -->
    <div class="sub-bar">
      <div v-if="mode === 'radar'" class="recency">
        <span class="rlbl">Période</span>
        <div class="seg-rec">
          <button v-for="r in recencyOptions" :key="r.value"
            :class="{ on: recency === r.value }"
            @click="setRecency(r.value)"
          >{{ r.label }}</button>
        </div>
      </div>
    </div>

    <div v-if="loading && !items.length" class="state">Chargement…</div>
    <div v-else-if="!total && !loading" class="state">Aucun résultat</div>
    <template v-else>
      <div class="table-wrap">
        <table class="tt" :class="{ swapping }">
          <thead>
            <tr>
              <th class="c-play"></th>
              <th class="sortable" :class="{ 'is-sorted': sortKey === 'title' }" @click="doSort('title')">
                Track <span v-if="sortKey === 'title'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-style sortable" :class="{ 'is-sorted': sortKey === 'style' }" @click="doSort('style')">
                Style <span v-if="sortKey === 'style'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num sortable col-bpm" :class="{ 'is-sorted': sortKey === 'bpm' }" @click="doSort('bpm')">
                BPM <span v-if="sortKey === 'bpm'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num sortable col-key" :class="{ 'is-sorted': sortKey === 'key' }" @click="doSort('key')">
                Key <span v-if="sortKey === 'key'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <!-- Zone d'échange: radar-only -->
              <th class="col-source sortable" :class="{ 'is-sorted': sortKey === 'source_name' }" @click="doSort('source_name')">
                Source <span v-if="sortKey === 'source_name'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-detect sortable" :class="{ 'is-sorted': sortKey === 'detected_at' }" @click="doSort('detected_at')">
                Détecté <span v-if="sortKey === 'detected_at'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <!-- Zone d'échange: catalog-only -->
              <th class="num sortable col-dur" :class="{ 'is-sorted': sortKey === 'duration_ms' }" @click="doSort('duration_ms')">
                Durée <span v-if="sortKey === 'duration_ms'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-rating sortable" :class="{ 'is-sorted': sortKey === 'rating' }" @click="doSort('rating')">
                Rating <span v-if="sortKey === 'rating'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="num col-lib sortable" :class="{ 'is-sorted': sortKey === 'in_lib' }" @click="doSort('in_lib')">
                In&nbsp;lib <span v-if="sortKey === 'in_lib'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <!-- Colonnes communes suite -->
              <th class="col-radar sortable" :class="{ 'is-sorted': sortKey === 'nb_radar_playlists' }" @click="doSort('nb_radar_playlists')">
                Radar <span v-if="sortKey === 'nb_radar_playlists'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="end col-avis sortable" :class="{ 'is-sorted': sortKey === 'avis' }" @click="doSort('avis')">
                Avis <span v-if="sortKey === 'avis'" class="arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in items" :key="e.id" :class="{ playing: player.isCurrent(e.id), liked: e.avis === 'liked', disliked: e.avis === 'disliked' }">
              <td class="c-play">
                <span
                  class="pbtn"
                  :class="{
                    'pbtn--disabled': !e.has_preview,
                    'pbtn--playing': player.isCurrent(e.id),
                  }"
                  @click="e.has_preview && player.play({ id: e.id, catalog_id: e.id, title: e.title, artist: e.artist, bpm: e.bpm, key: e.key })"
                >
                  <svg v-if="!(player.isCurrent(e.id) && player.playing)" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
                  <svg v-else viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5" width="3.4" height="14" rx="1"/><rect x="13.6" y="5" width="3.4" height="14" rx="1"/></svg>
                </span>
              </td>
              <td>
                <div class="td-track">
                  <span class="aw">
                    <img v-if="e.has_artwork" :src="`/storage/catalog-artworks/${e.id}.jpg`" :alt="e.title" />
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
                <span v-else class="td-empty">—</span>
              </td>
              <td class="num col-bpm"><span :class="e.bpm != null ? 'td-bpm' : 'td-empty'">{{ e.bpm != null ? Math.round(e.bpm) : '—' }}</span></td>
              <td class="num col-key"><span :class="e.key ? 'td-key' : 'td-empty'">{{ e.key || '—' }}</span></td>
              <!-- Zone d'échange: radar-only -->
              <td class="col-source">
                <span v-if="e.source_name" class="src" :title="e.source_name">
                  <span class="src-badge" :class="e.source_kind">{{ e.source_kind?.toUpperCase() }}</span>
                  <span class="nm">{{ e.source_name }}</span>
                </span>
                <span v-else class="td-empty">—</span>
              </td>
              <td class="col-detect">
                <span class="detect">{{ fmtRelative(e.detected_at) }}</span>
              </td>
              <!-- Zone d'échange: catalog-only -->
              <td class="num col-dur"><span class="td-dur">{{ e.duration_ms > 0 ? fmtMs(e.duration_ms) : '—' }}</span></td>
              <td class="col-rating">
                <span v-if="e.rating" class="rating">
                  <svg v-for="n in 5" :key="n" :class="{ off: n > e.rating }" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3.2l2.6 5.5 6 .7-4.4 4.1 1.2 5.9L12 16.9 6.6 19.4l1.2-5.9L3.4 9.4l6-.7z"/></svg>
                </span>
                <span v-else class="td-empty">—</span>
              </td>
              <td class="num col-lib">
                <LibDot :in-lib="e.in_lib" />
              </td>
              <!-- Colonnes communes suite -->
              <td class="col-radar">
                <ScorePill v-if="e.nb_radar_playlists > 0" :score="Math.min(e.nb_radar_playlists * 2, 10)" />
                <span v-else class="td-empty">—</span>
              </td>
              <td class="end c-avis col-avis">
                <LikeDislike :model-value="e.avis" @update:model-value="v => setAvis(e, v)" />
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import axios from 'axios'
import ScorePill from '../components/ScorePill.vue'
import LibDot from '../components/LibDot.vue'
import LikeDislike from '../components/LikeDislike.vue'
import StyleTag from '../components/StyleTag.vue'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs } from '../utils/format'

const PAGE_SIZE = 50

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()

const items     = ref([])
const total     = ref(0)
const nLib      = ref(0)
const loading   = ref(false)
const search    = ref('')
const notInLib  = ref(false)
const radarMin2 = ref(false)
const page      = ref(1)
const swapping  = ref(false)

// Mode: catalog or radar
const mode = ref(route.query.view === 'radar' ? 'radar' : 'catalog')

// Sort defaults per mode
const sortKey = ref(mode.value === 'radar' ? 'detected_at' : 'nb_radar_playlists')
const sortDir = ref('desc')

// Recency filter (radar mode)
const recency = ref(null)
const recencyOptions = [
  { value: '7d', label: '7j' },
  { value: '30d', label: '30j' },
  { value: null, label: 'Tout' },
]

// inLib: persistent via sessionStorage
const savedInLib = sessionStorage.getItem('catalog_inlib')
const inLib = ref(route.query.inlib === 'true' || savedInLib === 'true')

function setInLib(val) {
  inLib.value = val
  sessionStorage.setItem('catalog_inlib', String(val))
}

let searchTimer = null
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function fmtRelative(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `il y a ${Math.max(1, mins)} min`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `il y a ${hours} h`
  const days = Math.floor(hours / 24)
  if (days < 30) return `il y a ${days} j`
  const months = Math.floor(days / 30)
  return `il y a ${months} mois`
}

function buildParams() {
  const params = {
    skip: (page.value - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  }
  if (mode.value === 'radar') params.view = 'radar'
  if (inLib.value) params.in_lib = true
  if (notInLib.value) params.in_lib = false
  if (radarMin2.value) params.min_radar_playlists = 2
  if (search.value) params.search = search.value
  if (sortKey.value) params.sort = sortKey.value
  if (sortDir.value) params.order = sortDir.value
  if (mode.value === 'radar' && recency.value) {
    const hours = recency.value === '7d' ? 168 : recency.value === '30d' ? 720 : 0
    if (hours) {
      const since = new Date(Date.now() - hours * 3600000)
      params.detected_after = since.toISOString()
    }
  }
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

function doSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
  page.value = 1
  fetchPage()
}

function switchMode(newMode) {
  if (mode.value === newMode) return
  swapping.value = true
  setTimeout(() => {
    mode.value = newMode
    sortKey.value = newMode === 'radar' ? 'detected_at' : 'nb_radar_playlists'
    sortDir.value = 'desc'
    page.value = 1
    router.replace({ query: newMode === 'radar' ? { view: 'radar' } : {} })
    fetchPage()
    swapping.value = false
  }, 150)
}

function setRecency(val) {
  recency.value = val
  page.value = 1
  fetchPage()
}

async function setAvis(entry, avis) {
  const prev = entry.avis
  entry.avis = avis
  try {
    await axios.patch(`/api/catalog/${entry.id}/avis`, { avis })
  } catch {
    entry.avis = prev
  }
}

onMounted(() => {
  fetchPage()
  fetchNLib()
})

// React to route query changes (e.g. sidebar click)
watch(() => route.query.view, (v) => {
  const newMode = v === 'radar' ? 'radar' : 'catalog'
  if (newMode !== mode.value) switchMode(newMode)
})
</script>

<style scoped>
/* ============ PAGE ============ */
.catalog-view {
  min-width: 0;
  display: flex;
  flex-direction: column;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
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
.sub b { color: var(--pos-ink); font-weight: 600; }
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  justify-content: flex-end;
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
.search svg { width: 16px; height: 16px; color: var(--ink-3); flex: none; }
.search input {
  border: 0; background: transparent; outline: none;
  width: 100%; font: 400 14px var(--font-ui); color: var(--ink);
}
.search input::placeholder { color: var(--ink-3); }

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
.chip:hover { border-color: var(--ink-3); color: var(--ink); }
.chip.on { background: var(--accent-soft); border-color: transparent; color: var(--accent-ink); }
.sw {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--ink-3); box-shadow: 0 0 0 3px var(--surface-2);
}
.chip.on .sw { background: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft-2); }

/* ============ VIEW SEGMENT ============ */
.viewseg {
  display: flex;
  gap: 3px;
  background: var(--surface-2);
  border: 1px solid var(--line);
  padding: 3px;
  border-radius: 999px;
}
.viewseg button {
  border: 0; background: transparent; cursor: pointer;
  display: inline-flex; align-items: center; gap: 7px;
  font: 600 12.5px var(--font-ui); color: var(--ink-2);
  padding: 7px 14px; border-radius: 999px; line-height: 1;
}
.viewseg button svg { width: 15px; height: 15px; }
.viewseg button:hover { color: var(--ink); }
.viewseg button.on {
  background: var(--surface); color: var(--accent-ink);
  box-shadow: var(--shadow-sm);
}

/* ============ SUB-BAR ============ */
.sub-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 46px;
  padding: 0 30px 14px;
}
/* ============ RECENCY (radar only) ============ */
.recency {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}
.rlbl {
  font: 600 10px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.seg-rec {
  display: flex;
  gap: 2px;
  background: var(--surface-2);
  padding: 3px;
  border-radius: var(--r-sm);
}
.seg-rec button {
  border: 0; background: transparent; color: var(--ink-2);
  font: 500 12px/1 var(--font-mono); padding: 7px 11px;
  border-radius: var(--r-xs); cursor: pointer;
}
.seg-rec button:hover { color: var(--ink); }
.seg-rec button.on {
  background: var(--surface); color: var(--accent-ink);
  box-shadow: var(--shadow-sm);
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
  min-width: 1060px;
  transition: opacity .16s ease;
}
table.tt.swapping { opacity: .25; }

/* Column widths on <th> (table-layout: fixed) */
table.tt th.c-play    { width: 44px; }
table.tt th.col-style { width: 158px; }
table.tt th.col-bpm   { width: 72px; }
table.tt th.col-key   { width: 64px; }
/* Zone d'échange — radar-only (300px total) */
table.tt th.col-source { width: 196px; }
table.tt th.col-detect { width: 104px; }
/* Zone d'échange — catalog-only (300px total) */
table.tt th.col-dur    { width: 86px; }
table.tt th.col-rating { width: 110px; }
table.tt th.col-lib    { width: 104px; }
/* Colonnes communes suite */
table.tt th.col-radar  { width: 128px; }
table.tt th.col-avis   { width: 92px; }

table.tt thead th {
  position: sticky; top: 0;
  background: var(--surface); z-index: 2;
  font: 600 10.5px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 14px 12px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.num, table.tt td.num { text-align: center; }
table.tt th.end, table.tt td.end { text-align: right; }
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

/* ============ COLUMN TOGGLE ============ */
/* Radar-only columns: hidden by default */
.col-source, .col-detect { display: none; }
.catalog-view[data-mode="radar"] .col-source,
.catalog-view[data-mode="radar"] .col-detect { display: table-cell; }
/* Catalog-only columns: hidden in radar */
.catalog-view[data-mode="radar"] .col-dur,
.catalog-view[data-mode="radar"] .col-rating,
.catalog-view[data-mode="radar"] .col-lib { display: none; }

/* ============ PLAY BTN ============ */
.c-play { width: 44px; padding: 0 14px; }
.pbtn {
  width: 30px; height: 30px;
  border-radius: 50%;
  display: grid; place-items: center;
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

/* ============ TRACK CELL ============ */
.td-track {
  display: flex; align-items: center; gap: 12px; min-width: 0;
}
.aw {
  width: 38px; height: 38px; border-radius: var(--r-xs); flex: none;
  background: var(--surface-3);
  background-image: repeating-linear-gradient(135deg, transparent 0 5px, oklch(0.50 0.01 70 / .05) 5px 6px);
  overflow: hidden;
}
.aw img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tx { min-width: 0; flex: 1; }
.tt-title-link { text-decoration: none; color: inherit; display: block; min-width: 0; }
.tt-title {
  font-size: 14.5px; font-weight: 500; color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: color .1s;
}
.tt-title-link:hover .tt-title { color: var(--accent-ink); }
tr.playing .tt-title { color: var(--accent-ink); }
.tt-art {
  font-size: 12.5px; color: var(--ink-3);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ============ DATA CELLS ============ */
.td-bpm { font: 500 13px var(--font-mono); color: var(--ink-2); }
.td-key { font: 500 13px var(--font-mono); color: var(--accent-ink); }
.td-dur { font: 500 13px var(--font-mono); color: var(--ink-2); }
.td-empty { font: 500 13px var(--font-mono); color: var(--ink-3); }

/* ============ RATING ============ */
.rating { display: inline-flex; gap: 2px; color: var(--accent); }
.rating svg { width: 14px; height: 14px; }
.rating .off { color: var(--line-2); }

/* ============ SOURCE (radar mode) ============ */
.src {
  display: inline-flex; align-items: center; gap: 9px;
  max-width: 100%; min-width: 0;
}
.src .src-badge {
  display: inline-flex; align-items: center;
  padding: 3px 7px; border-radius: 4px;
  font: 600 10px/1 var(--font-mono);
  letter-spacing: 0.06em; white-space: nowrap; flex: none;
}
.src .src-badge.deezer  { background: var(--accent-soft); color: var(--accent-ink); }
.src .src-badge.spotify { background: var(--pos-soft); color: var(--pos-ink); }
.src .src-badge.tidal   { background: var(--surface-3); color: var(--ink-2); border: 1px solid var(--line-2); }
.src .nm {
  font: 500 13px var(--font-ui); color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ============ DÉTECTÉ ============ */
.detect { font: 500 12.5px var(--font-mono); color: var(--ink-2); white-space: nowrap; }

/* ============ AVIS (LikeDislike) ============ */
.c-avis { padding: 0 14px; }
.c-avis :deep(.ld-btn) { opacity: 0; }
tr:hover .c-avis :deep(.ld-btn) { opacity: 1; }
.c-avis :deep(.ld[data-state="liked"] .ld-btn.like),
.c-avis :deep(.ld[data-state="disliked"] .ld-btn.dislike) { opacity: 1; }

/* ============ ROW AVIS STATES ============ */
table.tt tbody tr.liked { background: oklch(var(--pos-l) var(--pos-c) var(--pos-h) / .06); }
table.tt tbody tr.liked:hover { background: oklch(var(--pos-l) var(--pos-c) var(--pos-h) / .10); }
table.tt tbody tr.disliked td:not(.c-avis) { opacity: .42; }
table.tt tbody tr.disliked:hover td:not(.c-avis) { opacity: .7; }
[data-theme="dark"] table.tt tbody tr.liked { background: oklch(var(--pos-l) var(--pos-c) var(--pos-h) / .10); }

/* ============ PAGINATION ============ */
.pagination {
  display: flex; align-items: center; justify-content: center;
  gap: 12px; padding: 0 30px 30px;
}
.page-btn {
  padding: 6px 14px; border-radius: var(--r-sm);
  border: 1px solid var(--line-2); background: var(--surface);
  color: var(--ink-2); font: 500 13px/1 var(--font-ui);
  cursor: pointer; transition: background 0.12s;
}
.page-btn:hover:not(:disabled) { background: var(--surface-2); }
.page-btn:disabled { opacity: 0.35; cursor: default; }
.page-info {
  font: 400 12px/1 var(--font-mono); color: var(--ink-3);
  min-width: 60px; text-align: center;
}

/* ============ STATES ============ */
.state {
  font: 400 14px var(--font-mono);
  color: var(--ink-3);
  text-align: center;
  padding: 60px 0;
}

/* ============ RESPONSIVE ============ */
@container (max-width: 880px) {
  .page-head { flex-wrap: wrap; }
  .head-tools { width: 100%; margin-left: 0; justify-content: flex-start; }
  .search { flex: 1; min-width: 0; }
}
@container (max-width: 600px) {
  .page-head { padding-left: 18px; padding-right: 18px; }
  .table-wrap { padding-left: 18px; padding-right: 18px; }
  .sub-bar { padding-left: 18px; padding-right: 18px; }
  .pagination { padding: 0 18px 22px; }
}
</style>
