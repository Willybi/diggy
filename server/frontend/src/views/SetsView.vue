<template>
  <div class="st-page">
    <!-- ── Head : identity + counter + search + avis filter + add ── -->
    <header class="page-head st-head">
      <div class="titles">
        <h1>Sets</h1>
        <div class="st-sub">
          <template v-if="isOpinionMode"
            >{{ fmtNum(baseTotal) }} sets<span class="st-sub-muted">
              · {{ fmtNum(total) }} {{ avisLabel }}</span
            ></template
          >
          <template v-else>{{ fmtNum(total) }} {{ pl(total, 'set', 'sets') }}</template>
        </div>
      </div>
      <div class="head-tools">
        <SearchBox
          v-model="search"
          placeholder="Rechercher un set…"
          @update:modelValue="runFetch(true)"
        />
        <SegFilter
          v-model="mode"
          :options="[
            { value: 'all', label: 'Tous' },
            { value: 'liked', label: 'Liked', cls: 'liked' },
            { value: 'disliked', label: 'Disliked', cls: 'disliked' },
            { value: 'unrated', label: 'À explorer' },
          ]"
        />
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
      </div>
    </header>

    <!-- ── Table : shared grid header/rows, infinite scroll ── -->
    <section class="st-table" aria-label="Liste des sets">
      <div v-if="showSkeleton || items.length" class="st-thead">
        <button
          class="st-th st-th--btn col-set"
          :class="{ 'is-sorted': sortKey === 'title' }"
          type="button"
          @click="toggleSort('title')"
        >
          Set<span v-if="sortKey === 'title'" class="st-arr">{{ arrow }}</span>
        </button>
        <span class="st-th col-genre">Genre</span>
        <button
          class="st-th st-th--btn col-date"
          :class="{ 'is-sorted': sortKey === 'date' }"
          type="button"
          @click="toggleSort('date')"
        >
          Date<span v-if="sortKey === 'date'" class="st-arr">{{ arrow }}</span>
        </button>
        <button
          class="st-th st-th--btn st-th--center col-tracks"
          :class="{ 'is-sorted': sortKey === 'tracks' }"
          type="button"
          @click="toggleSort('tracks')"
        >
          Tracks<span v-if="sortKey === 'tracks'" class="st-arr">{{ arrow }}</span>
        </button>
        <button
          class="st-th st-th--btn st-th--right col-dur"
          :class="{ 'is-sorted': sortKey === 'duration' }"
          type="button"
          @click="toggleSort('duration')"
        >
          Durée<span v-if="sortKey === 'duration'" class="st-arr">{{ arrow }}</span>
        </button>
        <span class="st-th st-th--center col-avis">Avis</span>
      </div>

      <!-- Loading skeleton : 8 ghost rows in the exact grid -->
      <div v-if="showSkeleton" class="st-body" aria-hidden="true">
        <div v-for="i in 8" :key="i" class="st-row st-row--skel" :style="{ '--i': i - 1 }">
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
          Aucun set ne correspond à « {{ search.trim() }} ». Vérifie l’orthographe ou élargis ta
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
          class="st-row"
          :class="{
            liked: opinionOf(s.id) === 'liked',
            disliked: opinionOf(s.id) === 'disliked',
          }"
          @click="goToSet(s.id)"
        >
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
      <div ref="sentinel" class="st-sentinel" :class="{ on: hasMore }">
        <span class="spin"></span>Chargement…
      </div>
    </section>

    <!-- ── Add modal (2 tabs) ── -->
    <div v-if="showAdd" class="st-overlay" @click.self="closeAdd">
      <div class="st-modal" role="dialog" aria-modal="true" aria-label="Ajouter un set">
        <div class="st-modal-head">
          <h2 class="st-modal-title">Ajouter un set</h2>
          <button class="st-modal-x" type="button" aria-label="Fermer" @click="closeAdd">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              aria-hidden="true"
            >
              <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
            </svg>
          </button>
        </div>

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
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useOpinionsStore } from '../stores/opinions.js'
import { usePaginatedList } from '../composables/usePaginatedList.js'
import { fmtMs, fmtDate, fmtNum, pl } from '../utils/format'
import Artwork from '../components/Artwork.vue'
import ArtistLinks from '../components/ArtistLinks.vue'
import StyleTag from '../components/StyleTag.vue'
import ScoreRing from '../components/ScoreRing.vue'
import LikeDislike from '../components/LikeDislike.vue'
import SearchBox from '../components/SearchBox.vue'
import SegFilter from '../components/SegFilter.vue'

const router = useRouter()
const opinions = useOpinionsStore()

// ── Filters / sort ──
const search = ref('')
const mode = ref('all')
const sortKey = ref('date') // title | date | tracks | duration
const sortDir = ref('desc') // asc | desc
const baseTotal = ref(0) // last unfiltered (all-mode) total, for the head sub-count

// Composite sort sent server-side: leading '-' = descending.
const sortParam = computed(() => (sortDir.value === 'desc' ? '-' : '') + sortKey.value)

// ── Paginated list (shared trunk) ──
const { items, total, loading, hasMore, sentinel, fetch } = usePaginatedList({
  endpoint: '/api/sets/',
  pageSize: 24,
  sort: () => sortParam.value,
  query: () => search.value,
})

const arrow = computed(() => (sortDir.value === 'asc' ? '↑' : '↓'))
const isOpinionMode = computed(() => mode.value !== 'all')
const hasSearch = computed(() => search.value.trim().length > 0)
const showSkeleton = computed(() => loading.value && !items.value.length)
const isEmpty = computed(() => !loading.value && !items.value.length)

const avisLabel = computed(() => {
  if (mode.value === 'liked') return 'likés'
  if (mode.value === 'disliked') return 'dislikés'
  if (mode.value === 'unrated') return 'à explorer'
  return ''
})

const emptyAvis = computed(() => {
  const map = {
    liked: { title: 'Aucun set liké', sub: 'Tu n’as encore liké aucun set.' },
    disliked: { title: 'Aucun set disliké', sub: 'Tu n’as encore disliké aucun set.' },
    unrated: { title: 'Aucun set à explorer', sub: 'Tous tes sets ont déjà un avis.' },
  }
  return map[mode.value] || { title: 'Aucun set', sub: '' }
})

function opinionOf(id) {
  return opinions.get('set', id)
}

// ── Fetch orchestration ──
// `all` goes through the shared paginated list (infinite scroll). The opinion
// filters resolve their id set from the opinions store in ONE non-paginated shot
// (like ArtistsView) and write the shared refs directly: liked/disliked pass the
// matching ids via `ids=`, unrated excludes every rated id via `exclude_ids=`.
async function runFetch(reset = true) {
  if (!isOpinionMode.value) {
    await fetch(reset)
    baseTotal.value = total.value
    return
  }
  if (!reset) return // opinion filters are not paginated (sentinel stays off)
  items.value = []
  loading.value = true
  try {
    await opinions.load()
    const setOps = opinions.data.set || {}
    const params = { sort: sortParam.value, limit: 200, offset: 0 }
    const q = search.value.trim()
    if (q) params.q = q

    if (mode.value === 'unrated') {
      const ratedIds = Object.keys(setOps).filter(
        (k) => setOps[k] === 'liked' || setOps[k] === 'disliked',
      )
      if (ratedIds.length) params.exclude_ids = ratedIds.join(',')
    } else {
      const matchingIds = Object.entries(setOps)
        .filter(([, v]) => v === mode.value)
        .map(([k]) => k)
      if (!matchingIds.length) {
        items.value = []
        total.value = 0
        hasMore.value = false
        return
      }
      params.ids = matchingIds.join(',')
    }

    const { data } = await api.get('/api/sets/', { params })
    items.value = data.items
    total.value = data.total
    hasMore.value = false
  } catch {
    items.value = []
    total.value = 0
    hasMore.value = false
  } finally {
    loading.value = false
  }
}

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'title' ? 'asc' : 'desc'
  }
}

function clearSearch() {
  search.value = ''
  runFetch(true)
}

function goToSet(id) {
  router.push(`/set/${id}`)
}

async function setOpinion(id, val) {
  // Optimistic store update; the row recolors reactively via opinionOf().
  await opinions.set('set', id, val)
}

// Mode / sort changes reload from the server.
watch([mode, sortKey, sortDir], () => runFetch(true))

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

function closeAdd() {
  showAdd.value = false
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

function onKeydown(e) {
  if (e.key === 'Escape' && showAdd.value) closeAdd()
}

onMounted(() => {
  runFetch(true)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
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
  color: var(--ink-2);
}
.st-sub-muted {
  color: var(--ink-3);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.head-tools :deep(.search) {
  flex: 1 1 200px;
  max-width: 320px;
  min-width: 200px;
}
.st-add {
  flex: none;
}

/* ============ TABLE — shared grid header/rows ============ */
.st-table {
  --st-grid: minmax(0, 1fr) 190px 104px 72px 92px 80px;
  --st-gap: var(--space-3);
  padding-bottom: var(--space-8);
}
.st-thead,
.st-row {
  display: grid;
  grid-template-columns: var(--st-grid);
  gap: var(--st-gap);
  align-items: center;
  padding-inline: var(--page-px);
}
.st-thead {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 36px;
  background: var(--bg);
  border-bottom: 1px solid var(--line-2);
}
.st-th {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  text-align: left;
  user-select: none;
}
.st-th--btn {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  transition: color 0.12s;
}
.st-th--btn:hover {
  color: var(--ink-2);
}
.st-th--btn.is-sorted {
  color: var(--accent-ink);
}
.st-th--btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.st-th--center {
  text-align: center;
}
.st-th--right {
  text-align: right;
}
.st-arr {
  margin-left: var(--space-05);
  color: var(--accent-ink);
}

/* ============ ROWS ============ */
.st-row {
  min-height: var(--row-h);
  padding-block: var(--space-2);
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  transition: background 0.12s;
}
.st-row:hover {
  background: var(--surface-2);
}
.st-row.liked {
  background: var(--pos-wash);
}
.st-row.liked:hover {
  background: var(--pos-wash-2);
}
[data-theme='dark'] .st-row.liked {
  background: var(--pos-wash-2);
}
.st-row.disliked > .st-cell:not(.st-cell--avis) {
  opacity: 0.45;
  transition: opacity 0.16s;
}
.st-row.disliked:hover > .st-cell:not(.st-cell--avis) {
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

/* ============ SENTINEL ============ */
.st-sentinel {
  display: none;
  align-items: center;
  justify-content: center;
  gap: var(--space-25);
  padding: var(--space-4) var(--page-px) var(--space-2);
  color: var(--ink-3);
  font: 500 var(--fs-xs) / 1 var(--font-mono);
}
.st-sentinel.on {
  display: flex;
}
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
.st-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--overlay-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6);
}
.st-modal {
  width: min(460px, 100vw - 32px);
  max-height: min(88vh, 720px);
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.st-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.st-modal-title {
  margin: 0;
  font: 700 var(--fs-md) / 1.2 var(--font-ui);
  color: var(--ink);
}
.st-modal-x {
  width: 30px;
  height: 30px;
  flex: none;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
}
.st-modal-x:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.st-modal-x svg {
  width: 16px;
  height: 16px;
}

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
@container (max-width: 999px) {
  .st-table {
    --st-grid: minmax(0, 1fr) 190px 104px 72px 80px;
  }
  .col-dur {
    display: none;
  }
}
@container (max-width: 859px) {
  .st-table {
    --st-grid: minmax(0, 1fr) 104px 72px 80px;
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
    --st-grid: minmax(0, 1fr) 72px 80px;
  }
  .col-date {
    display: none;
  }
}
@container (max-width: 639px) {
  .st-table {
    --st-grid: minmax(0, 1fr) 46px 84px;
    --st-gap: var(--space-2);
  }
  .st-thead,
  .st-row {
    padding-inline: var(--page-px-mobile);
  }
  .st-head {
    padding: var(--space-4) var(--page-px-mobile) var(--space-3);
  }
  .head-tools {
    width: 100%;
    margin-left: 0;
  }
  .head-tools :deep(.search) {
    flex: 1 1 100%;
    max-width: none;
  }
  .st-sentinel,
  .st-empty {
    padding-inline: var(--page-px-mobile);
  }
  /* Ring keeps the arc, drops the « N % » label on narrow screens (S3). */
  .col-tracks :deep(.sr-note) {
    display: none;
  }
}

/* Bottom-sheet Add modal on mobile (fixed → @media, not @container). */
@media (max-width: 640px) {
  .st-overlay {
    align-items: flex-end;
    padding: 0;
  }
  .st-modal {
    width: 100%;
    max-width: none;
    max-height: 90vh;
    border-radius: var(--r-xl) var(--r-xl) 0 0;
    padding: var(--space-5) var(--page-px-mobile) var(--space-6);
  }
}
</style>
