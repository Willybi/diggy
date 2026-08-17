<template>
  <div class="pl-page">
    <!-- ── Head : identity + counter + avis filter + add (no search on this page) ── -->
    <header class="page-head pl-head">
      <div class="titles">
        <h1>Playlists</h1>
        <div class="pl-sub">
          <template v-if="isOpinionMode"
            >{{ fmtNum(baseTotal) }} playlists<span class="pl-sub-muted">
              · {{ fmtNum(total) }} {{ avisLabel }}</span
            ><span v-if="capped" class="pl-cap-note"> · 200 premiers affichés</span></template
          >
          <template v-else>{{ fmtNum(total) }} {{ pl(total, 'playlist', 'playlists') }}</template>
        </div>
      </div>
      <div class="head-tools">
        <SegFilter
          v-model="mode"
          :options="[
            { value: 'all', label: 'Toutes' },
            { value: 'liked', label: 'Liked', cls: 'liked' },
            { value: 'disliked', label: 'Disliked', cls: 'disliked' },
            { value: 'unrated', label: 'À explorer' },
          ]"
        />
        <button class="btn btn--accent pl-add" type="button" @click="openAdd">
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

    <!-- ── Contextual genre filter (D8) : removable chip, landed from Genre Detail ── -->
    <div v-if="genreFilter" class="pl-filter-row">
      <FilterChip label="Style" :value="genreFilter" @remove="clearGenre" />
    </div>

    <!-- ── Table : shared grid header/rows, infinite scroll ── -->
    <section class="pl-table" aria-label="Liste des playlists surveillées">
      <div v-if="showSkeleton || items.length" class="pl-thead lt-thead">
        <button
          class="pl-th pl-th--btn col-pl lt-th lt-th--btn"
          :class="{ 'is-sorted': sortKey === 'title' }"
          type="button"
          @click="toggleSort('title')"
        >
          Playlist<span v-if="sortKey === 'title'" class="pl-arr">{{ arrow }}</span>
        </button>
        <span class="pl-th col-genre lt-th">Genre</span>
        <button
          class="pl-th pl-th--btn col-creator lt-th lt-th--btn"
          :class="{ 'is-sorted': sortKey === 'creator' }"
          type="button"
          @click="toggleSort('creator')"
        >
          Créateur<span v-if="sortKey === 'creator'" class="pl-arr">{{ arrow }}</span>
        </button>
        <button
          class="pl-th pl-th--btn pl-th--right col-tracks lt-th lt-th--btn lt-th--right"
          :class="{ 'is-sorted': sortKey === 'tracks' }"
          type="button"
          @click="toggleSort('tracks')"
        >
          Tracks<span v-if="sortKey === 'tracks'" class="pl-arr">{{ arrow }}</span>
        </button>
        <button
          class="pl-th pl-th--btn col-crawl lt-th lt-th--btn"
          :class="{ 'is-sorted': sortKey === 'crawl' }"
          type="button"
          @click="toggleSort('crawl')"
        >
          Dernier crawl<span v-if="sortKey === 'crawl'" class="pl-arr">{{ arrow }}</span>
        </button>
        <span class="pl-th pl-th--center col-avis lt-th lt-th--center">Avis</span>
      </div>

      <!-- Loading skeleton : 8 ghost rows in the exact grid -->
      <div v-if="showSkeleton" class="pl-body" aria-hidden="true">
        <div v-for="i in 8" :key="i" class="pl-row pl-row--skel lt-row" :style="{ '--i': i - 1 }">
          <div class="pl-cell col-pl pl-cell--pl">
            <span class="sk sk-art"></span>
            <div class="pl-tx">
              <span class="sk sk-line sk-line--title"></span>
              <span class="sk sk-line sk-line--sub"></span>
            </div>
          </div>
          <div class="pl-cell col-genre"><span class="sk sk-line sk-line--tag"></span></div>
          <div class="pl-cell col-creator"><span class="sk sk-line sk-line--sub"></span></div>
          <div class="pl-cell col-tracks pl-cell--right">
            <span class="sk sk-line sk-line--num"></span>
          </div>
          <div class="pl-cell col-crawl">
            <span class="sk sk-line sk-line--num"></span>
            <span class="sk sk-line sk-line--tag"></span>
          </div>
          <div class="pl-cell col-avis pl-cell--center">
            <span class="sk sk-round"></span><span class="sk sk-round"></span>
          </div>
        </div>
      </div>

      <!-- Empty : avis filter with no match (adapted copy, no action) -->
      <div v-else-if="isEmpty && isOpinionMode" class="pl-empty">
        <svg
          class="pl-empty-ic"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
        </svg>
        <p class="pl-empty-title">{{ emptyAvis.title }}</p>
        <p class="pl-empty-sub">{{ emptyAvis.sub }}</p>
      </div>

      <!-- Empty : generic fallback -->
      <div v-else-if="isEmpty" class="pl-empty">
        <svg
          class="pl-empty-ic"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
        </svg>
        <p class="pl-empty-title">Aucune playlist à afficher</p>
      </div>

      <!-- Rows -->
      <div v-else class="pl-body">
        <div
          v-for="p in items"
          :key="p.id"
          class="pl-row lt-row"
          :class="{
            liked: opinionOf(p.id) === 'liked',
            disliked: opinionOf(p.id) === 'disliked',
          }"
          @click="goToPlaylist(p.id)"
        >
          <!-- Playlist : cover + title + source glyph (+ folded genre/crawl below xs) -->
          <div class="pl-cell col-pl pl-cell--pl">
            <Artwork
              size="row"
              :src="p.has_artwork ? `/storage/playlist-artworks/${p.id}.jpg` : undefined"
              :alt="p.title || p.external_id"
            />
            <div class="pl-tx">
              <div class="pl-title-row">
                <span class="pl-title">{{ p.title || p.external_id }}</span>
                <PlatformLink :platform="p.source || 'deezer'" variant="glyph" />
              </div>

              <!-- Genre chips fold under the title below 880px (P1) -->
              <div v-if="p.top_genres.length" class="pl-genre-fold">
                <RouterLink
                  v-for="g in p.top_genres.slice(0, 2)"
                  :key="g.name"
                  class="pl-style-link"
                  :to="`/style/${encodeURIComponent(g.name)}`"
                  @click.stop
                >
                  <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
                </RouterLink>
              </div>

              <!-- Crawl meta folds under the title below 720px (P12) -->
              <div class="pl-crawl-fold">
                <span class="pl-crawl-fold-date">{{ crawlShort(p) }}</span>
              </div>
            </div>
          </div>

          <!-- Genre : 1–2 StyleTag (P1) -->
          <div class="pl-cell col-genre pl-cell--genre">
            <template v-if="p.top_genres.length">
              <RouterLink
                v-for="g in p.top_genres.slice(0, 2)"
                :key="g.name"
                class="pl-style-link"
                :to="`/style/${encodeURIComponent(g.name)}`"
                @click.stop
              >
                <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
              </RouterLink>
            </template>
          </div>

          <!-- Créateur : owner, non-clickable (P3) -->
          <div class="pl-cell col-creator">
            <span v-if="p.owner" class="pl-creator">{{ p.owner }}</span>
          </div>

          <!-- Tracks : raw count, right-aligned (P8) -->
          <div class="pl-cell col-tracks pl-cell--right">
            <span v-if="p.track_count != null" class="pl-num">{{ p.track_count }}</span>
            <span v-else class="pl-null">—</span>
          </div>

          <!-- Dernier crawl : single centered line — date/status left, Crawl button right (P4–P7) -->
          <div class="pl-cell col-crawl pl-crawl" @click.stop>
            <div class="pl-crawl-l1">
              <span v-if="crawlStatus[p.id]" class="pl-live" :class="crawlStatus[p.id]">
                <span class="pl-live-dot"></span>
                <span class="pl-live-lbl">{{ liveLabel(crawlStatus[p.id]) }}</span>
              </span>
              <span v-else class="pl-date" :class="{ 'pl-null': !p.last_crawled_at }">{{
                fmtCrawled(p.last_crawled_at)
              }}</span>
            </div>
            <div class="pl-crawl-l2">
              <template v-if="!crawlStatus[p.id]">
                <button
                  v-if="!isCooldown(p)"
                  class="btn btn--sm pl-crawl-btn"
                  type="button"
                  @click.stop="triggerCrawl(p)"
                >
                  Crawl
                </button>
                <span v-else class="pl-cooldown" title="Réessaie dans quelques heures"
                  >cooldown 12 h</span
                >
              </template>
            </div>
          </div>

          <!-- Avis (P) -->
          <div class="pl-cell col-avis pl-cell--avis" @click.stop>
            <LikeDislike
              :model-value="opinionOf(p.id)"
              @update:model-value="(v) => setOpinion(p.id, v)"
            />
          </div>
        </div>
      </div>

      <!-- Sentinel (infinite scroll) — always in DOM so the observer attaches -->
      <div ref="sentinel" class="pl-sentinel lt-sentinel" :class="{ on: hasMore }">
        <span class="spin"></span>Chargement…
      </div>
    </section>

    <!-- ── Add modal (single URL field) — shared chrome via AddModal ── -->
    <AddModal v-model:open="showAdd" title="Ajouter une playlist" bottom-sheet>
      <div class="pl-tabpanel">
        <label class="pl-field-label" for="pl-url-input">URL de la playlist</label>
        <input
          id="pl-url-input"
          v-model="inputValue"
          class="pl-input pl-input--mono"
          :class="{ 'is-error': formError }"
          type="text"
          placeholder="https://www.deezer.com/playlist/…"
          @keydown.enter="addPlaylist"
          @input="onUrlInput"
        />
        <p class="pl-field-help">
          Colle l’URL d’une playlist Deezer, Tidal ou Spotify. Elle est crawlée dès l’ajout et
          alimente le radar.
        </p>
        <p v-if="formError" class="pl-form-error">
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
          class="btn btn--accent pl-url-go"
          type="button"
          :disabled="adding"
          @click="addPlaylist"
        >
          {{ adding ? 'Ajout…' : 'Ajouter' }}
        </button>
      </div>
    </AddModal>
  </div>
</template>

<script setup>
import { ref, computed, watch, reactive, onMounted, onActivated, onDeactivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useOpinionsStore } from '../stores/opinions.js'
import { usePaginatedList } from '../composables/usePaginatedList.js'
import { useOpinionOneShot } from '../composables/useOpinionOneShot.js'
import { useUrlSync } from '../composables/useUrlSync.js'
import { useScrollRestore } from '../composables/useScrollRestore.js'
import { useTaskPoll } from '../composables/useTaskPoll.js'
import { fmtNum, pl } from '../utils/format'
import Artwork from '../components/Artwork.vue'
import PlatformLink from '../components/PlatformLink.vue'
import StyleTag from '../components/StyleTag.vue'
import LikeDislike from '../components/LikeDislike.vue'
import SegFilter from '../components/SegFilter.vue'
import AddModal from '../components/AddModal.vue'
import FilterChip from '../components/filters/FilterChip.vue'

// Explicit name so <KeepAlive :include> in App.vue matches this cached listing.
defineOptions({ name: 'WatchlistView' })

const route = useRoute()
const router = useRouter()
const opinions = useOpinionsStore()

const COOLDOWN_MS = 12 * 3600 * 1000
const DAY_MS = 86400000

// ── Filters / sort ──
const mode = ref('all')
const sortKey = ref('title') // title | creator | tracks | crawl
const sortDir = ref('asc') // asc | desc
const baseTotal = ref(0) // last unfiltered (all-mode) total, for the head sub-count
// D8: contextual genre filter (raw name), URL-synced, landed from Genre Detail's
// « Voir les N autres » shelf renvoi. No picker on this page — the chip is
// removable and the only way in is the /playlists?genre= link.
const genreFilter = ref('')

// Composite sort sent server-side: leading '-' = descending.
const sortParam = computed(() => (sortDir.value === 'desc' ? '-' : '') + sortKey.value)

// Filters ↔ URL so a back-return restores them (before the refetch watchers so
// the initial hydrate doesn't trigger a spurious fetch).
useUrlSync(
  [
    { ref: sortKey, param: 'sort', default: 'title' },
    { ref: sortDir, param: 'dir', default: 'asc' },
    { ref: mode, param: 'avis', default: 'all' },
    { ref: genreFilter, param: 'genre', default: '' },
  ],
  { router, route },
)

// ── Paginated list (shared trunk, infinite scroll) ──
const { items, total, loading, hasMore, sentinel, fetch, fetchUpTo } = usePaginatedList({
  endpoint: '/api/watchlist/browse',
  pageSize: 24,
  sort: () => sortParam.value,
  extraParams: () => (genreFilter.value ? { genres: genreFilter.value } : undefined),
})

// Scroll restoration on a back/forward return. The grid scrolls inside
// .app-main (#main-content); on return we reload the rows in one burst
// (fetchUpTo) then re-apply the offset. Opinion facets are not paginated —
// they reload wholesale through the runFetch wrapper.
const scrollRestore = useScrollRestore({
  scroller: () => document.getElementById('main-content'),
  getCount: () => items.value.length,
})

const arrow = computed(() => (sortDir.value === 'asc' ? '↑' : '↓'))
const isOpinionMode = computed(() => mode.value !== 'all')
const showSkeleton = computed(() => loading.value && !items.value.length)
const isEmpty = computed(() => !loading.value && !items.value.length)

const avisLabel = computed(() => {
  if (mode.value === 'liked') return 'likées'
  if (mode.value === 'disliked') return 'dislikées'
  if (mode.value === 'unrated') return 'à explorer'
  return ''
})

const emptyAvis = computed(() => {
  const map = {
    liked: {
      title: 'Aucune playlist likée',
      sub: 'Tu n’as encore liké aucune playlist surveillée.',
    },
    disliked: {
      title: 'Aucune playlist dislikée',
      sub: 'Tu n’as encore disliké aucune playlist surveillée.',
    },
    unrated: {
      title: 'Aucune playlist à explorer',
      sub: 'Toutes tes playlists surveillées ont déjà un avis.',
    },
  }
  return map[mode.value] || { title: 'Aucune playlist', sub: '' }
})

function opinionOf(id) {
  return opinions.get('playlist', id)
}

// ── Opinion one-shot (avis facets) : shared helper (mirrors SetsView) ──
// liked/disliked pass the matching ids via `ids=`, unrated excludes every rated
// id via `exclude_ids=`. `capped` flags a truncated one-shot (limit 200) so the
// head can show « 200 premiers affichés ».
const opinionOneShot = useOpinionOneShot({
  endpoint: '/api/watchlist/browse',
  kind: 'playlist',
  refs: { items, total, hasMore, loading },
  unratedValue: 'unrated',
  buildParams: () => {
    const p = { sort: sortParam.value, limit: 200, offset: 0 }
    if (genreFilter.value) p.genres = genreFilter.value
    return p
  },
})
const { capped } = opinionOneShot

// ── Fetch orchestration (mirrors SetsView) ──
// `all` goes through the shared paginated list (infinite scroll). The opinion
// filters go through the one-shot helper (sentinel stays off).
async function runFetch(reset = true) {
  if (!isOpinionMode.value) {
    await fetch(reset)
    baseTotal.value = total.value
    return
  }
  if (!reset) return // opinion filters are not paginated (sentinel stays off)
  await opinionOneShot.run(mode.value)
}

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    // Alphabetical dimensions open ascending; magnitudes/dates open descending.
    sortDir.value = key === 'title' || key === 'creator' ? 'asc' : 'desc'
  }
}

function goToPlaylist(id) {
  router.push(`/playlists/${id}`)
}

function clearGenre() {
  genreFilter.value = ''
}

async function setOpinion(id, val) {
  // Optimistic store update; the row recolors reactively via opinionOf().
  await opinions.set('playlist', id, val)
}

// Mode / sort / genre changes reload from the server.
watch([mode, sortKey, sortDir, genreFilter], () => runFetch(true))

// ── Crawl live status (one keyed poll per playlist id) ──
const crawlStatus = reactive({}) // id → 'queued' | 'running' | 'done'

const crawlPoll = useTaskPoll((id) => `/api/watchlist/${id}/crawl-status`, {
  intervalMs: 4000,
  async onData(data, { key: id, stop }) {
    if (data.status === 'done') {
      stop()
      crawlStatus[id] = 'done'
      stampCrawled(id)
      setTimeout(() => {
        delete crawlStatus[id]
      }, 3000)
    } else if (!data.status) {
      stop()
      delete crawlStatus[id]
      stampCrawled(id)
    } else {
      crawlStatus[id] = data.status
    }
  },
  onError(_err, { key: id }) {
    delete crawlStatus[id]
  },
})

// Reflect a finished crawl on the loaded row without a disruptive full refetch:
// stamp "just now" (→ "aujourd'hui" + 12h cooldown) and clear the active-task flag.
function stampCrawled(id) {
  const item = items.value.find((p) => p.id === id)
  if (item) {
    item.last_crawled_at = new Date().toISOString()
    item.current_task_id = null
  }
}

function startPolling(id) {
  if (!crawlStatus[id]) crawlStatus[id] = 'queued'
  crawlPoll.start(id)
}

// Attach a poll to any freshly loaded row that already has a crawl in flight.
function syncPolls() {
  for (const p of items.value) {
    if (p.current_task_id && !crawlPoll.isActive(p.id)) {
      crawlStatus[p.id] = 'queued'
      crawlPoll.start(p.id)
    }
  }
}
watch(() => items.value.length, syncPolls)

function isCooldown(p) {
  if (!p.last_crawled_at) return false
  return Date.now() - new Date(p.last_crawled_at).getTime() < COOLDOWN_MS
}

function liveLabel(status) {
  if (status === 'running') return 'En cours'
  if (status === 'done') return 'Crawlé'
  return 'En attente'
}

async function triggerCrawl(p) {
  crawlStatus[p.id] = 'queued'
  try {
    await api.post(`/api/watchlist/${p.id}/crawl`)
    startPolling(p.id)
  } catch (e) {
    // 429 = cooldown still active server-side: reflect it locally (hide the button).
    if (e.response?.status === 429) p.last_crawled_at = new Date().toISOString()
    delete crawlStatus[p.id]
  }
}

// ── Relative crawl date (L1) + compact fold token ──
function crawlDays(iso) {
  return Math.floor((Date.now() - new Date(iso).getTime()) / DAY_MS)
}

function fmtCrawled(iso) {
  if (!iso) return 'jamais'
  const days = crawlDays(iso)
  if (days <= 0) return "aujourd'hui"
  if (days === 1) return 'il y a 1 j'
  return `il y a ${days} j`
}

// Compact crawl token for the folded mobile meta (< 720px).
function crawlShort(p) {
  const live = crawlStatus[p.id]
  if (live === 'running') return 'crawl en cours'
  if (live === 'queued') return 'crawl en attente'
  if (live === 'done') return 'crawlé'
  if (!p.last_crawled_at) return 'jamais crawlée'
  const days = crawlDays(p.last_crawled_at)
  if (days <= 0) return 'crawl auj.'
  return `crawl ${days} j`
}

// ── Add modal ──
const showAdd = ref(false)
const inputValue = ref('')
const formError = ref('')
const adding = ref(false)

function openAdd() {
  showAdd.value = true
  inputValue.value = ''
  formError.value = ''
}

function onUrlInput() {
  formError.value = ''
}

function parsePlaylistInput(input) {
  const s = input.trim()
  let match = s.match(/deezer\.com\/.*playlist\/(\d+)/)
  if (match) return { external_id: match[1], source: 'deezer' }
  match = s.match(/tidal\.com\/(?:browse\/)?playlist\/([a-f0-9-]+)/i)
  if (match) return { external_id: match[1], source: 'tidal' }
  match = s.match(/open\.spotify\.com\/playlist\/([a-zA-Z0-9]+)/)
  if (match) return { external_id: match[1], source: 'spotify' }
  if (/^\d+$/.test(s)) return { external_id: s, source: 'deezer' }
  if (/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(s))
    return { external_id: s, source: 'tidal' }
  return null
}

async function addPlaylist() {
  formError.value = ''
  const parsed = parsePlaylistInput(inputValue.value)
  if (!parsed) {
    formError.value = 'URL non reconnue — colle un lien de playlist Deezer, Tidal ou Spotify.'
    return
  }
  adding.value = true
  try {
    const { data } = await api.post('/api/watchlist/', parsed)
    inputValue.value = ''
    showAdd.value = false
    await runFetch(true)
    startPolling(data.id)
  } catch (e) {
    if (e.response?.status === 409) {
      formError.value = 'Cette playlist est déjà dans ta watchlist.'
    } else {
      formError.value = 'Erreur lors de l’ajout. Réessaie.'
    }
  } finally {
    adding.value = false
  }
}

onMounted(() => {
  scrollRestore.restore({
    initialFetch: () => runFetch(true),
    hydrate: (count) => (isOpinionMode.value ? runFetch(true) : fetchUpTo(count)),
  })
})

// Under <KeepAlive> the view is deactivated (not unmounted) when we open a detail
// page, so useTaskPoll's onUnmounted cleanup never fires: the crawl-status polls
// would keep hitting the API in the background. Pause every live poll on
// deactivate and resume the same set on reactivation (the crawlStatus badges and
// loaded rows stay in memory, so the UI picks up exactly where it left off).
// reapply() re-applies the scroll offset without a refetch; the first activation
// follows onMounted and is skipped.
let firstActivate = true
let pausedPollKeys = []
onDeactivated(() => {
  pausedPollKeys = crawlPoll.activeKeys()
  crawlPoll.stop()
})
onActivated(() => {
  for (const id of pausedPollKeys) crawlPoll.start(id)
  pausedPollKeys = []
  if (firstActivate) {
    firstActivate = false
    return
  }
  scrollRestore.reapply()
})
</script>

<style scoped>
.pl-page {
  container-type: inline-size;
  container-name: pl;
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
.pl-sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm) / 1 var(--font-mono);
  color: var(--ink-2);
}
.pl-sub-muted {
  color: var(--ink-3);
}
.pl-cap-note {
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.pl-add {
  flex: none;
}

/* Contextual genre filter chip row (D8) — matches the page gutter. */
.pl-filter-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--page-px) var(--space-3);
}

/* ============ TABLE — shared grid header/rows ============ */
.pl-table {
  --pl-grid: minmax(0, 1fr) 190px 128px 64px 196px 80px;
  --pl-gap: var(--space-3);
  padding-bottom: var(--space-8);
}
/* Column track + gap are view-specific and stay here; the grid frame, sticky
   header and header-cell styling come from the shared .lt-* socle
   (assets/list-table.css). The pl-thead/pl-row/pl-th* classes remain on the
   elements alongside the lt-* ones (grid var here, base there). */
.pl-thead,
.pl-row {
  grid-template-columns: var(--pl-grid);
  gap: var(--pl-gap);
}
.pl-arr {
  margin-left: var(--space-1);
  letter-spacing: normal;
  color: var(--accent-ink);
}

/* ============ ROWS ============ */
/* Base row + hover + liked wash come from the shared .lt-row socle. Disliked
   (dimmed, sparing the avis cell) is view-specific and stays here. */
.pl-row.disliked > .pl-cell:not(.pl-cell--avis) {
  opacity: 0.45;
  transition: opacity 0.16s;
}
.pl-row.disliked:hover > .pl-cell:not(.pl-cell--avis) {
  opacity: 0.7;
}
.pl-cell {
  min-width: 0;
}
.pl-cell--center {
  display: flex;
  justify-content: center;
}
.pl-cell--right {
  text-align: right;
}
/* Optical gutter compensation (E2) : Tracks is flush-right, Dernier crawl
   flush-left, so both mono values crowd the --space-3 gutter and read as one
   block. Pad them apart → ≥ 24px of perceived whitespace between them. Applied
   on both the header and the body cells so the columns stay aligned. */
.col-tracks {
  padding-right: var(--space-2);
}
.col-crawl {
  padding-left: var(--space-2);
}

/* ============ PLAYLIST CELL ============ */
.pl-cell--pl {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
/* Local sizing of the shared Artwork (BRIEF : 44px cover, --r-sm). */
.pl-cell--pl :deep(.artwork--row) {
  width: 44px;
}
.pl-cell--pl :deep(.artwork--row .aw-frame) {
  border-radius: var(--r-sm);
}
.pl-tx {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.pl-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  min-width: 0;
}
.pl-title {
  font: 600 var(--fs-table) / 1.25 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* Source glyph: attribute of the title, never shrinks, muted (P2). */
.pl-title-row :deep(.plink--glyph) {
  flex: none;
  color: var(--ink-3);
}
.pl-row:hover .pl-title {
  color: var(--accent-ink);
}

/* Genre chips folded under the title (< 880px, P1) — hidden by default. */
.pl-genre-fold {
  display: none;
  flex-wrap: wrap;
  gap: var(--space-15);
  margin-top: var(--space-05);
}
/* Folded chip = nano variant (E5) : the desktop column keeps StyleTag's default
   --fs-sm / dot 7px; here it must not weigh as much as the title. */
.pl-genre-fold :deep(.style-tag) {
  font-size: var(--fs-nano);
  gap: var(--space-1);
  padding: var(--space-05) var(--space-15);
}
.pl-genre-fold :deep(.dot) {
  width: 5px;
  height: 5px;
}
/* Crawl meta folded under the title (< 720px, P12) — hidden by default. */
.pl-crawl-fold {
  display: none;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-05);
  min-width: 0;
}
.pl-crawl-fold-date {
  font: 500 var(--fs-table-sm) / 1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============ GENRE CELL ============ */
.pl-cell--genre {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  overflow: hidden;
}
.pl-style-link {
  text-decoration: none;
  min-width: 0;
  display: inline-flex;
}
/* The dominant chip never compresses; only the 2nd absorbs the shortfall (P1). */
.pl-cell--genre .pl-style-link:first-child {
  flex: none;
}

/* ============ CRÉATEUR ============ */
.pl-creator {
  font: 400 var(--fs-table) / 1.3 var(--font-ui);
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

/* ============ TRACKS ============ */
.pl-num {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-2);
}
.pl-null {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-3);
}

/* ============ DERNIER CRAWL (P4–P7) ============ */
/* A single row on the baseline: date/status on the left, Crawl button / cooldown
   pushed to the right. L1/L2 keep their reserved height so the button revealed on
   hover never reflows the row vertically. */
.pl-crawl {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: var(--space-2);
}
.pl-crawl .pl-crawl-l2 {
  flex: 1;
}
.pl-crawl-l1 {
  min-height: 19px;
  display: flex;
  align-items: center;
}
.pl-crawl-l2 {
  min-height: 24px;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.pl-date {
  font: 500 var(--fs-table) / 1 var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
}
.pl-date.pl-null {
  color: var(--ink-3);
}

/* Live status (P6) — replaces both date and button. */
.pl-live {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  white-space: nowrap;
}
.pl-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.pl-live-lbl {
  font: 500 var(--fs-table-sm) / 1 var(--font-ui);
}
.pl-live.queued .pl-live-dot {
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--ink-3);
}
.pl-live.queued .pl-live-lbl {
  color: var(--ink-3);
}
.pl-live.running .pl-live-dot {
  background: var(--accent);
}
.pl-live.running .pl-live-lbl {
  font-weight: 600;
  color: var(--accent-ink);
}
.pl-live.done .pl-live-dot {
  background: var(--pos);
}
.pl-live.done .pl-live-lbl {
  color: var(--pos-ink);
}
@keyframes pl-live {
  from {
    opacity: 0.35;
    transform: scale(0.8);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
@media (prefers-reduced-motion: no-preference) {
  .pl-live.running .pl-live-dot {
    animation: pl-live 1.1s ease-in-out infinite alternate;
  }
}

/* Crawl button (P5) — revealed on row hover / focus. .btn--sm shrunk to the
   reserved 24px L2 line height. */
.pl-crawl-btn {
  margin-left: auto;
  height: 24px;
  padding-inline: var(--space-25);
  font-size: var(--fs-xs);
  opacity: 0;
  transition:
    opacity 0.12s,
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.pl-row:hover .pl-crawl-btn,
.pl-crawl-btn:focus-visible {
  opacity: 1;
}
.pl-crawl-btn:hover {
  border-color: var(--accent);
  color: var(--accent-ink);
}

/* Cooldown label (P5) — replaces the button, only on hover. */
.pl-cooldown {
  margin-left: auto;
  font: 500 var(--fs-nano) / 1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.12s;
}
.pl-row:hover .pl-cooldown {
  opacity: 0.7;
}

/* ============ AVIS (shared LikeDislike, local deltas) ============ */
.pl-cell--avis {
  display: flex;
  justify-content: center;
}
.pl-cell--avis :deep(.ld-btn) {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border-color: transparent;
  background: transparent;
}
.pl-cell--avis :deep(.ld-btn:hover) {
  background: var(--surface-3);
}
.pl-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like) {
  background: var(--pos-soft);
}
.pl-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
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
.pl-row--skel {
  cursor: default;
}
.sk {
  display: inline-block;
  background: var(--surface-2);
  border-radius: var(--r-xs);
  animation: pl-pulse 1.4s ease-in-out infinite;
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
  width: 42%;
}
.sk-line--tag {
  width: 84px;
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
.pl-row--skel .pl-tx {
  gap: var(--space-15);
}
@keyframes pl-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

/* ============ EMPTY STATES ============ */
.pl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-15x) var(--page-px);
  text-align: center;
}
.pl-empty-ic {
  width: 26px;
  height: 26px;
  color: var(--ink-3);
}
.pl-empty-title {
  margin: 0;
  font: 600 var(--fs-md) / 1.3 var(--font-ui);
  color: var(--ink);
}
.pl-empty-sub {
  margin: 0;
  max-width: 44ch;
  font: 400 var(--fs-sm) / 1.5 var(--font-ui);
  color: var(--ink-2);
}

/* ============ ADD MODAL ============ */
/* Overlay + card + head + close button (and the mobile bottom-sheet, opted in
   via the `bottom-sheet` prop) now live in the shared AddModal component; only
   the Watchlist-specific body (the URL field) is styled here. */
.pl-tabpanel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.pl-field-label {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.pl-input {
  height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
  outline: none;
}
.pl-input--mono {
  font-family: var(--font-mono);
}
.pl-input::placeholder {
  color: var(--ink-3);
}
.pl-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.pl-input.is-error {
  border-color: var(--neg);
}
.pl-field-help {
  margin: 0;
  font: 400 var(--fs-xs) / 1.4 var(--font-ui);
  color: var(--ink-3);
}
.pl-form-error {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  margin: 0;
  font: 500 var(--fs-xs) / 1.3 var(--font-mono);
  color: var(--neg-ink);
}
.pl-form-error svg {
  width: 13px;
  height: 13px;
  flex: none;
}
.pl-url-go {
  align-self: flex-start;
}

/* ============ RESPONSIVE — column drop ============ */
@container pl (max-width: 1039px) {
  .pl-table {
    --pl-grid: minmax(0, 1fr) 190px 64px 196px 80px;
  }
  .col-creator {
    display: none;
  }
}
@container pl (max-width: 879px) {
  .pl-table {
    --pl-grid: minmax(0, 1fr) 64px 196px 80px;
  }
  .col-genre {
    display: none;
  }
  .pl-genre-fold {
    display: flex;
  }
}
@container pl (max-width: 719px) {
  .pl-table {
    --pl-grid: minmax(0, 1fr) 64px 80px;
  }
  .col-crawl {
    display: none;
  }
  .pl-crawl-fold {
    display: flex;
  }
  /* Below 720px the folded genre is limited to the dominant chip. */
  .pl-genre-fold .pl-style-link:nth-child(n + 2) {
    display: none;
  }
}
@container pl (max-width: 639px) {
  .pl-table {
    --pl-grid: minmax(0, 1fr) 44px 72px;
    --pl-gap: var(--space-2);
  }
  .pl-thead,
  .pl-row {
    padding-inline: var(--page-px-mobile);
  }
  .pl-head {
    padding: var(--space-4) var(--page-px-mobile) var(--space-3);
  }
  .head-tools {
    width: 100%;
    margin-left: 0;
  }
  .pl-sentinel,
  .pl-empty {
    padding-inline: var(--page-px-mobile);
  }
  .pl-filter-row {
    padding-inline: var(--page-px-mobile);
  }
}
</style>
