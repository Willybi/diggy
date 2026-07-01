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
            { value: 'rating', label: 'Rating' },
            { value: 'alpha', label: 'A–Z' },
          ]"
        />
      </div>
    </div>

    <!-- Pillar chips -->
    <FamilyChips v-model="familyFilter" :counts="familyCounts" />

    <!-- Skeleton loading -->
    <div v-if="loading && !items.length" class="artist-grid">
      <SkeletonGrid />
    </div>

    <!-- Empty state -->
    <div v-else-if="!items.length && !loading" class="empty">Aucun artiste ne correspond.</div>

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
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import { fmtNum } from '../utils/format'

const opinions = useOpinionsStore()

const PAGE_SIZE = 24

// -- State --
const items = ref([])
const total = ref(0)
const familyCounts = ref({})
const loading = ref(false)
const searchQuery = ref('')
const sortBy = ref('catalog')
const familyFilter = ref('all')
const offset = ref(0)
const hasMore = ref(false)

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

const displayItems = computed(() => items.value)

// -- Fetch --
async function fetchArtists(reset = true) {
  if (reset) {
    offset.value = 0
    items.value = []
  }

  const isOpinionFilter = sortBy.value === 'liked' || sortBy.value === 'disliked'

  // Opinion-based filters: fetch only matching artist IDs from opinions store
  if (isOpinionFilter) {
    if (!reset) return // no pagination for opinion filters
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
    return
  }

  // Normal paginated fetch
  loading.value = true
  try {
    const params = {
      sort: sortBy.value,
      limit: PAGE_SIZE,
      offset: offset.value,
    }
    if (familyFilter.value !== 'all') params.family = familyFilter.value
    if (searchQuery.value.trim()) params.q = searchQuery.value.trim()

    const { data } = await api.get('/api/artists/', { params })
    if (reset) {
      items.value = data.items
    } else {
      items.value = [...items.value, ...data.items]
    }
    total.value = data.total
    familyCounts.value = data.pillarCounts || {}
    hasMore.value = items.value.length < data.total
  } catch {
    if (reset) items.value = []
  } finally {
    loading.value = false
  }
}

function loadMore() {
  if (loading.value || !hasMore.value) return
  offset.value = items.value.length
  fetchArtists(false)
}

// -- Sort & family: immediate reload --
watch(sortBy, () => fetchArtists(true))
watch(familyFilter, () => fetchArtists(true))

const { sentinel } = useInfiniteScroll(loadMore)

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
.page-head {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 26px 30px 18px;
  flex-wrap: wrap;
}
.titles h1 {
  margin: 0;
  font: 600 28px/1.1 var(--font-ui);
  letter-spacing: -0.3px;
  color: var(--ink);
}
.sub {
  margin-top: 5px;
  font: 500 13px/1 var(--font-mono);
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}
/* -- Grid -- */
.artist-grid {
  padding: 2px 30px 36px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(208px, 1fr));
  gap: 16px;
}

/* -- Empty -- */
.empty {
  padding: 60px 30px;
  text-align: center;
  color: var(--ink-3);
  font: 500 14px var(--font-mono);
}

/* -- Sentinel -- */
.sentinel {
  display: none;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 8px 30px 40px;
  color: var(--ink-3);
  font: 500 12px/1 var(--font-mono);
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
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
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
@container (max-width: 680px) {
  .page-head,
  .artist-grid,
  .sentinel {
    padding-left: 18px;
    padding-right: 18px;
  }
  :deep(.fam-chips) {
    padding-left: 18px;
    padding-right: 18px;
  }
}
@container (max-width: 560px) {
  .artist-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@container (max-width: 380px) {
  .artist-grid {
    grid-template-columns: 1fr;
  }
}
</style>
