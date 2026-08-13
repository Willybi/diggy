<template>
  <div ref="pageEl" class="rd-page">
    <!-- ── Head : identity + bi-score counter (no imports menu, reco surface) ── -->
    <header class="page-head rd-head">
      <div class="rd-titles">
        <h1>Radar</h1>
        <div class="rd-sub">{{ headCount }}</div>
      </div>
    </header>

    <!-- ── Filter bar + chips + inline panel (reused from Explorer) ── -->
    <div class="rd-controls">
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
          <SearchInput v-model="state.q" placeholder="Artiste ou titre…" :debounce="0" />
        </template>
        <template #sort>
          <span class="rd-sort">
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
              <div class="rd-styles-scroll">
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

    <!-- ── Cold-start invite : shown while the user has no likes yet (R7) ── -->
    <div v-if="showColdStart" class="rd-cold">
      <span class="rd-cold-ic" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
          />
        </svg>
      </span>
      <span class="rd-cold-tx">
        <span class="rd-cold-title">Débloque Pour toi</span>
        <span class="rd-cold-sub"
          >Like quelques sons pour activer tes recommandations personnalisées. En attendant, tu vois
          le classement Tendance.</span
        >
      </span>
      <button class="rd-cold-x" type="button" aria-label="Fermer" @click="dismissColdStart">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>

    <!-- ── Table : shared virtualised, sortable track table (A4-01). The two
             bi-score columns (Tendance / Pour toi) are injected through the
             head-extra / row-extra slots so ScoreRing, the ▲ velocity marker and
             the active-column band stay in this view's scope. ── -->
    <TrackTable
      ref="trackTableRef"
      variant="radar"
      :window-items="windowItems"
      :items="items"
      :pad-top="padTop"
      :pad-bottom="padBottom"
      :has-more="hasMore"
      :initial-loading="initialLoading"
      :is-error="isError"
      :is-empty="isEmpty"
      :active-chips="activeChips"
      :sort="effectiveSort"
      :arrow="arrow"
      :extra-skeleton="['disc', 'disc']"
      :is-current="player.isCurrent"
      :playing="player.playing"
      @header-sort="onHeaderSort"
      @row-click="openTrack"
      @play="playTrack"
      @avis="setAvis"
      @retry="fetchPage(true)"
      @reset="resetFilters"
      @remove-chip="removeChip"
    >
      <template #head-extra>
        <button
          class="rd-th rd-th--score col-trend"
          :class="{ 'is-sorted': effectiveSort === 'tendance' }"
          type="button"
          @click="onHeaderSort('tendance')"
        >
          Tendance<span v-if="effectiveSort === 'tendance'" class="rd-arr">{{ arrow }}</span>
        </button>
        <button
          class="rd-th rd-th--score col-reco"
          :class="{ 'is-sorted': effectiveSort === 'pour_toi' }"
          type="button"
          @click="onHeaderSort('pour_toi')"
        >
          Pour toi<span v-if="effectiveSort === 'pour_toi'" class="rd-arr">{{ arrow }}</span>
        </button>
      </template>
      <template #row-extra="{ row: e }">
        <span
          class="rd-cell rd-cell--score col-trend"
          :class="{ 'is-active-col': effectiveSort === 'tendance' }"
        >
          <span v-if="e.trend_score_10 != null" class="rd-ring">
            <ScoreRing
              size="sm"
              :score="e.trend_score_10 / 10"
              :label="`Tendance ${Math.round(e.trend_score_10)} sur 10`"
            />
            <span v-if="isRising(e)" class="rd-velo" title="Monte vite" aria-label="Monte vite">
              <svg viewBox="0 0 10 10" aria-hidden="true">
                <path d="M5 0.5 9.5 9.5H0.5z" fill="currentColor" />
              </svg>
            </span>
          </span>
          <span v-else class="rd-dash" role="img" aria-label="Pas de score Tendance">—</span>
        </span>
        <span
          class="rd-cell rd-cell--score col-reco"
          :class="{ 'is-active-col': effectiveSort === 'pour_toi' }"
        >
          <ScoreRing
            v-if="e.reco_score_10 != null"
            size="sm"
            :score="e.reco_score_10 / 10"
            :label="`Pour toi ${Math.round(e.reco_score_10)} sur 10`"
          />
          <span v-else class="rd-dash" role="img" aria-label="Pas de score Pour toi">—</span>
        </span>
      </template>
    </TrackTable>

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
        <div class="rd-styles-scroll">
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
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
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
import ScoreRing from '../components/ScoreRing.vue'

const PAGE_SIZE = 100
const BPM_MIN = 60
const BPM_MAX = 200
const YEAR_MIN = 1985
const YEAR_MAX = 2026
const GENRE_OPTIONS_MAX = 150
// velocity is bounded 0..5 server-side; a value at/above this reads as "rising
// fast" (R5) and stamps a ▲ on the Tendance ring only.
const VELOCITY_HIGH = 1.5

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()

// ── Criteria (contract components/filters/criteria.js) — same set as Explorer ─

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

// Repeated query params (key/genre/artist_id are repeated in the URL, not
// comma-joined) — vue-router serializes array values as repeats.
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

// ── Sort (R6) : select + header clicks pilot the same state ─────────────────
// Radar defaults to `tendance` (global trend ranking) — always available, even
// with no likes. The default is the ABSENT sort param (state.sort === null);
// effectiveSort resolves it to 'tendance' so the column highlight/arrow behave.

const SORT_OPTIONS = [
  { value: 'tendance', label: 'Tendance' },
  { value: 'pour_toi', label: 'Pour toi' },
  { value: 'bpm', label: 'BPM' },
  { value: 'recent', label: 'Récent' },
]
const SORT_FIELDS = SORT_OPTIONS.map((o) => o.value)
const DEFAULT_ORDER = {
  tendance: 'desc',
  pour_toi: 'desc',
  bpm: 'asc',
  recent: 'desc',
}

// Sort is URL state but not a filter (never a chip, never counted in the badge).
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

// `tendance` is the standing default: an absent sort param resolves to it, and
// the score/BPM headers highlight against this resolved value.
const effectiveSort = computed(() => state.sort || 'tendance')
const effectiveOrder = computed(() => state.order || DEFAULT_ORDER[effectiveSort.value] || 'desc')
const sortValue = computed(() => effectiveSort.value)
const arrow = computed(() => (effectiveOrder.value === 'asc' ? '↑' : '↓'))

function onSortSelect(v) {
  if (v === 'tendance') {
    // The default: drop the params so the URL stays clean (back applies tendance).
    state.sort = null
    state.order = null
  } else {
    state.sort = v
    state.order = DEFAULT_ORDER[v]
  }
}

function onHeaderSort(field) {
  if (effectiveSort.value === field) {
    state.sort = field
    state.order = effectiveOrder.value === 'asc' ? 'desc' : 'asc'
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
// GET /api/radar/feed mirrors /api/catalog/ params + the bi-score sort values.
// buildSearchParams (page-specific) stays here; useWindowedList owns the trunk
// (in-flight token, loading/hasMore, append-vs-replace, reset).

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
  // Default (tendance) → no sort param, the back applies its own default.
  if (state.sort) {
    p.set('sort', state.sort)
    p.set('order', state.order || DEFAULT_ORDER[state.sort] || 'desc')
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
  endpoint: '/api/radar/feed',
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
    if (route.path !== '/radar') return
    if (filterKey() === lastFilterKey) return
    lastFilterKey = filterKey()
    fetchPage(true)
  },
)

const initialLoading = computed(() => loading.value && !items.value.length)
const isError = computed(() => !loading.value && error.value)
// Only a genuine empty result (never a fetch error — that leaves total null).
const isEmpty = computed(() => !loading.value && !error.value && total.value === 0)

// ── Head counters (union bounds : trend_count + reco_count from the feed) ────

const trendCount = ref(null)
const recoCount = ref(null)

const headCount = computed(() => {
  if (trendCount.value == null || recoCount.value == null) return '…'
  const t = trendCount.value.toLocaleString('fr-FR')
  if (recoCount.value === 0) return `${t} tendances · Pour toi en attente de tes likes`
  return `${t} tendances · ${recoCount.value.toLocaleString('fr-FR')} pour toi`
})

async function fetchCounts() {
  try {
    const { data } = await api.get('/api/radar/feed', { params: { limit: 1 } })
    trendCount.value = data.trend_count
    recoCount.value = data.reco_count
  } catch {
    /* the header stays on '…' */
  }
}

// ── Cold-start (R7) : no reco at all → Pour toi is all « — » + an invite ─────

const coldStartDismissed = ref(false)
const showColdStart = computed(() => recoCount.value === 0 && !coldStartDismissed.value)

function dismissColdStart() {
  coldStartDismissed.value = true
}

// ── Style options (GET /api/catalog/genres) ─────────────────────────────────

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

function isRising(e) {
  return e.velocity != null && e.velocity >= VELOCITY_HIGH
}

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

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(() => {
  const px = parseFloat(window.getComputedStyle(pageEl.value).getPropertyValue('--row-h'))
  if (Number.isFinite(px) && px > 0) rowH.value = px
  // Resolving the scroll ancestor here (after the DOM is up) updates the ref;
  // useVirtualWindow watches it and binds its listeners onto it.
  scrollEl.value = findScrollParent(pageEl.value)
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
</script>

<style scoped>
/* ============ PAGE ============ */
.rd-page {
  container-type: inline-size;
  min-width: 0;
  width: 100%;
  max-width: var(--page-max-w);
  margin-inline: auto;
}

/* ============ HEAD ============ */
.rd-titles h1 {
  margin: 0;
  font: 700 var(--fs-lg) / 1 var(--font-ui);
  letter-spacing: -0.3px;
  color: var(--ink);
}
.rd-sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm) / 1 var(--font-mono);
  color: var(--ink-3);
}

/* ============ CONTROLS ============ */
.rd-controls {
  padding: 0 var(--page-px) var(--space-4);
}

/* Styles field: the full genre list scrolls inside its panel cell. */
.rd-styles-scroll {
  max-height: 180px;
  overflow-y: auto;
}

/* ============ COLD-START INVITE (R7) ============ */
.rd-cold {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  margin: 0 var(--page-px) var(--space-4);
  padding: var(--space-25) var(--space-3);
  background: var(--accent-wash);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
}
.rd-cold-ic {
  flex: none;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--accent-soft);
}
.rd-cold-ic svg {
  width: 16px;
  height: 16px;
  color: var(--accent-ink);
}
.rd-cold-tx {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
  min-width: 0;
}
.rd-cold-title {
  font: 600 var(--fs-sm) / 1.2 var(--font-ui);
  color: var(--ink);
}
.rd-cold-sub {
  font: 400 var(--fs-xs) / 1.35 var(--font-ui);
  color: var(--ink-2);
}
.rd-cold-x {
  flex: none;
  margin-left: auto;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  transition: background 0.12s;
}
.rd-cold-x:hover {
  background: var(--surface-2);
}
.rd-cold-x svg {
  width: 14px;
  height: 14px;
}
.rd-cold-x:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

/* ============ SCORE COLUMNS (Tendance / Pour toi) ============ */
/* These two columns are injected into <TrackTable> through the head-extra /
   row-extra slots, so they render in THIS view's scope and keep their styling
   here. The base .rd-th / .rd-cell / .rd-arr rules below apply ONLY to that
   slotted content — the real table headers/cells are TrackTable's own
   .tt-th / .tt-cell. */
.rd-th {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  text-align: left;
  user-select: none;
}
.rd-arr {
  margin-left: var(--space-05);
  color: var(--accent-ink);
}
.rd-cell {
  min-width: 0;
}
/* Score headers : centered, stretch so the active band reaches the row edge. */
.rd-th--score {
  align-self: stretch;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-05);
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink-2);
  cursor: pointer;
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  transition:
    color 0.12s,
    background 0.12s;
}
.rd-th--score:hover {
  color: var(--ink);
}
.rd-th--score.is-sorted {
  color: var(--accent-ink);
  background: var(--accent-wash);
}
.rd-th--score:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
/* The cell stretches to the full row height so the active-column band is a
   continuous vertical stripe; the ring/dash stays vertically centered. */
.rd-cell--score {
  align-self: stretch;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rd-cell--score.is-active-col {
  background: var(--accent-wash);
}
/* Disliked row: dim the injected score cells like TrackTable dims its own
   .tt-cell (slotted cells aren't .tt-cell, so TrackTable's rule can't reach
   them). Mirrors the pre-extraction .rd-row.disliked > .rd-cell rule. */
.tt-row.disliked > .rd-cell--score {
  opacity: 0.45;
  transition: opacity 0.16s;
}
.tt-row.disliked:hover > .rd-cell--score {
  opacity: 0.7;
}
.rd-ring {
  position: relative;
  display: inline-flex;
}
/* ▲ velocity : accent triangle in the top-right corner of the Tendance ring. */
.rd-velo {
  position: absolute;
  top: -2px;
  right: -3px;
  width: 9px;
  height: 9px;
  display: block;
  color: var(--accent-ink);
  pointer-events: none;
}
.rd-velo svg {
  display: block;
  width: 100%;
  height: 100%;
}
/* « — » muet : no ring, no empty track — the row reads as mono-score, not broken. */
.rd-dash {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-3);
}

/* ============ RESPONSIVE — view chrome + score headers ============ */
/* The table paliers (grid + column drops) live in TrackTable; only the view
   chrome and the slotted score-header shrink stay here. */
@container (max-width: 639px) {
  .rd-head {
    padding: var(--space-4) var(--page-px-mobile) var(--space-3);
  }
  .rd-controls {
    padding: 0 var(--page-px-mobile) var(--space-3);
  }
  .rd-cold {
    margin-inline: var(--page-px-mobile);
  }
  /* Sort select leaves the bar (v1: default order lives in the drawer later). */
  .rd-sort {
    display: none;
  }
  /* Score columns shrink to 52px < 640px: drop the header type down and kill the
     tracking so « TENDANCE »/« POUR TOI » stay readable and stop overlapping. */
  .rd-th--score {
    font-size: var(--fs-nano);
    letter-spacing: 0;
  }
}
</style>
