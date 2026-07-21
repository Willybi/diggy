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
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
        <div v-if="menuOpen" class="xp-menu" role="menu">
          <button class="xp-menu-item" type="button" role="menuitem" @click="openExternalImport">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            Ajouter un track
          </button>
          <button class="xp-menu-item" type="button" role="menuitem" @click="openXmlImport">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
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
          <FilterPanel :result-count="total" :loading="loading" @reset="resetFilters" @close="closePanel">
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
              <SearchInput v-model="state.label" :icon="false" placeholder="Defected, Drumcode…" :debounce="0" />
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

    <!-- ── Table : shared grid header/rows, windowed body ── -->
    <section class="xp-table" aria-label="Résultats">
      <div v-if="!isEmpty && !isError" class="xp-thead">
        <span class="xp-th"></span>
        <button
          class="xp-th xp-th--btn"
          :class="{ 'is-sorted': state.sort === 'title' }"
          type="button"
          @click="onHeaderSort('title')"
        >
          Track<span v-if="state.sort === 'title'" class="xp-arr">{{ arrow }}</span>
        </button>
        <span class="xp-th col-style">Style</span>
        <button
          class="xp-th xp-th--btn xp-th--right col-bpm"
          :class="{ 'is-sorted': state.sort === 'bpm' }"
          type="button"
          @click="onHeaderSort('bpm')"
        >
          BPM<span v-if="state.sort === 'bpm'" class="xp-arr">{{ arrow }}</span>
        </button>
        <button
          class="xp-th xp-th--btn col-key"
          :class="{ 'is-sorted': state.sort === 'key' }"
          type="button"
          @click="onHeaderSort('key')"
        >
          Key<span v-if="state.sort === 'key'" class="xp-arr">{{ arrow }}</span>
        </button>
        <button
          class="xp-th xp-th--btn xp-th--right col-dur"
          :class="{ 'is-sorted': state.sort === 'duration_ms' }"
          type="button"
          @click="onHeaderSort('duration_ms')"
        >
          Durée<span v-if="state.sort === 'duration_ms'" class="xp-arr">{{ arrow }}</span>
        </button>
        <span class="xp-th xp-th--avis">Avis</span>
      </div>

      <!-- Loading skeleton (E13) : 8 ghost rows in the exact grid -->
      <div v-if="initialLoading" class="xp-body" aria-hidden="true">
        <div v-for="i in 8" :key="i" class="xp-row xp-row--skel" :style="{ '--i': i - 1 }">
          <span class="xp-cell"><span class="sk sk-play"></span></span>
          <span class="xp-cell xp-cell--track">
            <span class="sk sk-art"></span>
            <span class="xp-tx">
              <span class="sk sk-line sk-line--title"></span>
              <span class="sk sk-line sk-line--sub"></span>
            </span>
          </span>
          <span class="xp-cell col-style"><span class="sk sk-line sk-line--tag"></span></span>
          <span class="xp-cell xp-cell--right col-bpm"><span class="sk sk-line sk-line--num"></span></span>
          <span class="xp-cell col-key"><span class="sk sk-line sk-line--num"></span></span>
          <span class="xp-cell xp-cell--right col-dur"><span class="sk sk-line sk-line--num"></span></span>
          <span class="xp-cell xp-cell--avis"><span class="sk sk-round"></span><span class="sk sk-round"></span></span>
        </div>
      </div>

      <!-- Error state : a fetch failure is not an empty result (offer a retry) -->
      <div v-else-if="isError" class="xp-empty">
        <svg class="xp-empty-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v5" />
          <path d="M12 16h.01" />
        </svg>
        <p class="xp-empty-title">Erreur de chargement</p>
        <p class="xp-empty-sub">Impossible de récupérer les résultats. Réessaie dans un instant.</p>
        <button class="btn" type="button" @click="fetchPage(true)">Réessayer</button>
      </div>

      <!-- Empty state (E10) : removable chips repair the search -->
      <div v-else-if="isEmpty" class="xp-empty">
        <svg class="xp-empty-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.2-3.2" />
          <path d="M4 4l14 14" />
        </svg>
        <p class="xp-empty-title">Aucun résultat avec ces filtres</p>
        <p class="xp-empty-sub">Retire un critère ci-dessous ou réinitialise la recherche.</p>
        <div v-if="activeChips.length" class="xp-empty-chips">
          <FilterChip
            v-for="chip in activeChips"
            :key="chip.id"
            :label="chip.label"
            :value="chip.value"
            empty
            @remove="removeChip(chip)"
          />
        </div>
        <button class="btn" type="button" @click="resetFilters">Réinitialiser tous les filtres</button>
      </div>

      <!-- Windowed rows : only the visible slice is rendered between spacers -->
      <template v-else>
        <div ref="listEl" class="xp-body">
          <div :style="{ height: padTop + 'px' }" aria-hidden="true"></div>
          <div
            v-for="e in windowItems"
            :key="e.id"
            class="xp-row"
            :class="{
              playing: player.isCurrent(e.id),
              liked: e.avis === 'liked',
              disliked: e.avis === 'disliked',
            }"
            @click="openTrack(e)"
          >
            <span class="xp-cell xp-cell--play">
              <button
                v-if="e.has_preview"
                class="pbtn"
                :class="{ 'pbtn--playing': player.isCurrent(e.id) }"
                type="button"
                :aria-label="`Écouter ${e.title}`"
                @click.stop="playTrack(e)"
              >
                <svg v-if="!(player.isCurrent(e.id) && player.playing)" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M8 5.5v13l11-6.5z" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <rect x="7" y="5" width="3.4" height="14" rx="1" />
                  <rect x="13.6" y="5" width="3.4" height="14" rx="1" />
                </svg>
              </button>
            </span>
            <span class="xp-cell xp-cell--track">
              <Artwork size="row" :src="artSrc(e)" :alt="e.title" :in-lib="e.in_lib" />
              <span class="xp-tx">
                <span class="xp-title-row">
                  <span class="xp-title">{{ e.title }}</span>
                  <span v-if="e.trend_rank && e.trend_rank <= 50" class="xp-rank">#{{ e.trend_rank }}</span>
                </span>
                <span class="xp-artists" @click.stop>
                  <ArtistLinks :artists="e.artists" :fallback="e.artist" />
                </span>
              </span>
            </span>
            <span class="xp-cell col-style">
              <template v-if="e.genres?.length">
                <RouterLink
                  class="xp-style-link"
                  :to="`/style/${encodeURIComponent(e.genres[0].name)}`"
                  @click.stop
                >
                  <StyleTag :name="e.genres[0].name" :family="e.genres[0].pillar" :depth="e.genres[0].depth" />
                </RouterLink>
                <span v-if="e.genres.length > 1" class="xp-more">+{{ e.genres.length - 1 }}</span>
              </template>
              <StyleTag v-else-if="e.style" :name="e.style" />
              <span v-else class="xp-null">—</span>
            </span>
            <span class="xp-cell xp-cell--right col-bpm">
              <span :class="e.bpm != null ? 'xp-bpm' : 'xp-null'">{{ e.bpm != null ? Math.round(e.bpm) : '—' }}</span>
            </span>
            <span class="xp-cell col-key">
              <span :class="e.key ? 'xp-key' : 'xp-null'">{{ e.key || '—' }}</span>
            </span>
            <span class="xp-cell xp-cell--right col-dur">
              <span :class="e.duration_ms > 0 ? 'xp-dur' : 'xp-null'">{{ e.duration_ms > 0 ? fmtMs(e.duration_ms) : '—' }}</span>
            </span>
            <span class="xp-cell xp-cell--avis" @click.stop>
              <LikeDislike :model-value="e.avis" @update:model-value="(v) => setAvis(e, v)" />
            </span>
          </div>
          <div :style="{ height: padBottom + 'px' }" aria-hidden="true"></div>
        </div>
        <div v-if="items.length" class="xp-end">{{ hasMore ? '…' : 'Fin des résultats' }}</div>
      </template>
    </section>

    <!-- ── Mobile filter drawer (< 640) ── -->
    <FilterDrawer v-model:open="drawerOpen" :result-count="total" :loading="loading" @reset="resetFilters">
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
        <ArtistTypeAhead :model-value="state.artist_id" variant="drawer" @update:model-value="setArtists" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Label</span>
        <SearchInput v-model="state.label" :icon="false" placeholder="Defected, Drumcode…" variant="drawer" :debounce="0" />
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

    <ImportRekordboxModal v-if="showImportModal" @close="showImportModal = false" @done="onImportDone" />

    <ExternalImportModal
      v-if="showExternalImportModal"
      @close="showExternalImportModal = false"
      @imported="onExternalImportDone"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { fmtMs } from '../utils/format'
import { useAudioPlayer } from '../stores/audioPlayer'
import { useFilterState } from '../composables/useFilterState.js'
import { useVirtualWindow } from '../composables/useVirtualWindow.js'
import { useWindowedList } from '../composables/useWindowedList.js'
import { buildChips, defaultValue } from '../components/filters/criteria.js'
import { compareCamelot, CAMELOT_KEYS } from '../components/filters/camelot.js'
import FilterBar from '../components/filters/FilterBar.vue'
import FilterChip from '../components/filters/FilterChip.vue'
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
import Artwork from '../components/Artwork.vue'
import StyleTag from '../components/StyleTag.vue'
import ArtistLinks from '../components/ArtistLinks.vue'
import LikeDislike from '../components/LikeDislike.vue'
import ImportRekordboxModal from '../components/ImportRekordboxModal.vue'
import ExternalImportModal from '../components/ExternalImportModal.vue'

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

const { items, total, loading, hasMore, error, fetch: fetchPage, loadMore } = useWindowedList({
  endpoint: '/api/catalog/',
  buildParams: buildSearchParams,
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
const listEl = ref(null)
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

// ── Rows ─────────────────────────────────────────────────────────────────────

function artSrc(e) {
  return e.has_artwork ? `/storage/catalog-artworks/${e.id}.jpg` : undefined
}

function openTrack(e) {
  router.push(`/catalog/${e.id}`)
}

function playTrack(e) {
  player.play({
    id: e.id,
    catalog_id: e.id,
    title: e.title,
    artist: e.artist,
    artist_id: e.artist_id,
    bpm: e.bpm,
    key: e.key,
  })
}

async function setAvis(entry, avis) {
  const prev = entry.avis
  entry.avis = avis
  try {
    await api.patch(`/api/catalog/${entry.id}/avis`, { avis })
  } catch {
    entry.avis = prev
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
  fetchPage(true)
  fetchCounts()
  fetchGenres()
  hydrateArtists()
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
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

/* ============ TABLE — shared grid header/rows ============ */
.xp-table {
  --xp-grid: 44px minmax(0, 1fr) 176px 56px 48px 60px 84px;
  --xp-gap: var(--space-2);
  padding-bottom: var(--space-8);
}
.xp-thead,
.xp-row {
  display: grid;
  grid-template-columns: var(--xp-grid);
  gap: var(--xp-gap);
  align-items: center;
  padding-inline: var(--page-px);
}
.xp-thead {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 36px;
  background: var(--bg);
  border-bottom: 1px solid var(--line-2);
}
.xp-th {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  text-align: left;
  user-select: none;
}
.xp-th--btn {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  transition: color 0.12s;
}
.xp-th--btn:hover {
  color: var(--ink-2);
}
.xp-th--btn.is-sorted {
  color: var(--accent-ink);
}
.xp-th--btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.xp-th--right {
  text-align: right;
}
.xp-th--avis {
  text-align: center;
}
.xp-arr {
  margin-left: var(--space-05);
  color: var(--accent-ink);
}

/* ============ ROWS ============ */
.xp-row {
  height: var(--row-h);
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  transition: background 0.12s;
}
.xp-row:hover {
  background: var(--surface-2);
}
.xp-row.playing,
.xp-row.playing:hover {
  background: var(--accent-wash);
}
.xp-row.liked {
  background: var(--pos-wash);
}
.xp-row.liked:hover {
  background: var(--pos-wash-2);
}
[data-theme='dark'] .xp-row.liked {
  background: var(--pos-wash-2);
}
.xp-row.disliked > .xp-cell:not(.xp-cell--avis) {
  opacity: 0.45;
  transition: opacity 0.16s;
}
.xp-row.disliked:hover > .xp-cell:not(.xp-cell--avis) {
  opacity: 0.7;
}

.xp-cell {
  min-width: 0;
}
.xp-cell--right {
  text-align: right;
}

/* ============ PLAY ============ */
.pbtn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.12s,
    background 0.12s;
}
.xp-row:hover .pbtn {
  opacity: 1;
}
.pbtn svg {
  width: 11px;
  height: 11px;
}
.pbtn--playing {
  opacity: 1;
  background: var(--accent);
  border-color: transparent;
  color: var(--on-accent);
}

/* ============ TRACK CELL ============ */
.xp-cell--track {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
/* Local sizing of the shared Artwork (brief: 38px row cover). */
.xp-cell--track :deep(.artwork--row) {
  width: 38px;
}
.xp-tx {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.xp-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.xp-title {
  font: 600 var(--fs-table) / 1.25 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.xp-row.playing .xp-title {
  color: var(--accent-ink);
}
.xp-rank {
  display: inline-flex;
  align-items: center;
  padding: var(--space-05) var(--space-15);
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-nano) / 1 var(--font-mono);
  flex: none;
}
.xp-artists {
  font: 400 var(--fs-table-sm) / 1.25 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

/* ============ STYLE CELL (E12 : 1 tag + « +N ») ============ */
.col-style {
  display: flex;
  align-items: center;
  gap: var(--space-15);
}
.xp-style-link {
  text-decoration: none;
  min-width: 0;
  display: inline-flex;
}
.xp-more {
  font: 500 var(--fs-nano) / 1 var(--font-mono);
  color: var(--ink-3);
  flex: none;
}

/* ============ DATA CELLS ============ */
.xp-bpm,
.xp-dur {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-2);
}
.xp-key {
  font: 600 var(--fs-table) var(--font-mono);
  color: var(--accent-ink);
}
.xp-null {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-3);
}

/* ============ AVIS (shared LikeDislike, local deltas only) ============ */
.xp-cell--avis {
  display: flex;
  justify-content: center;
}
.xp-cell--avis :deep(.ld-btn) {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border-color: transparent;
  background: transparent;
  opacity: 0;
}
.xp-row:hover .xp-cell--avis :deep(.ld-btn) {
  opacity: 1;
}
.xp-cell--avis :deep(.ld-btn:hover) {
  background: var(--surface-3);
}
.xp-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like),
.xp-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  opacity: 1;
}
.xp-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like) {
  background: var(--pos-soft);
}
.xp-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  background: var(--neg-soft);
}

/* ============ END SENTINEL ============ */
.xp-end {
  font: 500 var(--fs-xs) / 1 var(--font-mono);
  color: var(--ink-3);
  text-align: center;
  padding: var(--space-4) var(--page-px) 0;
}

/* ============ SKELETON (E13) ============ */
.xp-row--skel {
  cursor: default;
}
.sk {
  display: inline-block;
  background: var(--surface-2);
  border-radius: var(--r-xs);
  animation: xp-pulse 1.4s ease-in-out infinite;
  animation-delay: calc(var(--i, 0) * 0.12s);
}
.sk-play {
  width: 30px;
  height: 30px;
  border-radius: 50%;
}
.sk-art {
  width: 38px;
  height: 38px;
  flex: none;
  background: var(--surface-3);
}
.sk-line {
  height: 10px;
}
.sk-line--title {
  width: 62%;
  background: var(--surface-3);
}
.sk-line--sub {
  width: 40%;
}
.sk-line--tag {
  width: 90px;
  height: 18px;
  border-radius: var(--r-pill);
}
.sk-line--num {
  width: 34px;
}
.sk-round {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  margin: 0 var(--space-05);
}
@keyframes xp-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

/* ============ EMPTY STATE (E10) ============ */
.xp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-15x) var(--page-px);
  text-align: center;
}
.xp-empty-ic {
  width: 34px;
  height: 34px;
  color: var(--ink-3);
}
.xp-empty-title {
  margin: 0;
  font: 600 var(--fs-md) / 1.3 var(--font-ui);
  color: var(--ink);
}
.xp-empty-sub {
  margin: 0;
  font: 400 var(--fs-sm) / 1.4 var(--font-ui);
  color: var(--ink-2);
}
.xp-empty-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-15);
  margin-top: var(--space-1);
}
.xp-empty .btn {
  margin-top: var(--space-2);
}

/* ============ RESPONSIVE — column drop (4 tiers) ============ */
@container (max-width: 999px) {
  .xp-table {
    --xp-grid: 44px minmax(0, 1fr) 176px 56px 48px 84px;
  }
  .col-dur {
    display: none;
  }
}
@container (max-width: 859px) {
  .xp-table {
    --xp-grid: 44px minmax(0, 1fr) 56px 48px 84px;
  }
  .col-style {
    display: none;
  }
}
@container (max-width: 699px) {
  .xp-table {
    --xp-grid: 44px minmax(0, 1fr) 56px 84px;
  }
  .col-key {
    display: none;
  }
}
@container (max-width: 639px) {
  .xp-table {
    --xp-grid: 40px minmax(0, 1fr) 46px 76px;
    --xp-gap: var(--space-1);
  }
  .xp-thead,
  .xp-row {
    padding-inline: var(--page-px-mobile);
  }
  .xp-head {
    padding: var(--space-4) var(--page-px-mobile) var(--space-3);
  }
  .xp-controls {
    padding: 0 var(--page-px-mobile) var(--space-3);
  }
  .xp-end {
    padding-inline: var(--page-px-mobile);
  }
  .xp-empty {
    padding-inline: var(--page-px-mobile);
  }
  /* Sort select leaves the bar (v1: default order lives in the drawer later). */
  .xp-sort {
    display: none;
  }
  /* Touch: play and avis always visible. */
  .pbtn,
  .xp-cell--avis :deep(.ld-btn) {
    opacity: 1;
  }
}
</style>
