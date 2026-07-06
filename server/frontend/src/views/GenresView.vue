<template>
  <div class="genres-view">
    <!-- Header -->
    <div class="page-head">
      <div class="titles">
        <h1>Genres</h1>
        <div class="sub">
          <template v-if="isFiltered"
            >{{ fmtNum(total) }} / {{ fmtNum(totalUnfiltered) }} genres</template
          >
          <template v-else>{{ fmtNum(totalUnfiltered) }} genres</template>
        </div>
      </div>
      <div class="head-tools">
        <SearchBox
          v-model="searchQuery"
          placeholder="Rechercher un genre…"
          @update:modelValue="fetchGenres(true)"
        />
        <SegFilter
          v-model="sortBy"
          :options="[
            { value: 'tracks', label: 'Tracks' },
            { value: 'alpha', label: 'A–Z' },
            { value: 'liked', label: 'Liked', cls: 'liked' },
            { value: 'disliked', label: 'Disliked', cls: 'disliked' },
          ]"
        />
      </div>
    </div>

    <!-- Admin strip -->
    <div v-if="auth.user?.is_admin" class="admin-strip">
      <div class="admin-block">
        <span class="admin-label">Admin</span>
        <span class="admin-txt">
          <b>{{ fmtNum(unclassifiedCount) }}</b> {{ pl(unclassifiedCount, 'track', 'tracks') }} sans
          genre attribué — à classer
        </span>
        <button class="btn-admin" :disabled="classifying" @click="launchClassify">
          {{ classifying ? 'En cours…' : 'Lancer le classement auto' }}
        </button>
      </div>
    </div>

    <!-- Pillar chips -->
    <FamilyChips v-model="familyFilter" :counts="familyCounts" />

    <!-- Genre grid -->
    <div v-if="loading && !items.length" class="genre-grid" aria-live="polite">
      <SkeletonGrid />
    </div>

    <div v-else-if="!displayItems.length && !loading" class="empty">Aucun genre ne correspond.</div>

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
import api from '../utils/api.js'
import { useToast } from '../stores/toast.js'
import { useAuthStore } from '../stores/auth.js'
import { useOpinionsStore } from '../stores/opinions.js'
import GenreCard from '../components/GenreCard.vue'
import SearchBox from '../components/SearchBox.vue'
import SegFilter from '../components/SegFilter.vue'
import FamilyChips from '../components/FamilyChips.vue'
import SkeletonGrid from '../components/SkeletonGrid.vue'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import { fmtNum, pl } from '../utils/format'

const auth = useAuthStore()
const opinions = useOpinionsStore()

const PAGE_SIZE = 24

// ── State ──
const items = ref([])
const total = ref(0)
const familyCounts = ref({})
const loading = ref(false)
const searchQuery = ref('')
const sortBy = ref('tracks')
const familyFilter = ref('all')
const offset = ref(0)
const hasMore = ref(false)
const unclassifiedCount = ref(0)
const classifying = ref(false)

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

// ── Fetch ──
async function fetchGenres(reset = true) {
  if (reset) {
    offset.value = 0
    items.value = []
  }
  loading.value = true
  try {
    const params = {
      sort: sortBy.value === 'liked' || sortBy.value === 'disliked' ? 'tracks' : sortBy.value,
      limit: PAGE_SIZE,
      offset: offset.value,
    }
    if (familyFilter.value !== 'all') params.family = familyFilter.value
    if (searchQuery.value.trim()) params.q = searchQuery.value.trim()

    const { data } = await api.get('/api/genres', { params })
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
  fetchGenres(false)
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
watch(sortBy, () => fetchGenres(true))
watch(familyFilter, () => fetchGenres(true))

const { sentinel } = useInfiniteScroll(loadMore)

onMounted(() => {
  fetchGenres()
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
/* ── Admin strip ── */
.admin-strip {
  display: flex;
  margin: 0 30px 18px;
}
.admin-block {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 14px;
  border: 1px dashed var(--line-2);
  background: var(--surface-2);
  border-radius: var(--r-md);
  padding: 14px 16px;
}
.admin-label {
  font: 600 9.5px/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: 4px;
  padding: 5px 7px;
  flex: none;
}
.admin-txt {
  font: 500 13.5px var(--font-ui);
  color: var(--ink-2);
}
.admin-txt b {
  color: var(--ink);
  font: 600 13.5px var(--font-mono);
}
.btn-admin {
  margin-left: auto;
  height: 34px;
  padding: 0 15px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 600 12.5px var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-admin:hover {
  border-color: var(--accent);
  color: var(--accent-ink);
}
.btn-admin:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Grid ── */
.genre-grid {
  padding: 2px 30px 36px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(296px, 1fr));
  gap: 16px;
}

/* ── Empty state ── */
.empty {
  padding: 60px 30px;
  text-align: center;
  color: var(--ink-3);
  font: 500 14px var(--font-mono);
}

/* ── Sentinel ── */
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
    grid-template-columns: 1fr 1fr;
  }
}
@container (max-width: 640px) {
  .page-head,
  .genre-grid,
  .admin-strip,
  .sentinel {
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
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .genre-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }
}
@container (max-width: 520px) {
  .genre-grid {
    grid-template-columns: 1fr;
  }
}
</style>
