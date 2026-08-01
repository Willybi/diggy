<template>
  <div class="genres-view">
    <!-- Header -->
    <div class="page-head">
      <div class="titles">
        <h1>Genres</h1>
        <div class="sub">
          <template v-if="isFiltered"
            >{{ fmtNum(shownCount) }} / {{ fmtNum(totalUnfiltered) }} genres</template
          >
          <template v-else>{{ fmtNum(totalUnfiltered) }} genres</template>
        </div>
      </div>
      <div class="head-tools">
        <SearchBox
          v-model="searchQuery"
          placeholder="Rechercher un genre…"
          @update:modelValue="fetch(true)"
        />
        <SegFilter
          v-model="sortBy"
          :options="[
            { value: 'tracks', label: 'Tracks' },
            { value: 'lib', label: 'En bib' },
            { value: 'alpha', label: 'A–Z' },
            { value: 'liked', label: 'Liked', cls: 'liked' },
            { value: 'disliked', label: 'Disliked', cls: 'disliked' },
          ]"
        />
      </div>
    </div>

    <!-- Admin strip (is_admin only) -->
    <div v-if="auth.user?.is_admin" class="admin-strip">
      <div class="admin-block">
        <span class="admin-label">Admin</span>
        <span class="admin-txt">
          <b>{{ fmtNum(unclassifiedCount) }}</b> {{ pl(unclassifiedCount, 'track', 'tracks') }} sans
          genre attribué — à classer
        </span>
        <button class="btn btn--sm" :disabled="classifying" @click="launchClassify">
          {{ classifying ? 'En cours…' : 'Lancer le classement auto' }}
        </button>
      </div>
    </div>

    <!-- Pillar chips -->
    <FamilyChips v-model="familyFilter" :counts="familyCounts" />

    <!-- Skeleton loading -->
    <div v-if="loading && !items.length" class="genre-grid" aria-live="polite">
      <SkeletonGrid :count="9" />
    </div>

    <!-- Empty state: « Liked » facet with no liked genre -->
    <div
      v-else-if="!loading && !displayItems.length && sortBy === 'liked'"
      class="empty-facet empty-facet--liked"
    >
      <span class="ef-icon">
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
          />
        </svg>
      </span>
      <p class="ef-title">Aucun genre liké pour l'instant.</p>
      <p class="ef-sub">
        Le cœur en haut à droite d'une card note un genre sans ouvrir sa fiche. Les genres likés
        remontent dans les recommandations.
      </p>
      <button class="btn btn--sm" @click="showAll">Voir tous les genres</button>
    </div>

    <!-- Empty state: « Disliked » facet with no disliked genre -->
    <div
      v-else-if="!loading && !displayItems.length && sortBy === 'disliked'"
      class="empty-facet empty-facet--disliked"
    >
      <span class="ef-icon">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
          />
          <path d="M4.5 19.5 22 2" />
        </svg>
      </span>
      <p class="ef-title">Aucun genre disliké pour l'instant.</p>
      <p class="ef-sub">
        Le cœur barré en haut à droite d'une card écarte un genre. Les genres dislikés sont
        estompés dans la grille et sortent des recommandations.
      </p>
      <button class="btn btn--sm" @click="showAll">Voir tous les genres</button>
    </div>

    <!-- Empty state: search / filter with no result -->
    <div v-else-if="!loading && !displayItems.length" class="empty-search">
      <span class="es-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <circle cx="11" cy="11" r="7" stroke-width="1.8" />
          <path d="m20 20-3.2-3.2" stroke-width="1.8" stroke-linecap="round" />
        </svg>
      </span>
      <p class="es-title">Aucun genre ne correspond.</p>
      <p class="es-sub">
        <template v-if="searchQuery.trim()"
          >Aucun genre ne contient «&nbsp;{{ searchQuery.trim() }}&nbsp;» dans son nom. Vérifie
          l'orthographe ou élargis les filtres.</template
        >
        <template v-else>Aucun genre ne correspond à cette combinaison de filtres.</template>
      </p>
    </div>

    <!-- Genre grid -->
    <div v-else class="genre-grid" aria-live="polite">
      <GenreCard v-for="g in displayItems" :key="g.name" :genre="g" />
    </div>

    <!-- Sentinel (infinite scroll) -->
    <div
      ref="sentinel"
      class="sentinel"
      :class="{ on: hasMore && sortBy !== 'liked' && sortBy !== 'disliked' }"
    >
      <span class="spin"></span>Chargement…
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useToast } from '../stores/toast.js'
import { useAuthStore } from '../stores/auth.js'
import { useOpinionsStore } from '../stores/opinions.js'
import GenreCard from '../components/GenreCard.vue'
import SearchBox from '../components/SearchBox.vue'
import SegFilter from '../components/SegFilter.vue'
import FamilyChips from '../components/FamilyChips.vue'
import SkeletonGrid from '../components/SkeletonGrid.vue'
import { usePaginatedList } from '../composables/usePaginatedList.js'
import { useUrlSync } from '../composables/useUrlSync.js'
import { useScrollRestore } from '../composables/useScrollRestore.js'
import { fmtNum, pl } from '../utils/format'

const auth = useAuthStore()
const opinions = useOpinionsStore()
const route = useRoute()
const router = useRouter()

// ── Filters ──
const searchQuery = ref('')
const sortBy = ref('tracks')
const familyFilter = ref('all')
const unclassifiedCount = ref(0)
const classifying = ref(false)

// Filters ↔ URL so a back-return restores them (must run before the refetch
// watchers below, so the initial hydrate doesn't trigger a spurious fetch).
useUrlSync(
  [
    { ref: sortBy, param: 'sort', default: 'tracks' },
    { ref: familyFilter, param: 'fam', default: 'all' },
    { ref: searchQuery, param: 'q', default: '', debounce: true },
  ],
  { router, route },
)

// ── Paginated list (shared trunk) ──
// « lib » is a real backend sort (passed through). liked/disliked are client-side
// facets over the 'tracks' ordering, so they map to the same server sort;
// displayItems below applies the opinion filter.
const { items, total, familyCounts, loading, hasMore, sentinel, fetch, fetchUpTo } =
  usePaginatedList({
    endpoint: '/api/genres',
    pageSize: 24,
    sort: () => (sortBy.value === 'liked' || sortBy.value === 'disliked' ? 'tracks' : sortBy.value),
    family: () => familyFilter.value,
    query: () => searchQuery.value,
  })

// Scroll restoration on a back/forward return. The grid scrolls inside
// .app-main (#main-content); on return we reload the rows in one burst
// (fetchUpTo) then re-apply the offset.
const scrollRestore = useScrollRestore({
  scroller: () => document.getElementById('main-content'),
  getCount: () => items.value.length,
})

// Total unfiltered (for subtitle)
const totalUnfiltered = computed(() => {
  const fc = familyCounts.value
  return Object.values(fc).reduce((s, v) => s + v, 0)
})

const isFiltered = computed(
  () =>
    searchQuery.value.trim() ||
    familyFilter.value !== 'all' ||
    sortBy.value === 'liked' ||
    sortBy.value === 'disliked',
)

const displayItems = computed(() => {
  if (sortBy.value === 'liked') {
    return items.value.filter((g) => opinions.get('genre', g.name) === 'liked')
  }
  if (sortBy.value === 'disliked') {
    return items.value.filter((g) => opinions.get('genre', g.name) === 'disliked')
  }
  return items.value
})

// Subtitle counter: on an avis facet the filtering is client-side (displayItems),
// so the server-page `total` would lie (e.g. « 75 / 75 » over an empty grid).
const shownCount = computed(() =>
  sortBy.value === 'liked' || sortBy.value === 'disliked'
    ? displayItems.value.length
    : total.value,
)

function showAll() {
  sortBy.value = 'tracks'
}

// ── Admin ──
async function fetchUnclassifiedCount() {
  if (!auth.user?.is_admin) return
  try {
    const { data } = await api.get('/api/admin/genres/unclassified-count')
    unclassifiedCount.value = data.count
  } catch {
    useToast().show('Erreur lors du chargement des genres non classifiés')
  }
}

async function launchClassify() {
  classifying.value = true
  try {
    await api.post('/api/admin/genres/auto-classify', null)
  } catch {
    useToast().show('Erreur lors de la classification automatique')
  }
  classifying.value = false
}

// ── Sort & family filter: immediate reload ──
watch(sortBy, () => fetch(true))
watch(familyFilter, () => fetch(true))

onMounted(() => {
  scrollRestore.restore({
    initialFetch: () => fetch(true),
    hydrate: (count) => fetchUpTo(count),
  })
  fetchUnclassifiedCount()
})
</script>

<style scoped>
.genres-view {
  min-width: 0;
  display: flex;
  flex-direction: column;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* ── Header ── */
.titles h1 {
  margin: 0;
  font: 700 var(--fs-lg)/1.1 var(--font-ui);
  letter-spacing: -0.3px;
  color: var(--ink);
}
.sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* ── Admin strip (neutral: surface + hairline, no alert colour) ── */
.admin-strip {
  display: flex;
  margin: 0 var(--page-px) var(--space-5);
}
.admin-block {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  border: 1px solid var(--line);
  background: var(--surface-2);
  border-radius: var(--r-md);
  padding: var(--space-4);
}
.admin-label {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-xs);
  padding: var(--space-1) var(--space-15);
  flex: none;
}
.admin-txt {
  font: 500 var(--fs-sm) var(--font-ui);
  color: var(--ink-2);
}
.admin-txt b {
  color: var(--ink);
  font: 600 var(--fs-base) var(--font-mono);
}
/* Shared .btn handles the look; scoped: right-anchor in the strip + the
   disabled state (absent from .btn) */
.admin-block .btn {
  margin-left: auto;
}
.admin-block .btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Grid — never a single column (G13) ── */
.genre-grid {
  padding: var(--space-05) var(--page-px) var(--space-8);
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(296px, 1fr));
  gap: var(--space-4);
}

/* ── Empty states ── */
.empty-search,
.empty-facet {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-2);
  padding: var(--space-15x) var(--page-px);
}
.es-icon,
.ef-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  margin-bottom: var(--space-2);
}
.es-icon {
  background: var(--surface-2);
  color: var(--ink-3);
}
.empty-facet--liked .ef-icon {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.empty-facet--disliked .ef-icon {
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.es-icon svg,
.ef-icon svg {
  width: 26px;
  height: 26px;
  display: block;
}
.es-title,
.ef-title {
  margin: 0;
  font: 600 var(--fs-md)/1.3 var(--font-ui);
  color: var(--ink);
}
.es-sub,
.ef-sub {
  margin: 0;
  max-width: 42ch;
  font: 500 var(--fs-sm)/1.5 var(--font-ui);
  color: var(--ink-2);
}
.empty-facet .btn {
  margin-top: var(--space-2);
}

/* ── Sentinel ── */
.sentinel {
  display: none;
  align-items: center;
  justify-content: center;
  gap: var(--space-25);
  padding: var(--space-2) var(--page-px) var(--space-10);
  color: var(--ink-3);
  font: 500 var(--fs-sm)/1 var(--font-mono);
}
.sentinel.on {
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

/* ── Responsive (container queries on .app) ── */
@container (max-width: 820px) {
  .head-tools {
    width: 100%;
    margin-left: 0;
  }
  :deep(.search) {
    flex: 1;
    min-width: 0;
  }
}
@container (max-width: 720px) {
  .genre-grid {
    grid-template-columns: repeat(auto-fill, minmax(216px, 1fr));
    gap: var(--space-3);
  }
}
@container (max-width: 640px) {
  .page-head,
  .genre-grid,
  .admin-strip,
  .sentinel,
  .empty-search,
  .empty-facet {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  :deep(.fam-chips) {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .admin-strip {
    margin-left: 0;
    margin-right: 0;
  }
  :deep(.search) {
    flex: 1 1 100%;
  }
  /* 2 fixed columns — never 1 (G13) */
  .genre-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  /* Admin strip repli: text full-width, button full-width below (G11) */
  .admin-block {
    flex-wrap: wrap;
    row-gap: var(--space-3);
  }
  .admin-txt {
    flex-basis: 100%;
    text-wrap: pretty;
  }
  .admin-block .btn {
    margin-left: 0;
    flex-basis: 100%;
    width: 100%;
    justify-content: center;
  }
}
</style>
