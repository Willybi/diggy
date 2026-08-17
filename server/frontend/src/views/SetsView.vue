<template>
  <div class="st-page">
    <!-- ── Head : identity + counter + add ── -->
    <header class="page-head st-head">
      <div class="titles">
        <h1>Sets</h1>
        <div class="st-sub">
          {{ headCount }}
          <span v-if="isOpinionMode && capped" class="st-cap-note">· 200 premiers affichés</span>
        </div>
      </div>
      <button class="btn btn--accent st-add" type="button" @click="openAdd">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.2"
          aria-hidden="true"
        >
          <path d="M12 5v14M5 12h14" stroke-linecap="round" />
        </svg>
        Ajouter
      </button>
    </header>

    <!-- ── Filter bar + chips + inline panel ── -->
    <div class="st-controls">
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
          <SearchInput v-model="state.q" placeholder="Rechercher un set…" :debounce="0" />
        </template>
        <template #sort>
          <span class="st-sort">
            <SortSelect
              :model-value="sortValue"
              :options="SORT_OPTIONS"
              aria-label="Trier les sets"
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
              <span class="flt-label">Durée</span>
              <SegmentedFilter v-model="state.dur" :options="DUR_OPTIONS" mono />
            </div>
            <div class="flt-field">
              <span class="flt-label">Année</span>
              <RangeSlider v-model="state.year" :min="YEAR_MIN" :max="YEAR_MAX" label="Année" />
            </div>
            <div class="flt-field flt-field--4">
              <span class="flt-label">Styles</span>
              <div class="st-styles-scroll">
                <StyleMultiSelect v-model="state.genre" :options="genreOptions" />
              </div>
            </div>
            <div class="flt-field">
              <span class="flt-label">Tracks</span>
              <SegmentedFilter v-model="state.tracks" :options="TRACKS_OPTIONS" mono />
            </div>
            <div class="flt-field">
              <span class="flt-label">Avis</span>
              <SegmentedFilter v-model="state.avis" :options="AVIS_OPTIONS" />
            </div>
          </FilterPanel>
        </template>
      </FilterBar>
    </div>

    <!-- ── Table : shared grid header/rows, infinite scroll ── -->
    <section class="st-table" aria-label="Liste des sets">
      <div v-if="showSkeleton || items.length" class="st-thead lt-thead">
        <span class="st-th col-play lt-th"></span>
        <button
          class="st-th st-th--btn col-set lt-th lt-th--btn"
          :class="{ 'is-sorted': effSort === 'title' }"
          type="button"
          @click="onHeaderSort('title')"
        >
          Set<span v-if="effSort === 'title'" class="st-arr">{{ arrow }}</span>
        </button>
        <span class="st-th col-genre lt-th">Genre</span>
        <button
          class="st-th st-th--btn col-date lt-th lt-th--btn"
          :class="{ 'is-sorted': effSort === 'date' }"
          type="button"
          @click="onHeaderSort('date')"
        >
          Date<span v-if="effSort === 'date'" class="st-arr">{{ arrow }}</span>
        </button>
        <button
          class="st-th st-th--btn st-th--center col-tracks lt-th lt-th--btn lt-th--center"
          :class="{ 'is-sorted': effSort === 'tracks' }"
          type="button"
          @click="onHeaderSort('tracks')"
        >
          Tracks<span v-if="effSort === 'tracks'" class="st-arr">{{ arrow }}</span>
        </button>
        <button
          class="st-th st-th--btn st-th--right col-dur lt-th lt-th--btn lt-th--right"
          :class="{ 'is-sorted': effSort === 'duration' }"
          type="button"
          @click="onHeaderSort('duration')"
        >
          Durée<span v-if="effSort === 'duration'" class="st-arr">{{ arrow }}</span>
        </button>
        <span class="st-th st-th--center col-avis lt-th lt-th--center">Avis</span>
      </div>

      <!-- Loading skeleton : 8 ghost rows in the exact grid -->
      <div v-if="showSkeleton" class="st-body" aria-hidden="true">
        <div v-for="i in 8" :key="i" class="st-row st-row--skel lt-row" :style="{ '--i': i - 1 }">
          <div class="st-cell col-play"><span class="sk sk-play"></span></div>
          <div class="st-cell col-set st-cell--set">
            <span class="sk sk-art"></span>
            <div class="st-tx">
              <span class="sk sk-line sk-line--title"></span>
              <span class="sk sk-line sk-line--sub"></span>
            </div>
          </div>
          <div class="st-cell col-genre"><span class="sk sk-line sk-line--tag"></span></div>
          <div class="st-cell col-date"><span class="sk sk-line sk-line--num"></span></div>
          <div class="st-cell col-tracks st-cell--center"><span class="sk sk-round"></span></div>
          <div class="st-cell col-dur st-cell--right">
            <span class="sk sk-line sk-line--num"></span>
          </div>
          <div class="st-cell col-avis st-cell--center">
            <span class="sk sk-round"></span><span class="sk sk-round"></span>
          </div>
        </div>
      </div>

      <!-- Empty : no search result (loupe + clear) -->
      <div v-else-if="isEmpty && hasSearch" class="st-empty">
        <svg
          class="st-empty-ic"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.2-3.2" />
        </svg>
        <p class="st-empty-title">Aucun set trouvé</p>
        <p class="st-empty-sub">
          Aucun set ne correspond à « {{ state.q.trim() }} ». Vérifie l’orthographe ou élargis ta
          recherche.
        </p>
        <button class="btn" type="button" @click="clearSearch">Effacer la recherche</button>
      </div>

      <!-- Empty : avis filter with no match (adapted copy, no action) -->
      <div v-else-if="isEmpty && isOpinionMode" class="st-empty">
        <svg
          class="st-empty-ic"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="2.4" />
        </svg>
        <p class="st-empty-title">{{ emptyAvis.title }}</p>
        <p class="st-empty-sub">{{ emptyAvis.sub }}</p>
      </div>

      <!-- Empty : active filters with no match -->
      <div v-else-if="isEmpty && hasActiveFilters" class="st-empty">
        <svg
          class="st-empty-ic"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.2-3.2" />
          <path d="M4 4l14 14" />
        </svg>
        <p class="st-empty-title">Aucun set avec ces filtres</p>
        <p class="st-empty-sub">Retire un critère ou réinitialise la recherche.</p>
        <button class="btn" type="button" @click="resetFilters">Réinitialiser les filtres</button>
      </div>

      <!-- Empty : generic fallback -->
      <div v-else-if="isEmpty" class="st-empty">
        <svg
          class="st-empty-ic"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.2-3.2" />
        </svg>
        <p class="st-empty-title">Aucun set à afficher</p>
      </div>

      <!-- Rows -->
      <div v-else class="st-body">
        <div
          v-for="s in items"
          :key="s.id"
          class="st-row lt-row"
          :class="{
            playing: isSetActive(s.id) && player.playing,
            liked: opinionOf(s.id) === 'liked',
            disliked: opinionOf(s.id) === 'disliked',
          }"
          @click="goToSet(s.id)"
        >
          <div class="st-cell col-play st-cell--play">
            <button
              class="pbtn"
              :class="{ 'pbtn--playing': isSetActive(s.id) && player.playing }"
              type="button"
              :disabled="playLoadingId === s.id"
              :aria-label="`Écouter ${s.title}`"
              @click.stop="playSet(s)"
            >
              <span v-if="playLoadingId === s.id" class="pbtn-spin"></span>
              <svg
                v-else-if="!(isSetActive(s.id) && player.playing)"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M8 5.5v13l11-6.5z" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <rect x="7" y="5" width="3.4" height="14" rx="1" />
                <rect x="13.6" y="5" width="3.4" height="14" rx="1" />
              </svg>
            </button>
          </div>

          <div class="st-cell col-set st-cell--set">
            <Artwork
              size="row"
              :src="s.has_artwork ? `/storage/set-artworks/${s.id}.jpg` : undefined"
              :alt="s.title"
            />
            <div class="st-tx">
              <div class="st-title">{{ s.title }}</div>
              <span v-if="s.artists.length" class="st-artists" @click.stop>
                <ArtistLinks :artists="s.artists" />
              </span>
              <!-- Genre chips fold under the title below 860px (S1) -->
              <div v-if="s.top_genres.length" class="st-genre-fold">
                <RouterLink
                  v-for="g in s.top_genres.slice(0, 2)"
                  :key="g.name"
                  class="st-style-link"
                  :to="`/style/${encodeURIComponent(g.name)}`"
                  @click.stop
                >
                  <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
                </RouterLink>
              </div>
            </div>
          </div>

          <div class="st-cell col-genre st-cell--genre">
            <template v-if="s.top_genres.length">
              <RouterLink
                v-for="g in s.top_genres.slice(0, 2)"
                :key="g.name"
                class="st-style-link"
                :to="`/style/${encodeURIComponent(g.name)}`"
                @click.stop
              >
                <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
              </RouterLink>
            </template>
          </div>

          <div class="st-cell col-date">
            <span :class="s.played_date ? 'st-date' : 'st-null'">{{ fmtDate(s.played_date) }}</span>
          </div>

          <div class="st-cell col-tracks st-cell--center">
            <ScoreRing
              mode="pct"
              size="md"
              :score="s.total_tracks ? s.identified_tracks / s.total_tracks : 0"
              :label="`${s.identified_tracks} / ${s.total_tracks} tracks identifiés`"
            />
          </div>

          <div class="st-cell col-dur st-cell--right">
            <span :class="s.duration_ms ? 'st-dur' : 'st-null'">{{ fmtMs(s.duration_ms) }}</span>
          </div>

          <div class="st-cell col-avis st-cell--center" @click.stop>
            <LikeDislike
              :model-value="opinionOf(s.id)"
              @update:model-value="(v) => setOpinion(s.id, v)"
            />
          </div>
        </div>
      </div>

      <!-- Sentinel (infinite scroll) — always in DOM so the observer attaches -->
      <div ref="sentinel" class="st-sentinel lt-sentinel" :class="{ on: hasMore }">
        <span class="spin"></span>Chargement…
      </div>
    </section>

    <!-- ── Mobile filter drawer (< 640) ── -->
    <FilterDrawer
      v-model:open="drawerOpen"
      :result-count="total"
      :loading="loading"
      @reset="resetFilters"
    >
      <div class="flt-field">
        <span class="flt-label">Durée</span>
        <SegmentedFilter v-model="state.dur" :options="DUR_OPTIONS" mono variant="drawer" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Année</span>
        <RangeSlider v-model="state.year" :min="YEAR_MIN" :max="YEAR_MAX" label="Année" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Styles</span>
        <div class="st-styles-scroll">
          <StyleMultiSelect v-model="state.genre" :options="genreOptions" variant="drawer" />
        </div>
      </div>
      <div class="flt-field">
        <span class="flt-label">Tracks</span>
        <SegmentedFilter v-model="state.tracks" :options="TRACKS_OPTIONS" mono variant="drawer" />
      </div>
      <div class="flt-field">
        <span class="flt-label">Avis</span>
        <SegmentedFilter v-model="state.avis" :options="AVIS_OPTIONS" variant="drawer" />
      </div>
    </FilterDrawer>

    <!-- ── Add modal (2 tabs) — shared chrome via AddModal, tabs as slot body ── -->
    <AddModal v-model:open="showAdd" title="Ajouter un set">
      <div class="st-tabs">
        <button
          class="st-tab"
          :class="{ on: addMode === 'search' }"
          type="button"
          @click="addMode = 'search'"
        >
          Rechercher
        </button>
        <button
          class="st-tab"
          :class="{ on: addMode === 'url' }"
          type="button"
          @click="addMode = 'url'"
        >
          URL
        </button>
      </div>

      <!-- Search tab -->
      <div v-if="addMode === 'search'" class="st-tabpanel">
        <div class="st-search-row">
          <label class="st-tid-search">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.2-3.2" stroke-linecap="round" />
            </svg>
            <input
              v-model="tdQuery"
              type="text"
              placeholder="Titre, artiste ou show TrackID…"
              @keydown.enter="doTrackIDSearch"
            />
          </label>
          <button
            class="btn btn--accent"
            type="button"
            :disabled="tdSearching"
            @click="doTrackIDSearch"
          >
            {{ tdSearching ? 'Recherche…' : 'Rechercher' }}
          </button>
        </div>

        <div v-if="tdResults.length" class="st-tid-count">
          {{ tdResults.length }} résultats TrackID
        </div>

        <div v-if="tdResults.length" class="st-results">
          <div v-for="r in tdResults" :key="r.trackid_id" class="st-res">
            <span class="st-res-art">
              <img v-if="r.artwork_url" :src="r.artwork_url" alt="" loading="lazy" />
              <span v-else class="st-res-ini">{{ (r.title || '?')[0] }}</span>
            </span>
            <span class="st-res-tx">
              <span class="st-res-title" :title="r.title">{{ r.title }}</span>
              <span class="st-res-meta">{{ resultMeta(r) }}</span>
            </span>
            <span v-if="r.already_imported" class="st-res-done">✓ Importé</span>
            <button
              v-else
              class="btn btn--sm"
              type="button"
              :disabled="r._importing"
              @click="doImportFromSearch(r)"
            >
              {{ r._importing ? 'Import…' : 'Importer' }}
            </button>
          </div>
        </div>

        <p v-if="formError && addMode === 'search'" class="st-form-error">{{ formError }}</p>
      </div>

      <!-- URL tab -->
      <div v-else class="st-tabpanel">
        <label class="st-field-label" for="st-url-input">URL TrackID</label>
        <input
          id="st-url-input"
          v-model="importUrl"
          class="st-input st-input--mono"
          :class="{ 'is-error': formError }"
          type="text"
          placeholder="https://trackid.net/audiostream/…"
          @keydown.enter="doImport"
          @input="onUrlInput"
        />
        <p class="st-field-help">Colle le lien d’un show TrackID pour l’importer directement.</p>
        <p v-if="formError" class="st-form-error">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.9"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v5M12 16h.01" stroke-linecap="round" />
          </svg>
          {{ formError }}
        </p>
        <button
          class="btn btn--accent st-url-go"
          type="button"
          :disabled="importing"
          @click="doImport"
        >
          {{ importing ? 'Import…' : 'Importer depuis l’URL' }}
        </button>
      </div>
    </AddModal>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onActivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useOpinionsStore } from '../stores/opinions.js'
import { useAudioPlayer } from '../stores/audioPlayer.js'
import { useToast } from '../stores/toast.js'
import { usePaginatedList } from '../composables/usePaginatedList.js'
import { useOpinionOneShot } from '../composables/useOpinionOneShot.js'
import { useFilterState } from '../composables/useFilterState.js'
import { useScrollRestore } from '../composables/useScrollRestore.js'
import { buildChips } from '../components/filters/criteria.js'
import { fmtMs, fmtDate, fmtNum, pl } from '../utils/format'
import FilterBar from '../components/filters/FilterBar.vue'
import FilterPanel from '../components/filters/FilterPanel.vue'
import FilterDrawer from '../components/filters/FilterDrawer.vue'
import SearchInput from '../components/filters/SearchInput.vue'
import RangeSlider from '../components/filters/RangeSlider.vue'
import StyleMultiSelect from '../components/filters/StyleMultiSelect.vue'
import SegmentedFilter from '../components/filters/SegmentedFilter.vue'
import SortSelect from '../components/filters/SortSelect.vue'
import Artwork from '../components/Artwork.vue'
import ArtistLinks from '../components/ArtistLinks.vue'
import StyleTag from '../components/StyleTag.vue'
import ScoreRing from '../components/ScoreRing.vue'
import LikeDislike from '../components/LikeDislike.vue'
import AddModal from '../components/AddModal.vue'

// Explicit name so <KeepAlive :include> in App.vue matches this cached listing.
defineOptions({ name: 'SetsView' })

const GENRE_OPTIONS_MAX = 150
const YEAR_MIN = 2005
const YEAR_MAX = 2026

const route = useRoute()
const router = useRouter()
const opinions = useOpinionsStore()
const player = useAudioPlayer()

// ── Criteria (contract components/filters/criteria.js) ──────────────────────

const DUR_OPTIONS = [
  { value: 'lt1', label: '< 1h' },
  { value: '1-2', label: '1–2h' },
  { value: '2-3', label: '2–3h' },
  { value: 'gt3', label: '> 3h' },
]
// Duration presets → API bounds in ms ([min, max], null = unbounded).
const DUR_BOUNDS = {
  lt1: [null, 3600000],
  '1-2': [3600000, 7200000],
  '2-3': [7200000, 10800000],
  gt3: [10800000, null],
}
const TRACKS_OPTIONS = [
  { value: 'lt20', label: '< 20' },
  { value: '20-50', label: '20–50' },
  { value: 'gt50', label: '> 50' },
]
const TRACKS_BOUNDS = {
  lt20: [null, 19],
  '20-50': [20, 50],
  gt50: [51, null],
}
const AVIS_OPTIONS = [
  { value: null, label: 'Tous' },
  { value: 'liked', label: 'Aimés' },
  { value: 'disliked', label: 'Rejetés' },
  { value: 'none', label: 'À explorer' },
]

// Artist filter (D8.c): ids in the URL, { id, name } objects in the state — the
// contextual « /sets?artist_id= » landing from Artist Detail. There is no picker
// control in the panel (arrived-at via link), only the removable chip; the cache
// keeps deserialization JSON-stable once the name is hydrated from ?ids=.
// Mirrors ExplorerView's artist chip.
function toArray(raw) {
  if (raw == null) return []
  return Array.isArray(raw) ? raw : [raw]
}
const artistCache = new Map()
function artistFromUrl(s) {
  const id = Number(s)
  if (!Number.isInteger(id) || id <= 0) return null
  return artistCache.get(id) || { id, name: `#${id}` }
}

const criteria = [
  { key: 'q', type: 'text', label: 'Recherche', chip: false },
  { key: 'dur', type: 'segment', label: 'Durée', options: DUR_OPTIONS },
  { key: 'year', type: 'range', label: 'Année', min: YEAR_MIN, max: YEAR_MAX },
  { key: 'genre', type: 'multi', label: 'Style', chipPerValue: true },
  {
    key: 'artist_id',
    type: 'multi',
    label: 'Artiste',
    chipPerValue: true,
    format: (a) => a.name,
    serialize: (v) => (Array.isArray(v) && v.length ? v.map((a) => String(a.id)) : undefined),
    deserialize: (raw) => toArray(raw).map(artistFromUrl).filter(Boolean),
  },
  { key: 'tracks', type: 'segment', label: 'Tracks', options: TRACKS_OPTIONS },
  { key: 'avis', type: 'segment', label: 'Avis', options: AVIS_OPTIONS },
]

// Sort is URL state but not a filter (never a chip, never counted in the badge).
const SORT_FIELDS = ['title', 'date', 'tracks', 'duration']
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

// ── Sort : select + header clicks pilot the same state (default = date desc) ──

const SORT_OPTIONS = [
  { value: 'date', label: 'Date (récent)' },
  { value: 'title', label: 'Titre A–Z' },
  { value: 'tracks', label: 'Nombre de tracks' },
  { value: 'duration', label: 'Durée' },
]
const DEFAULT_ORDER = { title: 'asc', date: 'desc', tracks: 'desc', duration: 'desc' }

// Effective sort/order — the criterion default (null) means « date desc ».
const effSort = computed(() => state.sort || 'date')
const effOrder = computed(() => state.order || DEFAULT_ORDER[effSort.value] || 'desc')
// Composite sort sent server-side: leading '-' = descending.
const sortParam = computed(() => (effOrder.value === 'desc' ? '-' : '') + effSort.value)
const sortValue = computed(() => effSort.value)
const arrow = computed(() => (effOrder.value === 'asc' ? '↑' : '↓'))

function onSortSelect(v) {
  state.sort = v
  state.order = DEFAULT_ORDER[v]
}

function onHeaderSort(field) {
  if (effSort.value === field) {
    // Materialize the key so the flipped order sticks even from the null default.
    state.sort = field
    state.order = effOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    state.sort = field
    state.order = DEFAULT_ORDER[field]
  }
}

// ── Filter state helpers ─────────────────────────────────────────────────────

const panelOpen = ref(false)
const drawerOpen = ref(false)

const activeChips = computed(() => buildChips(criteria, state))
const hasActiveFilters = computed(() => activeChips.value.length > 0)

function applyFilters(next) {
  for (const c of criteria) {
    if (c.key in next) state[c.key] = next[c.key]
  }
}

function resetFilters() {
  state.q = ''
  state.dur = null
  state.year = [YEAR_MIN, YEAR_MAX]
  state.genre = []
  state.artist_id = []
  state.tracks = null
  state.avis = null
}

function closePanel() {
  panelOpen.value = false
}

// Filter params (everything EXCEPT pagination, sort/q handled by the composable,
// and avis handled by the opinion path). Shared by both fetch paths.
function buildExtraParams() {
  const p = {}
  const [durLo, durHi] = DUR_BOUNDS[state.dur] || [null, null]
  if (durLo != null) p.duration_min = durLo
  if (durHi != null) p.duration_max = durHi
  const [yLo, yHi] = state.year
  if (yLo > YEAR_MIN) p.year_min = yLo
  if (yHi < YEAR_MAX) p.year_max = yHi
  const [tLo, tHi] = TRACKS_BOUNDS[state.tracks] || [null, null]
  if (tLo != null) p.tracks_min = tLo
  if (tHi != null) p.tracks_max = tHi
  if (state.genre.length) p.genres = state.genre.join(',')
  // D8.c: CSV of artist ids → /sets router `_parse_id_csv(artist_id)`.
  if (state.artist_id.length) p.artist_id = state.artist_id.map((a) => a.id).join(',')
  return p
}

// ── Paginated list (shared trunk) ──
const { items, total, loading, hasMore, sentinel, fetch, fetchUpTo } = usePaginatedList({
  endpoint: '/api/sets/',
  pageSize: 24,
  sort: () => sortParam.value,
  query: () => state.q,
  extraParams: () => buildExtraParams(),
})

// Independent, unfiltered base count for the head sub-line.
const nBase = ref(null)
const headCount = computed(() =>
  nBase.value == null ? '…' : `${fmtNum(nBase.value)} ${pl(nBase.value, 'set', 'sets')}`,
)

async function fetchBaseCount() {
  try {
    const { data } = await api.get('/api/sets/', { params: { limit: 1 } })
    nBase.value = data.total
  } catch {
    /* the head stays on '…' */
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

// ── Artist chip hydration from the URL (GET /api/artists/?ids=) — resolves the
// #id placeholder into the artist name for the contextual /sets?artist_id= chip
// (mirrors ExplorerView). Idempotent: only fetches ids still missing a name.
async function hydrateArtists() {
  const missing = state.artist_id.filter((a) => !artistCache.has(a.id))
  if (!missing.length) return
  try {
    const { data } = await api.get('/api/artists/', {
      params: { ids: missing.map((a) => a.id).join(','), limit: 100 },
    })
    for (const a of data.items || []) artistCache.set(a.id, { id: a.id, name: a.name })
    // Reassign with resolved names (same ids → URL/fetchKey unchanged, no loop).
    state.artist_id = state.artist_id.map((a) => artistCache.get(a.id) || a)
  } catch {
    /* the chip keeps its #id placeholder */
  }
}
// Re-hydrate whenever the id set changes (fresh landing handled by onMounted; a
// cached KeepAlive re-landing on a new ?artist_id= flows through here).
watch(
  () => state.artist_id.map((a) => a.id).join(','),
  () => hydrateArtists(),
)

// Scroll restoration on a back/forward return.
const scrollRestore = useScrollRestore({
  scroller: () => document.getElementById('main-content'),
  getCount: () => items.value.length,
})

const isOpinionMode = computed(() => !!state.avis)
const hasSearch = computed(() => state.q.trim().length > 0)
const showSkeleton = computed(() => loading.value && !items.value.length)
const isEmpty = computed(() => !loading.value && !items.value.length)

const emptyAvis = computed(() => {
  const map = {
    liked: { title: 'Aucun set liké', sub: 'Tu n’as encore liké aucun set.' },
    disliked: { title: 'Aucun set disliké', sub: 'Tu n’as encore disliké aucun set.' },
    none: { title: 'Aucun set à explorer', sub: 'Tous tes sets ont déjà un avis.' },
  }
  return map[state.avis] || { title: 'Aucun set', sub: '' }
})

function opinionOf(id) {
  return opinions.get('set', id)
}

// ── Opinion one-shot (avis facets) : shared helper ──
// liked/disliked pass the matching ids via `ids=`, « À explorer » (none)
// excludes every rated id via `exclude_ids=`; both carry the panel filters
// (buildExtraParams) + sort + q. `capped` flags a truncated one-shot (limit 200)
// so the head can show « 200 premiers affichés ».
const opinionOneShot = useOpinionOneShot({
  endpoint: '/api/sets/',
  kind: 'set',
  refs: { items, total, hasMore, loading },
  unratedValue: 'none',
  buildParams: () => {
    const p = { ...buildExtraParams(), sort: sortParam.value, limit: 200, offset: 0 }
    const q = state.q.trim()
    if (q) p.q = q
    return p
  },
})
const { capped } = opinionOneShot

// ── Fetch orchestration ──
// `all` (avis null) goes through the shared paginated list (infinite scroll).
// The opinion filters go through the one-shot helper (sentinel stays off).
async function runFetch(reset = true) {
  if (!isOpinionMode.value) {
    await fetch(reset)
    return
  }
  if (!reset) return // opinion filters are not paginated (sentinel stays off)
  await opinionOneShot.run(state.avis)
}

function clearSearch() {
  state.q = ''
}

function goToSet(id) {
  router.push(`/set/${id}`)
}

async function setOpinion(id, val) {
  // Optimistic store update; the row recolors reactively via opinionOf().
  // Keep the PlayerBar avis in sync if that set's track happens to be playing.
  await opinions.set('set', id, val)
}

// ── Play a set in order (frontend queue: fetch its tracklist on demand) ──
const playLoadingId = ref(null)

function isSetActive(id) {
  return player.source?.type === 'list' && player.source?.setId === id
}

async function playSet(s) {
  // Re-click on the active set → toggle play/pause.
  if (isSetActive(s.id)) {
    player.toggle()
    return
  }
  playLoadingId.value = s.id
  try {
    const { data } = await api.get(`/api/sets/${s.id}`)
    const tracks = (data.tracklist || [])
      .filter((t) => !t.is_id && t.catalog_id && t.has_preview)
      .map((t) => ({
        id: t.catalog_id,
        catalog_id: t.catalog_id,
        title: t.catalog_title || t.raw_title,
        artist: t.catalog_artist || t.raw_artist,
        bpm: t.bpm,
        key: t.key,
        has_preview: t.has_preview,
      }))
    if (!tracks.length) {
      useToast().show('Aucun extrait écoutable dans ce set')
      return
    }
    // Queue source: "next" walks the set's tracklist in play order. setId lets
    // the row reflect the playing state (read by isSetActive).
    const source = { type: 'list', setId: s.id, getItems: () => tracks }
    await player.play(tracks[0], source)
  } catch {
    useToast().show('Impossible de lire ce set')
  } finally {
    playLoadingId.value = null
  }
}

// Filters/sort changed → the URL is the trigger (debounce handled by
// useFilterState). Dedup on a serialized fetch key so a same-content replace
// (e.g. an echo, or a sort→sort no-op) never refetches.
function fetchKey() {
  return JSON.stringify([sortParam.value, state.q.trim(), buildExtraParams(), state.avis])
}
let lastKey = null
watch(
  () => route.query,
  () => {
    if (route.path !== '/sets') return
    const k = fetchKey()
    if (k === lastKey) return
    lastKey = k
    runFetch(true)
  },
)

// ── Add modal ──
const showAdd = ref(false)
const addMode = ref('search') // search | url
const importUrl = ref('')
const importing = ref(false)
const formError = ref('')
const tdQuery = ref('')
const tdResults = ref([])
const tdSearching = ref(false)

function openAdd() {
  showAdd.value = true
  addMode.value = 'search'
  tdResults.value = []
  formError.value = ''
}

function onUrlInput() {
  formError.value = ''
}

function resultMeta(r) {
  const parts = []
  if (r.channel) parts.push(r.channel)
  if (r.track_count) parts.push(`${r.track_count} tracks`)
  if (r.created_on) parts.push(fmtDate(r.created_on.slice(0, 10)))
  return parts.join(' · ')
}

async function doTrackIDSearch() {
  formError.value = ''
  if (!tdQuery.value.trim()) return
  tdSearching.value = true
  try {
    const { data } = await api.get('/api/sets/search', { params: { q: tdQuery.value.trim() } })
    tdResults.value = data
    if (!data.length) formError.value = 'Aucun résultat sur TrackID'
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Erreur de recherche'
  } finally {
    tdSearching.value = false
  }
}

async function doImportFromSearch(result) {
  result._importing = true
  formError.value = ''
  try {
    const { data } = await api.post('/api/sets/import', { slug: result.slug })
    result.already_imported = true
    result._importing = false
    await opinions.set('set', data.id, 'liked')
    await runFetch(true)
  } catch (e) {
    result._importing = false
    formError.value = e.response?.data?.detail || 'Erreur d’import'
  }
}

async function doImport() {
  formError.value = ''
  if (!importUrl.value.trim()) {
    formError.value = 'URL non reconnue — colle un lien de show TrackID.'
    return
  }
  importing.value = true
  try {
    const { data } = await api.post('/api/sets/import', { url: importUrl.value.trim() })
    importUrl.value = ''
    showAdd.value = false
    router.push(`/set/${data.id}`)
  } catch (e) {
    formError.value =
      e.response?.data?.detail || 'URL non reconnue — colle un lien de show TrackID.'
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  lastKey = fetchKey()
  scrollRestore.restore({
    initialFetch: () => runFetch(true),
    hydrate: (count) => (isOpinionMode.value ? runFetch(true) : fetchUpTo(count)),
  })
  fetchBaseCount()
  fetchGenres()
  hydrateArtists()
})

// Cached return under <KeepAlive>: reactivated (no onMounted), rows/filters still
// in memory — only re-apply the scroll offset, no refetch. The first activation
// follows onMounted (which already restored scroll) and is skipped.
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
.st-page {
  container-type: inline-size;
  min-width: 0;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* ============ HEAD ============ */
.titles h1 {
  margin: 0;
  font: 700 var(--fs-lg) / 1.1 var(--font-ui);
  letter-spacing: -0.3px;
  color: var(--ink);
}
.st-sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm) / 1 var(--font-mono);
  color: var(--ink-3);
}
.st-cap-note {
  margin-left: var(--space-1);
  color: var(--ink-2);
}
.st-add {
  flex: none;
  margin-left: auto;
}

/* ============ CONTROLS ============ */
.st-controls {
  padding: 0 var(--page-px) var(--space-4);
}
/* Styles field: the full genre list scrolls inside its panel cell. */
.st-styles-scroll {
  max-height: 180px;
  overflow-y: auto;
}

/* ============ TABLE — shared grid header/rows ============ */
.st-table {
  --st-grid: 44px minmax(0, 1fr) 190px 104px 72px 92px 80px;
  --st-gap: var(--space-3);
  padding-bottom: var(--space-8);
}
/* Column track + gap are view-specific and stay here; the grid frame, sticky
   header and header-cell styling come from the shared .lt-* socle
   (assets/list-table.css). The st-thead/st-row/st-th* classes remain on the
   elements alongside the lt-* ones (grid var here, base there). */
.st-thead,
.st-row {
  grid-template-columns: var(--st-grid);
  gap: var(--st-gap);
}
.st-arr {
  margin-left: var(--space-05);
  color: var(--accent-ink);
}

/* ============ ROWS ============ */
/* Base row + hover + liked wash come from the shared .lt-row socle. Playing
   (accent wash) and disliked (dimmed, sparing the play + avis cells) are
   Sets-specific and stay here. */
.st-row.playing,
.st-row.playing:hover {
  background: var(--accent-wash);
}
.st-row.disliked > .st-cell:not(.st-cell--avis):not(.st-cell--play) {
  opacity: 0.45;
  transition: opacity 0.16s;
}
.st-row.disliked:hover > .st-cell:not(.st-cell--avis):not(.st-cell--play) {
  opacity: 0.7;
}
.st-cell {
  min-width: 0;
}
.st-cell--center {
  display: flex;
  justify-content: center;
}
.st-cell--right {
  text-align: right;
}

/* ============ PLAY ============ */
.st-cell--play {
  display: flex;
  justify-content: center;
}
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
.st-row:hover .pbtn {
  opacity: 1;
}
.pbtn:hover {
  background: var(--surface-2);
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
.pbtn:disabled {
  cursor: default;
}
.pbtn-spin {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid var(--line-2);
  border-top-color: var(--accent);
  animation: spin 0.7s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .pbtn-spin {
    animation: none;
  }
}

/* ============ SET CELL ============ */
.st-cell--set {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
/* Local sizing of the shared Artwork (BRIEF S4 : 44px cover, --r-sm). */
.st-cell--set :deep(.artwork--row) {
  width: 44px;
}
.st-cell--set :deep(.artwork--row .aw-frame) {
  border-radius: var(--r-sm);
}
.st-tx {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.st-title {
  font: 600 var(--fs-table) / 1.25 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.st-row.playing .st-title {
  color: var(--accent-ink);
}
.st-artists {
  font: 400 var(--fs-table-sm) / 1.25 var(--font-ui);
  color: var(--ink-3);
  min-width: 0;
}
.st-artists :deep(.art-link:hover) {
  color: var(--ink);
  text-decoration: underline;
}
/* Genre chips folded under the title (< 860px, S1) — hidden by default. */
.st-genre-fold {
  display: none;
  flex-wrap: wrap;
  gap: var(--space-15);
  margin-top: var(--space-05);
}

/* ============ GENRE CELL ============ */
.st-cell--genre {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  overflow: hidden;
}
.st-style-link {
  text-decoration: none;
  min-width: 0;
  display: inline-flex;
}

/* ============ DATA CELLS ============ */
.st-date,
.st-dur {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-2);
}
.st-null {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-3);
}

/* ============ AVIS (shared LikeDislike, local deltas) ============ */
.st-cell--avis :deep(.ld-btn) {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border-color: transparent;
  background: transparent;
}
.st-cell--avis :deep(.ld-btn:hover) {
  background: var(--surface-3);
}
.st-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like) {
  background: var(--pos-soft);
}
.st-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  background: var(--neg-soft);
}

/* ============ SENTINEL (base from the shared .lt-sentinel socle) ============ */
.spin {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--line-2);
  border-top-color: var(--accent);
  animation: spin 0.7s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }
}

/* ============ SKELETON ============ */
.st-row--skel {
  cursor: default;
}
.sk {
  display: inline-block;
  background: var(--surface-2);
  border-radius: var(--r-xs);
  animation: st-pulse 1.4s ease-in-out infinite;
  animation-delay: calc(var(--i, 0) * 0.12s);
}
.sk-play {
  width: 30px;
  height: 30px;
  border-radius: 50%;
}
.sk-art {
  width: 44px;
  height: 44px;
  flex: none;
  border-radius: var(--r-sm);
  background: var(--surface-3);
}
.sk-line {
  height: 10px;
}
.sk-line--title {
  width: 60%;
  background: var(--surface-3);
}
.sk-line--sub {
  width: 38%;
}
.sk-line--tag {
  width: 88px;
  height: 18px;
  border-radius: var(--r-pill);
}
.sk-line--num {
  width: 40px;
}
.sk-round {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  margin: 0 var(--space-05);
}
@keyframes st-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

/* ============ EMPTY STATES ============ */
.st-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-15x) var(--page-px);
  text-align: center;
}
.st-empty-ic {
  width: 30px;
  height: 30px;
  color: var(--ink-3);
}
.st-empty-title {
  margin: 0;
  font: 600 var(--fs-md) / 1.3 var(--font-ui);
  color: var(--ink);
}
.st-empty-sub {
  margin: 0;
  max-width: 44ch;
  font: 400 var(--fs-sm) / 1.5 var(--font-ui);
  color: var(--ink-2);
}
.st-empty .btn {
  margin-top: var(--space-2);
}

/* ============ ADD MODAL ============ */
/* Overlay + card + head + close button now live in the shared AddModal
   component; only the Sets-specific body (tabs + panels) is styled here. */

/* Tabs (underlined, distinct from the head SegFilter) */
.st-tabs {
  display: flex;
  gap: var(--space-5);
  border-bottom: 1px solid var(--line);
}
.st-tab {
  border: 0;
  background: transparent;
  cursor: pointer;
  font: 600 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  padding: 0 var(--space-05) var(--space-25);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.12s;
}
.st-tab:hover {
  color: var(--ink-2);
}
.st-tab.on {
  color: var(--ink);
  border-bottom-color: var(--accent);
}
.st-tabpanel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* Search tab */
.st-search-row {
  display: flex;
  gap: var(--space-2);
}
.st-tid-search {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  cursor: text;
}
.st-tid-search:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.st-tid-search svg {
  width: 15px;
  height: 15px;
  flex: none;
  color: var(--ink-3);
}
.st-tid-search input {
  border: 0;
  background: transparent;
  outline: none;
  width: 100%;
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
}
.st-tid-search input::placeholder {
  color: var(--ink-3);
}
.st-search-row .btn {
  height: 44px;
  flex: none;
}
.st-tid-count {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.st-results {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  overflow-y: auto;
}
.st-res {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-05);
  border-bottom: 1px solid var(--line);
}
.st-res:last-child {
  border-bottom: 0;
}
.st-res-art {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: var(--r-xs);
  overflow: hidden;
  background: var(--surface-3);
  display: grid;
  place-items: center;
}
.st-res-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.st-res-ini {
  font: 600 var(--fs-base) var(--font-ui);
  color: var(--ink-3);
  text-transform: uppercase;
}
.st-res-tx {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.st-res-title {
  font: 600 var(--fs-sm) var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.st-res-meta {
  font: 500 var(--fs-xs) / 1.4 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.st-res .btn {
  flex: none;
}
.st-res-done {
  flex: none;
  font: 600 var(--fs-sm) / 1 var(--font-ui);
  color: var(--pos-ink);
  white-space: nowrap;
}

/* URL tab */
.st-field-label {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.st-input {
  height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
  outline: none;
}
.st-input--mono {
  font-family: var(--font-mono);
}
.st-input::placeholder {
  color: var(--ink-3);
}
.st-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.st-input.is-error {
  border-color: var(--neg);
}
.st-field-help {
  margin: 0;
  font: 400 var(--fs-xs) / 1.4 var(--font-ui);
  color: var(--ink-3);
}
.st-url-go {
  align-self: flex-start;
}
.st-form-error {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  margin: 0;
  font: 500 var(--fs-sm) / 1.3 var(--font-mono);
  color: var(--neg-ink);
}
.st-form-error svg {
  width: 15px;
  height: 15px;
  flex: none;
}

/* ============ RESPONSIVE — column drop ============ */
/* The Add modal stays centered on mobile: Sets does not pass AddModal's
   `bottom-sheet` prop, so it keeps the default centered card and the BottomNav
   never masks it. */
@container (max-width: 999px) {
  .st-table {
    --st-grid: 44px minmax(0, 1fr) 190px 104px 72px 80px;
  }
  .col-dur {
    display: none;
  }
}
@container (max-width: 859px) {
  .st-table {
    --st-grid: 44px minmax(0, 1fr) 104px 72px 80px;
  }
  .col-genre {
    display: none;
  }
  .st-genre-fold {
    display: flex;
  }
}
@container (max-width: 699px) {
  .st-table {
    --st-grid: 44px minmax(0, 1fr) 72px 80px;
  }
  .col-date {
    display: none;
  }
}
@container (max-width: 639px) {
  .st-table {
    --st-grid: 40px minmax(0, 1fr) 46px 84px;
    --st-gap: var(--space-2);
  }
  .st-thead,
  .st-row {
    padding-inline: var(--page-px-mobile);
  }
  .st-head {
    padding: var(--space-4) var(--page-px-mobile) var(--space-3);
  }
  .st-controls {
    padding: 0 var(--page-px-mobile) var(--space-3);
  }
  .st-sentinel,
  .st-empty {
    padding-inline: var(--page-px-mobile);
  }
  /* Touch: play always visible. */
  .pbtn {
    opacity: 1;
  }
}
</style>
