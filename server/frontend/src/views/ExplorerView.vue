<template>
  <div ref="pageEl" class="xp-page">
    <!-- ── Head : identity + counter + imports menu (E6/E7) ── -->
    <header class="page-head xp-head">
      <div class="xp-titles">
        <h1>Explorer</h1>
        <div class="xp-sub">{{ headCount }}</div>
      </div>
      <div ref="menuEl" class="xp-plus-wrap">
        <button
          class="btn xp-plus"
          type="button"
          aria-label="Imports"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          @click="toggleMenu"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
        <div v-if="menuOpen" class="xp-menu" role="menu">
          <button class="xp-menu-item" type="button" role="menuitem" @click="openExternalImport">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              aria-hidden="true"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            Ajouter un track
          </button>
          <button class="xp-menu-item" type="button" role="menuitem" @click="openXmlImport">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M12 3v12M7 10l5 5 5-5" />
              <path d="M4 19h16" />
            </svg>
            Importer XML Rekordbox
          </button>
        </div>
      </div>
    </header>

    <!-- ── Filter bar + chips + inline panel (E1/E2/E3) ── -->
    <div class="xp-controls">
      <FilterBar
        v-model:panelOpen="panelOpen"
        v-model:drawerOpen="drawerOpen"
        :criteria="criteria"
        :filters="state"
        :result-count="total"
        :loading="loading"
        @update:filters="applyFilters"
      >
        <template #search>
          <SearchInput v-model="state.q" placeholder="Artiste, titre ou label…" :debounce="0" />
        </template>
        <template #sort>
          <span class="xp-sort">
            <SortSelect
              :model-value="sortValue"
              :options="SORT_OPTIONS"
              aria-label="Trier les résultats"
              @update:model-value="onSortSelect"
            />
          </span>
        </template>
        <template #panel>
          <FilterPanel
            :result-count="total"
            :loading="loading"
            @reset="resetFilters"
            @close="closePanel"
          >
            <div class="flt-field">
              <span class="flt-label">BPM</span>
              <RangeSlider v-model="state.bpm" :min="BPM_MIN" :max="BPM_MAX" label="BPM" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Année</span>
              <RangeSlider v-model="state.year" :min="YEAR_MIN" :max="YEAR_MAX" label="Année" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Durée</span>
              <SegmentedFilter v-model="state.dur" :options="DUR_OPTIONS" mono />
            </div>
            <div class="flt-field flt-field--4">
              <span class="flt-label">Key</span>
              <CamelotSelect v-model="state.key" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Bibliothèque</span>
              <SegmentedFilter v-model="state.lib" :options="LIB_OPTIONS" />
            </div>
            <div class="flt-field flt-field--4">
              <span class="flt-label">Styles</span>
              <div class="xp-styles-scroll">
                <StyleMultiSelect v-model="state.genre" :options="genreOptions" />
              </div>
            </div>
            <div class="flt-field">
              <span class="flt-label">Artiste</span>
              <ArtistTypeAhead :model-value="state.artist_id" @update:model-value="setArtists" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Label</span>
              <SearchInput
                v-model="state.label"
                :icon="false"
                placeholder="Defected, Drumcode…"
                :debounce="0"
              />
            </div>
            <div class="flt-field">
              <span class="flt-label">Avis</span>
              <SegmentedFilter v-model="state.avis" :options="AVIS_OPTIONS" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Extrait audio</span>
              <ToggleChip v-model="state.preview" label="Écoutable uniquement" />
            </div>
          </FilterPanel>
        </template>
      </FilterBar>
    </div>

    <!-- ── Table : shared virtualised, sortable track table (A4-01) ── -->
    <TrackTable
      ref="trackTableRef"
      variant="explorer"
      :window-items="windowItems"
      :items="items"
      :pad-top="padTop"
      :pad-bottom="padBottom"
      :has-more="hasMore"
      :initial-loading="initialLoading"
      :is-error="isError"
      :is-empty="isEmpty"
      :active-chips="activeChips"
      :sort="state.sort"
      :arrow="arrow"
      track-sortable
      key-sortable
      show-duration
      :is-current="player.isCurrent"
      :playing="player.playing"
      @header-sort="onHeaderSort"
      @row-click="openTrack"
      @play="playTrack"
      @avis="setAvis"
      @retry="fetchPage(true)"
      @reset="resetFilters"
      @remove-chip="removeChip"
    />

    <!-- ── Mobile filter drawer (< 640) ── -->
    <FilterDrawer
      v-model:open="drawerOpen"
      :result-count="total"
      :loading="loading"
      @reset="resetFilters"
    >
      <div class="flt-field">
        <span class="flt-label">BPM</span>
        <RangeSlider v-model="state.bpm" :min="BPM_MIN" :max="BPM_MAX" label="BPM" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Année</span>
        <RangeSlider v-model="state.year" :min="YEAR_MIN" :max="YEAR_MAX" label="Année" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Durée</span>
        <SegmentedFilter v-model="state.dur" :options="DUR_OPTIONS" mono variant="drawer" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Key</span>
        <CamelotSelect v-model="state.key" variant="drawer" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Bibliothèque</span>
        <SegmentedFilter v-model="state.lib" :options="LIB_OPTIONS" variant="drawer" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Styles</span>
        <div class="xp-styles-scroll">
          <StyleMultiSelect v-model="state.genre" :options="genreOptions" variant="drawer" />
        </div>
      </div>
      <div class="flt-field">
        <span class="flt-label">Artiste</span>
        <ArtistTypeAhead
          :model-value="state.artist_id"
          variant="drawer"
          @update:model-value="setArtists"
        />
      </div>
      <div class="flt-field">
        <span class="flt-label">Label</span>
        <SearchInput
          v-model="state.label"
          :icon="false"
          placeholder="Defected, Drumcode…"
          variant="drawer"
          :debounce="0"
        />
      </div>
      <div class="flt-field">
        <span class="flt-label">Avis</span>
        <SegmentedFilter v-model="state.avis" :options="AVIS_OPTIONS" variant="drawer" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Extrait audio</span>
        <ToggleChip v-model="state.preview" label="Écoutable uniquement" variant="drawer" />
      </div>
    </FilterDrawer>

    <ImportRekordboxModal
      v-if="showImportModal"
      @close="showImportModal = false"
      @done="onImportDone"
    />

    <ExternalImportModal
      v-if="showExternalImportModal"
      @close="showExternalImportModal = false"
      @imported="onExternalImportDone"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, onActivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { useFilterState } from '../composables/useFilterState.js'
import { useVirtualWindow } from '../composables/useVirtualWindow.js'
import { useWindowedList } from '../composables/useWindowedList.js'
import { useScrollRestore } from '../composables/useScrollRestore.js'
import { buildChips, defaultValue } from '../components/filters/criteria.js'
import { compareCamelot, CAMELOT_KEYS } from '../components/filters/camelot.js'
import FilterBar from '../components/filters/FilterBar.vue'
import FilterPanel from '../components/filters/FilterPanel.vue'
import FilterDrawer from '../components/filters/FilterDrawer.vue'
import SearchInput from '../components/filters/SearchInput.vue'
import RangeSlider from '../components/filters/RangeSlider.vue'
import CamelotSelect from '../components/filters/CamelotSelect.vue'
import StyleMultiSelect from '../components/filters/StyleMultiSelect.vue'
import ArtistTypeAhead from '../components/filters/ArtistTypeAhead.vue'
import SegmentedFilter from '../components/filters/SegmentedFilter.vue'
import ToggleChip from '../components/filters/ToggleChip.vue'
import SortSelect from '../components/filters/SortSelect.vue'
import TrackTable from '../components/TrackTable.vue'
import ImportRekordboxModal from '../components/ImportRekordboxModal.vue'
import ExternalImportModal from '../components/ExternalImportModal.vue'

// Explicit name so <KeepAlive :include> in App.vue matches this cached listing.
defineOptions({ name: 'ExplorerView' })

const PAGE_SIZE = 100
const BPM_MIN = 60
const BPM_MAX = 200
const YEAR_MIN = 1985
const YEAR_MAX = 2026
const GENRE_OPTIONS_MAX = 150

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()

// ── Criteria (contract components/filters/criteria.js) ──────────────────────

const LIB_OPTIONS = [
  { value: null, label: 'Tous' },
  { value: 'in', label: 'Dans ma bib' },
  { value: 'out', label: 'Pas dans RB' },
]
const DUR_OPTIONS = [
  { value: 'lt3', label: '< 3 min' },
  { value: '3-5', label: '3–5 min' },
  { value: '5-8', label: '5–8 min' },
  { value: 'gt8', label: '> 8 min' },
]
const AVIS_OPTIONS = [
  { value: null, label: 'Tous' },
  { value: 'liked', label: 'Aimés' },
  { value: 'disliked', label: 'Rejetés' },
  { value: 'none', label: 'Sans avis' },
]
// Duration presets → API bounds in ms ([min, max], null = unbounded).
const DUR_BOUNDS = {
  lt3: [null, 180000],
  '3-5': [180000, 300000],
  '5-8': [300000, 480000],
  gt8: [480000, null],
}

function toArray(raw) {
  if (raw == null) return []
  return Array.isArray(raw) ? raw : [raw]
}

// Repeated query params (mission contract: key/genre/artist_id are repeated in
// the URL, not comma-joined) — vue-router serializes array values as repeats.
const listSerialize = (v) => (Array.isArray(v) && v.length ? [...v] : undefined)
const listDeserialize = (raw) => toArray(raw).map(String).filter(Boolean)

// Artists: ids in the URL, { id, name } objects in the state. The cache keeps
// deserialization JSON-stable once names are known (typeahead or ?ids= hydration).
const artistCache = new Map()
function artistFromUrl(s) {
  const id = Number(s)
  if (!Number.isInteger(id) || id <= 0) return null
  return artistCache.get(id) || { id, name: `#${id}` }
}

const criteria = [
  { key: 'q', type: 'text', label: 'Recherche', chip: false },
  { key: 'bpm', type: 'range', label: 'BPM', min: BPM_MIN, max: BPM_MAX },
  {
    key: 'key',
    type: 'multi',
    label: 'Key',
    sort: compareCamelot,
    serialize: listSerialize,
    deserialize: (raw) =>
      listDeserialize(raw)
        .map((k) => k.toUpperCase())
        .filter((k) => CAMELOT_KEYS.includes(k)),
  },
  {
    key: 'genre',
    type: 'multi',
    label: 'Style',
    chipPerValue: true,
    serialize: listSerialize,
    deserialize: listDeserialize,
  },
  {
    key: 'artist_id',
    type: 'multi',
    label: 'Artiste',
    chipPerValue: true,
    format: (a) => a.name,
    serialize: (v) => (Array.isArray(v) && v.length ? v.map((a) => String(a.id)) : undefined),
    deserialize: (raw) => toArray(raw).map(artistFromUrl).filter(Boolean),
  },
  { key: 'lib', type: 'segment', label: 'Bibliothèque', options: LIB_OPTIONS },
  { key: 'dur', type: 'segment', label: 'Durée', options: DUR_OPTIONS },
  { key: 'preview', type: 'toggle', label: 'Extrait', valueLabel: 'Écoutable' },
  { key: 'avis', type: 'segment', label: 'Avis', options: AVIS_OPTIONS },
  { key: 'year', type: 'range', label: 'Année', min: YEAR_MIN, max: YEAR_MAX },
  { key: 'label', type: 'text', label: 'Label' },
]

// Sort is URL state but not a filter (never a chip, never counted in the badge).
const SORT_FIELDS = ['title', 'artist', 'bpm', 'key', 'duration_ms', 'release_date']
const urlCriteria = [
  ...criteria,
  {
    key: 'sort',
    type: 'segment',
    label: 'Tri',
    chip: false,
    options: SORT_FIELDS.map((v) => ({ value: v, label: v })),
  },
  {
    key: 'order',
    type: 'segment',
    label: 'Ordre',
    chip: false,
    options: [
      { value: 'asc', label: 'asc' },
      { value: 'desc', label: 'desc' },
    ],
  },
]

const { state } = useFilterState(urlCriteria, { router, route })

// ── Sort (E8) : select + header clicks pilot the same state ─────────────────

const SORT_OPTIONS = [
  { value: 'recent', label: 'Récemment ajoutés' },
  { value: 'title', label: 'Titre A–Z' },
  { value: 'artist', label: 'Artiste A–Z' },
  { value: 'bpm', label: 'BPM' },
  { value: 'key', label: 'Key (harmonique)' },
  { value: 'duration_ms', label: 'Durée' },
  { value: 'release_date', label: 'Date de sortie' },
]
const DEFAULT_ORDER = {
  title: 'asc',
  artist: 'asc',
  bpm: 'asc',
  key: 'asc',
  duration_ms: 'asc',
  release_date: 'desc',
}

const sortValue = computed(() => state.sort || 'recent')
const arrow = computed(() => (state.order === 'asc' ? '↑' : '↓'))

function onSortSelect(v) {
  if (v === 'recent') {
    state.sort = null
    state.order = null
  } else {
    state.sort = v
    state.order = DEFAULT_ORDER[v]
  }
}

function onHeaderSort(field) {
  if (state.sort === field) {
    state.order = state.order === 'asc' ? 'desc' : 'asc'
  } else {
    state.sort = field
    state.order = DEFAULT_ORDER[field]
  }
}

// ── Filter state helpers ─────────────────────────────────────────────────────

const panelOpen = ref(false)
const drawerOpen = ref(false)

const activeChips = computed(() => buildChips(criteria, state))

function applyFilters(next) {
  for (const c of criteria) {
    if (c.key in next) state[c.key] = next[c.key]
  }
}

function setArtists(list) {
  state.artist_id = (list || []).map((a) => {
    const entry = { id: a.id, name: a.name }
    artistCache.set(entry.id, entry)
    return entry
  })
}

function removeChip(chip) {
  const criterion = criteria.find((c) => c.key === chip.key)
  if (!criterion) return
  if (criterion.type === 'multi' && criterion.chipPerValue) {
    state[chip.key] = state[chip.key].filter((v) => v !== chip.rawValue)
  } else {
    state[chip.key] = defaultValue(criterion)
  }
}

function resetFilters() {
  for (const c of criteria) state[c.key] = defaultValue(c)
}

function closePanel() {
  panelOpen.value = false
}

// ── Fetch (windowed table) ──────────────────────────────────────────────────
// useWindowedList is the sibling of usePaginatedList for a virtualised table:
// the delivered GET /api/catalog/ contract paginates with `skip` (not
// `offset`), takes 15 filter params and needs REPEATED list params
// (genre/key/artist_id) — none expressible through usePaginatedList's fixed
// { sort, limit, offset, family?, q? } shape and axios' bracket array
// serialization. buildSearchParams (page-specific) stays here; the composable
// owns the trunk (in-flight token, loading/hasMore, append-vs-replace, reset).

function buildSearchParams(skip) {
  const p = new URLSearchParams()
  p.set('skip', String(skip))
  p.set('limit', String(PAGE_SIZE))
  const q = (state.q || '').trim()
  if (q) p.set('search', q)
  const [bpmLo, bpmHi] = state.bpm
  if (bpmLo > BPM_MIN) p.set('bpm_min', String(bpmLo))
  if (bpmHi < BPM_MAX) p.set('bpm_max', String(bpmHi))
  for (const k of state.key) p.append('key', k)
  for (const g of state.genre) p.append('genre', g)
  for (const a of state.artist_id) p.append('artist_id', String(a.id))
  if (state.lib === 'in') p.set('in_lib', 'true')
  if (state.lib === 'out') p.set('in_lib', 'false')
  const dur = DUR_BOUNDS[state.dur]
  if (dur) {
    if (dur[0] != null) p.set('duration_min', String(dur[0]))
    if (dur[1] != null) p.set('duration_max', String(dur[1]))
  }
  if (state.preview) p.set('has_preview', 'true')
  if (state.avis) p.set('avis', state.avis)
  const [yearLo, yearHi] = state.year
  if (yearLo > YEAR_MIN) p.set('year_min', String(yearLo))
  if (yearHi < YEAR_MAX) p.set('year_max', String(yearHi))
  const label = (state.label || '').trim()
  if (label) p.set('label', label)
  if (state.sort) {
    p.set('sort', state.sort)
    p.set('order', state.order || 'desc')
  }
  return p
}

const {
  items,
  total,
  loading,
  hasMore,
  error,
  fetch: fetchPage,
  loadMore,
  fetchUpTo,
} = useWindowedList({
  endpoint: '/api/catalog/',
  buildParams: buildSearchParams,
  pageSize: PAGE_SIZE,
})

// Filters/sort changed → the URL is the trigger (debounce already handled by
// useFilterState). Dedup on the serialized API params (skip fixed at 0): a
// same-content replace (e.g. reset) must not refetch.
let lastFilterKey = null
function filterKey() {
  return buildSearchParams(0).toString()
}
watch(
  () => route.query,
  () => {
    if (route.path !== '/explorer') return
    if (filterKey() === lastFilterKey) return
    lastFilterKey = filterKey()
    fetchPage(true)
  },
)

const initialLoading = computed(() => loading.value && !items.value.length)
const isError = computed(() => !loading.value && error.value)
// Only a genuine empty result (never a fetch error — that leaves total null).
const isEmpty = computed(() => !loading.value && !error.value && total.value === 0)

// ── Head counters (base total + in-lib total, independent from the filters) ──

const nBase = ref(null)
const nLib = ref(null)

const headCount = computed(() => {
  if (nBase.value == null || nLib.value == null) return '…'
  return `${nBase.value.toLocaleString('fr-FR')} tracks · ${nLib.value.toLocaleString('fr-FR')} dans ma bibliothèque`
})

async function fetchCounts() {
  try {
    const [base, lib] = await Promise.all([
      api.get('/api/catalog/', { params: { limit: 1 } }),
      api.get('/api/catalog/', { params: { in_lib: true, limit: 1 } }),
    ])
    nBase.value = base.data.total
    nLib.value = lib.data.total
  } catch {
    /* the header stays on '…' */
  }
}

// ── Style options (GET /api/catalog/genres, sorted by count desc) ───────────

const genreOptions = ref([])

async function fetchGenres() {
  try {
    const { data } = await api.get('/api/catalog/genres')
    genreOptions.value = (data || []).slice(0, GENRE_OPTIONS_MAX)
  } catch {
    /* panel simply shows no style options */
  }
}

// ── Artist chips hydration from the URL (GET /api/artists/?ids=) ────────────

async function hydrateArtists() {
  const missing = state.artist_id.filter((a) => !artistCache.has(a.id))
  if (!missing.length) return
  try {
    const { data } = await api.get('/api/artists/', {
      params: { ids: missing.map((a) => a.id).join(','), limit: 100 },
    })
    for (const a of data.items || []) artistCache.set(a.id, { id: a.id, name: a.name })
    state.artist_id = state.artist_id.map((a) => artistCache.get(a.id) || a)
  } catch {
    /* chips keep their #id placeholder */
  }
}

// ── Windowing : useWindowedList fetch + useVirtualWindow rendering ──────────
// The app scrolls inside .app-main (overflow-y: auto), not the window: the
// scroll ancestor is resolved after mount and handed to useVirtualWindow via
// `container`, which then owns its own scroll/resize listeners on it.

const pageEl = ref(null)
const trackTableRef = ref(null)
// TrackTable owns the windowed body markup; it exposes that element so this view
// can keep ownership of the windowing (useVirtualWindow needs it as `listRef`,
// paired with the scroll ancestor). A computed forwards the exposed ref.
const listEl = computed(() => trackTableRef.value?.bodyEl || null)
const scrollEl = ref(null)
const rowH = ref(56)

function findScrollParent(el) {
  let node = el?.parentElement
  while (node) {
    const { overflowY } = window.getComputedStyle(node)
    if (overflowY === 'auto' || overflowY === 'scroll') return node
    node = node.parentElement
  }
  return null
}

const { startIndex, endIndex, padTop, padBottom } = useVirtualWindow({
  count: () => items.value.length,
  rowHeight: rowH,
  listRef: listEl,
  container: scrollEl,
  onNearEnd: loadMore,
})

const windowItems = computed(() =>
  endIndex.value < startIndex.value ? [] : items.value.slice(startIndex.value, endIndex.value + 1),
)

// Scroll restoration on a back/forward return: snapshots { top, count } into
// history.state on leave, and on the way back reloads the pages (one parallel
// burst via fetchUpTo) then re-applies the offset. Owns its onBeforeRouteLeave.
const scrollRestore = useScrollRestore({
  scroller: scrollEl,
  getCount: () => items.value.length,
})

// ── Rows ─────────────────────────────────────────────────────────────────────

function openTrack(e) {
  router.push(`/catalog/${e.id}`)
}

function toPlayerTrack(e) {
  return {
    id: e.id,
    catalog_id: e.id,
    title: e.title,
    artist: e.artist,
    artist_id: e.artist_id,
    bpm: e.bpm,
    key: e.key,
    avis: e.avis,
    has_preview: e.has_preview,
  }
}

// Queue source: "next" follows the table as displayed (current filters + sort),
// pulling the next page when the loaded window runs out.
const playSource = {
  type: 'list',
  getItems: () => items.value.map(toPlayerTrack),
  loadMore,
  onAvis: (id, avis) => {
    const row = items.value.find((r) => r.id === id)
    if (row) row.avis = avis
  },
}

function playTrack(e) {
  player.play(toPlayerTrack(e), playSource)
}

async function setAvis(entry, avis) {
  const prev = entry.avis
  entry.avis = avis
  player.syncAvis(entry.id, avis)
  try {
    await api.patch(`/api/catalog/${entry.id}/avis`, { avis })
  } catch {
    entry.avis = prev
    player.syncAvis(entry.id, prev)
  }
}

// ── Imports menu ─────────────────────────────────────────────────────────────

const menuEl = ref(null)
const menuOpen = ref(false)
const showImportModal = ref(false)
const showExternalImportModal = ref(false)

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function openExternalImport() {
  menuOpen.value = false
  showExternalImportModal.value = true
}

function openXmlImport() {
  menuOpen.value = false
  showImportModal.value = true
}

function onDocClick(ev) {
  if (!menuOpen.value) return
  if (menuEl.value && !menuEl.value.contains(ev.target)) menuOpen.value = false
}

function onImportDone() {
  showImportModal.value = false
  fetchPage(true)
  fetchCounts()
}

// Fired on every successful external import; the modal stays open so the user
// can add several tracks in a row. Refresh the listing behind it each time.
function onExternalImportDone() {
  fetchPage(true)
  fetchCounts()
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(() => {
  const px = parseFloat(window.getComputedStyle(pageEl.value).getPropertyValue('--row-h'))
  if (Number.isFinite(px) && px > 0) rowH.value = px
  // Resolving the scroll ancestor here (after the DOM is up) updates the ref;
  // useVirtualWindow watches it and binds its listeners onto it.
  scrollEl.value = findScrollParent(pageEl.value)
  document.addEventListener('click', onDocClick)
  lastFilterKey = filterKey()
  // On a back-return, hydrate the previously loaded rows in one burst and
  // re-apply the scroll offset; otherwise just load page 1.
  scrollRestore.restore({
    initialFetch: () => fetchPage(true),
    hydrate: (count) => fetchUpTo(count),
  })
  fetchCounts()
  fetchGenres()
  hydrateArtists()
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
})

// Cached return under <KeepAlive>: the view is reactivated (no onMounted), the
// rows/filters/window are still in memory, so only the scroll offset needs
// re-applying — no refetch. The first activation follows onMounted (which
// already restored scroll) and is skipped.
let firstActivate = true
onActivated(() => {
  if (firstActivate) {
    firstActivate = false
    return
  }
  scrollRestore.reapply()
})
</script>

<style scoped>
/* ============ PAGE ============ */
.xp-page {
  container-type: inline-size;
  min-width: 0;
  width: 100%;
  max-width: var(--page-max-w);
  margin-inline: auto;
}

/* ============ HEAD ============ */
.xp-titles h1 {
  margin: 0;
  font: 700 var(--fs-lg) / 1 var(--font-ui);
  letter-spacing: -0.3px;
  color: var(--ink);
}
.xp-sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm) / 1 var(--font-mono);
  color: var(--ink-3);
}
.xp-plus-wrap {
  position: relative;
  margin-left: auto;
}
.xp-plus {
  width: 38px;
  padding: 0;
  justify-content: center;
}
.xp-menu {
  position: absolute;
  top: calc(100% + var(--space-1));
  right: 0;
  z-index: 60;
  min-width: 236px;
  padding: var(--space-1);
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
}
.xp-menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  height: 38px;
  padding: 0 var(--space-25);
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
}
.xp-menu-item:hover {
  background: var(--surface-2);
}
.xp-menu-item svg {
  width: 15px;
  height: 15px;
  flex: none;
  color: var(--ink-2);
}
.xp-menu-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

/* ============ CONTROLS ============ */
.xp-controls {
  padding: 0 var(--page-px) var(--space-4);
}

/* Styles field: the full genre list scrolls inside its panel cell. */
.xp-styles-scroll {
  max-height: 180px;
  overflow-y: auto;
}

/* ============ RESPONSIVE — view chrome (table paliers live in TrackTable) ==== */
@container (max-width: 639px) {
  .xp-head {
    padding: var(--space-4) var(--page-px-mobile) var(--space-3);
  }
  .xp-controls {
    padding: 0 var(--page-px-mobile) var(--space-3);
  }
  /* Sort select leaves the bar (v1: default order lives in the drawer later). */
  .xp-sort {
    display: none;
  }
}
</style>
