<template>
  <div class="artists-view">
    <!-- Header -->
    <div class="page-head">
      <div class="titles">
        <h1>Artistes</h1>
        <div class="sub">
          <template v-if="isFiltered"
            >{{ fmtNum(total) }} / {{ fmtNum(totalUnfiltered) }} artistes</template
          >
          <template v-else>{{ fmtNum(totalUnfiltered) }} artistes</template>
        </div>
      </div>
      <div class="head-tools">
        <SearchBox
          v-model="searchQuery"
          placeholder="Rechercher un artiste…"
          @update:modelValue="fetchArtists(true)"
        />
        <SegFilter
          v-model="sortBy"
          :options="[
            { value: 'catalog', label: 'Catalog' },
            { value: 'lib', label: 'In Bib' },
            { value: 'liked', label: 'Liked', cls: 'liked' },
            { value: 'disliked', label: 'Disliked', cls: 'disliked' },
            { value: 'followed', label: 'Suivis' },
            { value: 'alpha', label: 'A–Z' },
          ]"
        />
      </div>
    </div>

    <!-- Pillar chips + « Sans Deezer » toggle -->
    <div class="tools-row">
      <FamilyChips v-model="familyFilter" :counts="familyCounts" />
      <button
        type="button"
        class="no-dz"
        :class="{ on: noDeezer }"
        role="switch"
        :aria-checked="noDeezer"
        title="Restreindre aux artistes non liés à Deezer (backlog d'enrichissement)"
        @click="toggleNoDeezer"
      >
        <span class="no-dz-label">Sans Deezer</span>
        <span class="no-dz-track"><span class="no-dz-thumb"></span></span>
      </button>
    </div>

    <!-- Skeleton loading -->
    <div v-if="loading && !items.length" class="artist-grid">
      <SkeletonGrid :count="10" />
    </div>

    <!-- Empty state: « Suivis » filter with no followed artist (frequent) -->
    <div v-else-if="!items.length && sortBy === 'followed'" class="empty-follow">
      <span class="ef-icon">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5S10.5 3.17 10.5 4v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"
          />
        </svg>
      </span>
      <p class="ef-title">Tu ne suis aucun artiste pour l'instant.</p>
      <p class="ef-sub">
        La pastille en haut à gauche de chaque card suit un artiste sans ouvrir sa fiche. Les
        artistes suivis alimentent les nouveautés du hub.
      </p>
      <button class="btn btn--sm" @click="showAll">Voir tout le catalogue</button>
    </div>

    <!-- Empty state: search / filter with no result -->
    <div v-else-if="!items.length && !loading" class="empty-search">
      <span class="es-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <circle cx="11" cy="11" r="7" stroke-width="1.8" />
          <path d="m20 20-3.2-3.2" stroke-width="1.8" stroke-linecap="round" />
        </svg>
      </span>
      <p class="es-title">Aucun artiste ne correspond.</p>
      <p class="es-sub">
        <template v-if="searchQuery.trim()"
          >Aucun artiste ne contient «&nbsp;{{ searchQuery.trim() }}&nbsp;» dans son nom. Vérifie
          l'orthographe ou élargis les filtres.</template
        >
        <template v-else>Aucun artiste ne correspond à cette combinaison de filtres.</template>
      </p>
    </div>

    <!-- Card grid -->
    <div v-else class="artist-grid">
      <ArtistCard v-for="a in displayItems" :key="a.id" :artist="a" />
    </div>

    <!-- Sentinel (infinite scroll) -->
    <div ref="sentinel" class="sentinel" :class="{ on: hasMore }">
      <span class="spin"></span>Chargement…
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '../utils/api.js'
import { useOpinionsStore } from '../stores/opinions.js'
import ArtistCard from '../components/ArtistCard.vue'
import SearchBox from '../components/SearchBox.vue'
import SegFilter from '../components/SegFilter.vue'
import FamilyChips from '../components/FamilyChips.vue'
import SkeletonGrid from '../components/SkeletonGrid.vue'
import { usePaginatedList } from '../composables/usePaginatedList.js'
import { fmtNum } from '../utils/format'

const opinions = useOpinionsStore()

// -- Filters --
const searchQuery = ref('')
const sortBy = ref('catalog')
const familyFilter = ref('all')
const noDeezer = ref(false)

// « Suivis » is a server filter (followed=true) sent with a valid default sort;
// « Sans Deezer » restricts the corpus for every sort. Both ride the shared
// paginated list via extraParams (opt-in, so other views stay untouched).
const extraParams = () => {
  const p = {}
  if (sortBy.value === 'followed') p.followed = true
  if (noDeezer.value) p.no_deezer = true
  return Object.keys(p).length ? p : undefined
}

// -- Paginated list (shared trunk) --
const { items, total, familyCounts, loading, hasMore, sentinel, fetch } = usePaginatedList({
  endpoint: '/api/artists/',
  pageSize: 24,
  // « followed » is not a backend sort value — map it to a valid default and
  // carry the filter through extraParams.
  sort: () => (sortBy.value === 'followed' ? 'catalog' : sortBy.value),
  family: () => familyFilter.value,
  query: () => searchQuery.value,
  extraParams,
})

const totalUnfiltered = computed(() => {
  const fc = familyCounts.value
  return Object.values(fc).reduce((s, v) => s + v, 0)
})

const isFiltered = computed(
  () =>
    searchQuery.value.trim() ||
    familyFilter.value !== 'all' ||
    sortBy.value === 'liked' ||
    sortBy.value === 'disliked' ||
    sortBy.value === 'followed' ||
    noDeezer.value,
)

const displayItems = computed(() => items.value)

function toggleNoDeezer() {
  noDeezer.value = !noDeezer.value
}

function showAll() {
  sortBy.value = 'catalog'
}

// -- Fetch --
// Normal sorts (incl. « followed » via extraParams) go through the shared
// paginated list; opinion filters (liked/disliked) resolve matching IDs from
// the opinions store in one non-paginated shot and write the shared refs.
async function fetchArtists(reset = true) {
  const isOpinionFilter = sortBy.value === 'liked' || sortBy.value === 'disliked'
  if (!isOpinionFilter) return fetch(reset)

  if (!reset) return // no pagination for opinion filters
  items.value = []
  loading.value = true
  try {
    await opinions.load()
    const artistOpinions = opinions.data.artist || {}
    const matchingIds = Object.entries(artistOpinions)
      .filter(([, v]) => v === sortBy.value)
      .map(([k]) => k)

    if (!matchingIds.length) {
      total.value = 0
      hasMore.value = false
      return
    }

    const params = {
      sort: 'alpha',
      limit: 100,
      offset: 0,
      ids: matchingIds.join(','),
    }
    if (familyFilter.value !== 'all') params.family = familyFilter.value
    if (searchQuery.value.trim()) params.q = searchQuery.value.trim()
    if (noDeezer.value) params.no_deezer = true

    const { data } = await api.get('/api/artists/', { params })
    items.value = data.items
    total.value = data.total
    familyCounts.value = data.pillarCounts || {}
    hasMore.value = false
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

// -- Sort, family & « Sans Deezer »: immediate reload --
watch(sortBy, () => fetchArtists(true))
watch(familyFilter, () => fetchArtists(true))
watch(noDeezer, () => fetchArtists(true))

onMounted(() => {
  fetchArtists()
})
</script>

<style scoped>
.artists-view {
  min-width: 0;
  display: flex;
  flex-direction: column;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* -- Header -- */
.titles h1 {
  margin: 0;
  font: 600 var(--fs-xl)/1.1 var(--font-ui);
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

/* -- Tools row: FamilyChips + « Sans Deezer » toggle -- */
.tools-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: 0 var(--page-px) var(--space-4);
}
.tools-row :deep(.fam-chips) {
  flex: 1;
  min-width: 0;
  padding: 0;
}
.no-dz {
  margin-left: auto;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 32px;
  padding: 0 var(--space-25);
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.14s,
    border-color 0.14s,
    color 0.14s;
}
.no-dz-track {
  position: relative;
  width: 26px;
  height: 15px;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  flex: none;
  transition: background 0.14s;
}
.no-dz-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--ink-2);
  transition:
    transform 0.14s,
    background 0.14s;
}
.no-dz.on {
  background: var(--accent-soft);
  border-color: var(--accent-soft-2);
  color: var(--accent-ink);
}
.no-dz.on .no-dz-track {
  background: var(--accent);
}
.no-dz.on .no-dz-thumb {
  transform: translateX(11px);
  background: var(--on-accent);
}
.no-dz:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* -- Grid -- */
.artist-grid {
  padding: var(--space-05) var(--page-px) var(--space-8);
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(208px, 1fr));
  gap: var(--space-4);
}

/* -- Empty states -- */
.empty-search,
.empty-follow {
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
.ef-icon {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.es-icon svg,
.ef-icon svg {
  width: 26px;
  height: 26px;
  display: block;
}
.ef-icon svg {
  fill: currentColor;
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
.empty-follow .btn {
  margin-top: var(--space-2);
}

/* -- Sentinel -- */
.sentinel {
  display: none;
  align-items: center;
  justify-content: center;
  gap: var(--space-25);
  padding: var(--space-2) var(--page-px) var(--space-10);
  color: var(--ink-3);
  font: 500 var(--fs-xs)/1 var(--font-mono);
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

/* -- Responsive (container queries) -- */
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
  .artist-grid {
    grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
    gap: var(--space-3);
  }
}
@container (max-width: 640px) {
  .page-head,
  .artist-grid,
  .sentinel,
  .tools-row {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  :deep(.search) {
    flex: 1 1 100%;
  }
  .artist-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
