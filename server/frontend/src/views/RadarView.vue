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
          <SearchInput v-model="state.q" placeholder="Artiste, titre ou label…" :debounce="0" />
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

    <!-- ── Cold-start invite : shown while the user has no likes yet (R7) ── -->
    <div v-if="showColdStart" class="rd-cold">
      <span class="rd-cold-ic" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
        </svg>
      </span>
      <span class="rd-cold-tx">
        <span class="rd-cold-title">Débloque Pour toi</span>
        <span class="rd-cold-sub">Like quelques sons pour activer tes recommandations personnalisées. En attendant, tu vois le classement Tendance.</span>
      </span>
      <button class="rd-cold-x" type="button" aria-label="Fermer" @click="dismissColdStart">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>

    <!-- ── Table : shared grid header/rows, windowed body ── -->
    <section class="rd-table" aria-label="Résultats">
      <div v-if="!isEmpty && !isError" class="rd-thead">
        <span class="rd-th"></span>
        <span class="rd-th">Track</span>
        <span class="rd-th col-style">Style</span>
        <button
          class="rd-th rd-th--btn rd-th--right col-bpm"
          :class="{ 'is-sorted': effectiveSort === 'bpm' }"
          type="button"
          @click="onHeaderSort('bpm')"
        >
          BPM<span v-if="effectiveSort === 'bpm'" class="rd-arr">{{ arrow }}</span>
        </button>
        <span class="rd-th col-key">Key</span>
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
        <span class="rd-th rd-th--avis">Avis</span>
      </div>

      <!-- Loading skeleton : 8 ghost rows in the exact grid (incl. 2 score discs) -->
      <div v-if="initialLoading" class="rd-body" aria-hidden="true">
        <div v-for="i in 8" :key="i" class="rd-row rd-row--skel" :style="{ '--i': i - 1 }">
          <span class="rd-cell"><span class="sk sk-play"></span></span>
          <span class="rd-cell rd-cell--track">
            <span class="sk sk-art"></span>
            <span class="rd-tx">
              <span class="sk sk-line sk-line--title"></span>
              <span class="sk sk-line sk-line--sub"></span>
            </span>
          </span>
          <span class="rd-cell col-style"><span class="sk sk-line sk-line--tag"></span></span>
          <span class="rd-cell rd-cell--right col-bpm"><span class="sk sk-line sk-line--num"></span></span>
          <span class="rd-cell col-key"><span class="sk sk-line sk-line--num"></span></span>
          <span class="rd-cell rd-cell--score col-trend"><span class="sk sk-disc"></span></span>
          <span class="rd-cell rd-cell--score col-reco"><span class="sk sk-disc"></span></span>
          <span class="rd-cell rd-cell--avis"><span class="sk sk-round"></span><span class="sk sk-round"></span></span>
        </div>
      </div>

      <!-- Error state : a fetch failure is not an empty result (offer a retry) -->
      <div v-else-if="isError" class="rd-empty">
        <svg class="rd-empty-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v5" />
          <path d="M12 16h.01" />
        </svg>
        <p class="rd-empty-title">Erreur de chargement</p>
        <p class="rd-empty-sub">Impossible de récupérer les résultats. Réessaie dans un instant.</p>
        <button class="btn" type="button" @click="fetchPage(true)">Réessayer</button>
      </div>

      <!-- Empty state : removable chips repair the search -->
      <div v-else-if="isEmpty" class="rd-empty">
        <svg class="rd-empty-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.2-3.2" />
          <path d="M4 4l14 14" />
        </svg>
        <p class="rd-empty-title">Aucun résultat avec ces filtres</p>
        <p class="rd-empty-sub">Retire un critère ci-dessous ou réinitialise la recherche.</p>
        <div v-if="activeChips.length" class="rd-empty-chips">
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
        <div ref="listEl" class="rd-body">
          <div :style="{ height: padTop + 'px' }" aria-hidden="true"></div>
          <div
            v-for="e in windowItems"
            :key="e.id"
            class="rd-row"
            :class="{
              playing: player.isCurrent(e.id),
              liked: e.avis === 'liked',
              disliked: e.avis === 'disliked',
            }"
            @click="openTrack(e)"
          >
            <span class="rd-cell rd-cell--play">
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
            <span class="rd-cell rd-cell--track">
              <Artwork size="row" :src="artSrc(e)" :alt="e.title" :in-lib="e.in_lib" />
              <span class="rd-tx">
                <span class="rd-title-row">
                  <span class="rd-title">{{ e.title }}</span>
                  <span v-if="e.trend_rank && e.trend_rank <= 50" class="rd-rank">#{{ e.trend_rank }}</span>
                </span>
                <span class="rd-artists" @click.stop>
                  <ArtistLinks :artists="e.artists" :fallback="e.artist" />
                </span>
              </span>
            </span>
            <span class="rd-cell col-style">
              <template v-if="e.genres?.length">
                <RouterLink
                  class="rd-style-link"
                  :to="`/style/${encodeURIComponent(e.genres[0].name)}`"
                  @click.stop
                >
                  <StyleTag :name="e.genres[0].name" :family="e.genres[0].pillar" :depth="e.genres[0].depth" />
                </RouterLink>
                <span v-if="e.genres.length > 1" class="rd-more">+{{ e.genres.length - 1 }}</span>
              </template>
              <StyleTag v-else-if="e.style" :name="e.style" />
              <span v-else class="rd-null">—</span>
            </span>
            <span class="rd-cell rd-cell--right col-bpm">
              <span :class="e.bpm != null ? 'rd-bpm' : 'rd-null'">{{ e.bpm != null ? Math.round(e.bpm) : '—' }}</span>
            </span>
            <span class="rd-cell col-key">
              <span :class="e.key ? 'rd-key' : 'rd-null'">{{ e.key || '—' }}</span>
            </span>
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
                  <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 0.5 9.5 9.5H0.5z" fill="currentColor" /></svg>
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
            <span class="rd-cell rd-cell--avis" @click.stop>
              <LikeDislike :model-value="e.avis" @update:model-value="(v) => setAvis(e, v)" />
            </span>
          </div>
          <div :style="{ height: padBottom + 'px' }" aria-hidden="true"></div>
        </div>
        <div v-if="items.length" class="rd-end">{{ hasMore ? '…' : 'Fin des résultats' }}</div>
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
        <div class="rd-styles-scroll">
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

const { items, total, loading, hasMore, error, fetch: fetchPage, loadMore } = useWindowedList({
  endpoint: '/api/radar/feed',
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

function isRising(e) {
  return e.velocity != null && e.velocity >= VELOCITY_HIGH
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

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(() => {
  const px = parseFloat(window.getComputedStyle(pageEl.value).getPropertyValue('--row-h'))
  if (Number.isFinite(px) && px > 0) rowH.value = px
  // Resolving the scroll ancestor here (after the DOM is up) updates the ref;
  // useVirtualWindow watches it and binds its listeners onto it.
  scrollEl.value = findScrollParent(pageEl.value)
  lastFilterKey = filterKey()
  fetchPage(true)
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

/* ============ TABLE — shared grid header/rows ============ */
.rd-table {
  --rd-grid: 44px minmax(0, 1fr) 176px 56px 48px 64px 64px 84px;
  --rd-gap: var(--space-2);
  padding-bottom: var(--space-8);
}
.rd-thead,
.rd-row {
  display: grid;
  grid-template-columns: var(--rd-grid);
  gap: var(--rd-gap);
  align-items: center;
  padding-inline: var(--page-px);
}
.rd-thead {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 36px;
  background: var(--bg);
  border-bottom: 1px solid var(--line-2);
}
.rd-th {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  text-align: left;
  user-select: none;
}
.rd-th--btn {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  transition: color 0.12s;
}
.rd-th--btn:hover {
  color: var(--ink-2);
}
.rd-th--btn.is-sorted {
  color: var(--accent-ink);
}
.rd-th--btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.rd-th--right {
  text-align: right;
}
.rd-th--avis {
  text-align: center;
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
.rd-arr {
  margin-left: var(--space-05);
  color: var(--accent-ink);
}

/* ============ ROWS ============ */
.rd-row {
  height: var(--row-h);
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  transition: background 0.12s;
}
.rd-row:hover {
  background: var(--surface-2);
}
.rd-row.playing,
.rd-row.playing:hover {
  background: var(--accent-wash);
}
.rd-row.liked {
  background: var(--pos-wash);
}
.rd-row.liked:hover {
  background: var(--pos-wash-2);
}
[data-theme='dark'] .rd-row.liked {
  background: var(--pos-wash-2);
}
.rd-row.disliked > .rd-cell:not(.rd-cell--avis) {
  opacity: 0.45;
  transition: opacity 0.16s;
}
.rd-row.disliked:hover > .rd-cell:not(.rd-cell--avis) {
  opacity: 0.7;
}

.rd-cell {
  min-width: 0;
}
.rd-cell--right {
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
.rd-row:hover .pbtn {
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
.rd-cell--track {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
/* Local sizing of the shared Artwork (brief: 38px row cover). */
.rd-cell--track :deep(.artwork--row) {
  width: 38px;
}
.rd-tx {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.rd-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.rd-title {
  font: 600 var(--fs-table) / 1.25 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rd-row.playing .rd-title {
  color: var(--accent-ink);
}
.rd-rank {
  display: inline-flex;
  align-items: center;
  padding: var(--space-05) var(--space-15);
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-nano) / 1 var(--font-mono);
  flex: none;
}
.rd-artists {
  font: 400 var(--fs-table-sm) / 1.25 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

/* ============ STYLE CELL (1 tag + « +N ») ============ */
.col-style {
  display: flex;
  align-items: center;
  gap: var(--space-15);
}
.rd-style-link {
  text-decoration: none;
  min-width: 0;
  display: inline-flex;
}
.rd-more {
  font: 500 var(--fs-nano) / 1 var(--font-mono);
  color: var(--ink-3);
  flex: none;
}

/* ============ DATA CELLS ============ */
.rd-bpm {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-2);
}
.rd-key {
  font: 600 var(--fs-table) var(--font-mono);
  color: var(--accent-ink);
}
.rd-null {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-3);
}

/* ============ SCORE CELLS (Tendance / Pour toi) ============ */
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

/* ============ AVIS (shared LikeDislike, local deltas only) ============ */
.rd-cell--avis {
  display: flex;
  justify-content: center;
}
/* Avis buttons stay visible at rest (neutral --ink-3 from LikeDislike); only
   Play is hover-revealed on desktop. Liked/disliked colored states below. */
.rd-cell--avis :deep(.ld-btn) {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border-color: transparent;
  background: transparent;
}
.rd-cell--avis :deep(.ld-btn:hover) {
  background: var(--surface-3);
}
.rd-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like),
.rd-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  opacity: 1;
}
.rd-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like) {
  background: var(--pos-soft);
}
.rd-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  background: var(--neg-soft);
}

/* ============ END SENTINEL ============ */
.rd-end {
  font: 500 var(--fs-xs) / 1 var(--font-mono);
  color: var(--ink-3);
  text-align: center;
  padding: var(--space-4) var(--page-px) 0;
}

/* ============ SKELETON ============ */
.rd-row--skel {
  cursor: default;
}
.sk {
  display: inline-block;
  background: var(--surface-2);
  border-radius: var(--r-xs);
  animation: rd-pulse 1.4s ease-in-out infinite;
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
.sk-disc {
  width: 30px;
  height: 30px;
  border-radius: 50%;
}
.sk-round {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  margin: 0 var(--space-05);
}
@keyframes rd-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

/* ============ EMPTY / ERROR STATE ============ */
.rd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-15x) var(--page-px);
  text-align: center;
}
.rd-empty-ic {
  width: 34px;
  height: 34px;
  color: var(--ink-3);
}
.rd-empty-title {
  margin: 0;
  font: 600 var(--fs-md) / 1.3 var(--font-ui);
  color: var(--ink);
}
.rd-empty-sub {
  margin: 0;
  font: 400 var(--fs-sm) / 1.4 var(--font-ui);
  color: var(--ink-2);
}
.rd-empty-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-15);
  margin-top: var(--space-1);
}
.rd-empty .btn {
  margin-top: var(--space-2);
}

/* ============ RESPONSIVE — column drop preserving the 2 scores ============ */
/* Score columns (Tendance/Pour toi), Play, Track and Avis survive to 375px.
   Drop order: Style, then Key, then BPM. */
@container (max-width: 999px) {
  .rd-table {
    --rd-grid: 44px minmax(0, 1fr) 56px 48px 64px 64px 84px;
  }
  .col-style {
    display: none;
  }
}
@container (max-width: 859px) {
  .rd-table {
    --rd-grid: 44px minmax(0, 1fr) 56px 64px 64px 84px;
  }
  .col-key {
    display: none;
  }
}
@container (max-width: 699px) {
  .rd-table {
    --rd-grid: 44px minmax(0, 1fr) 64px 64px 84px;
  }
  .col-bpm {
    display: none;
  }
}
@container (max-width: 639px) {
  .rd-table {
    --rd-grid: 40px minmax(0, 1fr) 52px 52px 76px;
    --rd-gap: var(--space-1);
  }
  .rd-thead,
  .rd-row {
    padding-inline: var(--page-px-mobile);
  }
  .rd-head {
    padding: var(--space-4) var(--page-px-mobile) var(--space-3);
  }
  .rd-controls {
    padding: 0 var(--page-px-mobile) var(--space-3);
  }
  .rd-cold {
    margin-inline: var(--page-px-mobile);
  }
  .rd-end {
    padding-inline: var(--page-px-mobile);
  }
  .rd-empty {
    padding-inline: var(--page-px-mobile);
  }
  /* Sort select leaves the bar (v1: default order lives in the drawer later). */
  .rd-sort {
    display: none;
  }
  /* Touch: play always visible (avis is already visible at rest). */
  .pbtn {
    opacity: 1;
  }
}
</style>
