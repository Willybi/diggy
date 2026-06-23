<template>
  <div class="genres-view">
    <!-- Header -->
    <div class="page-head">
      <div class="titles">
        <h1>Genres</h1>
        <div class="sub">
          <template v-if="isFiltered">{{ fmtNum(total) }} / {{ fmtNum(totalUnfiltered) }} genres</template>
          <template v-else>{{ fmtNum(totalUnfiltered) }} genres</template>
        </div>
      </div>
      <div class="head-tools">
        <label class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2" stroke-linecap="round"/></svg>
          <input v-model="searchQuery" type="text" placeholder="Rechercher un genre…" />
        </label>
        <div class="filterseg">
          <button :class="{ on: sortBy === 'tracks' }" @click="sortBy = 'tracks'">Tracks</button>
          <button :class="{ on: sortBy === 'alpha' }" @click="sortBy = 'alpha'">A–Z</button>
        </div>
      </div>
    </div>

    <!-- Admin strip -->
    <div v-if="auth.user?.is_admin" class="admin-strip">
      <div class="admin-block">
        <span class="admin-label">Admin</span>
        <span class="admin-txt">
          <b>{{ fmtNum(unclassifiedCount) }}</b> tracks sans genre attribué — à classer
        </span>
        <button class="btn-admin" :disabled="classifying" @click="launchClassify">
          {{ classifying ? 'En cours…' : 'Lancer le classement auto' }}
        </button>
      </div>
    </div>

    <!-- Family chips -->
    <div class="fam-chips">
      <button
        v-for="chip in familyChips"
        :key="chip.key"
        class="fam-chip"
        :class="{ on: familyFilter === chip.key }"
        @click="familyFilter = chip.key"
      >
        <span v-if="chip.hue != null" class="fc-dot" :style="{ '--fh': chip.hue }"></span>
        {{ chip.label }}<span class="fc-n">{{ fmtNum(chip.count) }}</span>
      </button>
    </div>

    <!-- Genre grid -->
    <div v-if="loading && !items.length" class="genre-grid">
      <div v-for="i in 12" :key="i" class="skeleton-card">
        <div class="sk-art"></div>
        <div class="sk-body">
          <div class="sk-line w60"></div>
          <div class="sk-line w40"></div>
        </div>
      </div>
    </div>

    <div v-else-if="!items.length && !loading" class="empty">
      Aucun genre ne correspond.
    </div>

    <div v-else class="genre-grid">
      <GenreCard v-for="g in items" :key="g.name" :genre="g" />
    </div>

    <!-- Sentinel (infinite scroll) -->
    <div ref="sentinelRef" class="sentinel" :class="{ on: hasMore }">
      <span class="spin"></span>Chargement…
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import axios from 'axios'
import { useAuthStore } from '../stores/auth.js'
import { styleTone } from '../composables/useStyleMap.js'
import GenreCard from '../components/GenreCard.vue'

const auth = useAuthStore()

const FAMILY_HUES = { house: 268, techno: 312, trance: 352, other: 42 }
const PAGE_SIZE = 24

function authHeaders() {
  return auth.token ? { Authorization: `Bearer ${auth.token}` } : {}
}

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
const sentinelRef = ref(null)
const unclassifiedCount = ref(0)
const classifying = ref(false)

// Total unfiltered (for subtitle)
const totalUnfiltered = computed(() => {
  const fc = familyCounts.value
  return Object.values(fc).reduce((s, v) => s + v, 0)
})

const isFiltered = computed(() => searchQuery.value.trim() || familyFilter.value !== 'all')

// Family chips
const familyChips = computed(() => {
  const fc = familyCounts.value
  const allCount = Object.values(fc).reduce((s, v) => s + v, 0)
  return [
    { key: 'all', label: 'Tous', hue: null, count: allCount },
    { key: 'house', label: 'House', hue: FAMILY_HUES.house, count: fc.house || 0 },
    { key: 'techno', label: 'Techno', hue: FAMILY_HUES.techno, count: fc.techno || 0 },
    { key: 'trance', label: 'Trance', hue: FAMILY_HUES.trance, count: fc.trance || 0 },
    { key: 'other', label: 'Autre', hue: FAMILY_HUES.other, count: (fc.other || 0) + (fc.misc || 0) },
  ]
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
      sort: sortBy.value,
      limit: PAGE_SIZE,
      offset: offset.value,
    }
    if (familyFilter.value !== 'all') params.family = familyFilter.value
    if (searchQuery.value.trim()) params.q = searchQuery.value.trim()

    const { data } = await axios.get('/api/genres', { params, headers: authHeaders() })
    if (reset) {
      items.value = data.items
    } else {
      items.value = [...items.value, ...data.items]
    }
    total.value = data.total
    familyCounts.value = data.familyCounts || {}
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
    const { data } = await axios.get('/api/admin/genres/unclassified-count', { headers: authHeaders() })
    unclassifiedCount.value = data.count
  } catch {}
}

async function launchClassify() {
  classifying.value = true
  try {
    await axios.post('/api/admin/genres/auto-classify', null, { headers: authHeaders() })
  } catch {}
  classifying.value = false
}

// ── Search debounce ──
let debounceTimer = null
watch(searchQuery, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => fetchGenres(true), 250)
})

// ── Sort & family filter: immediate reload ──
watch(sortBy, () => fetchGenres(true))
watch(familyFilter, () => fetchGenres(true))

// ── IntersectionObserver for infinite scroll ──
let observer = null
onMounted(() => {
  fetchGenres()
  fetchUnclassifiedCount()

  nextTick(() => {
    if (sentinelRef.value) {
      observer = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) loadMore()
        },
        { rootMargin: '0px 0px 360px 0px' }
      )
      observer.observe(sentinelRef.value)
    }
  })
})

onUnmounted(() => {
  observer?.disconnect()
  clearTimeout(debounceTimer)
})

function fmtNum(n) {
  return (n || 0).toLocaleString('fr-FR').replace(/\u202f/g, ' ')
}
</script>

<style scoped>
.genres-view {
  min-width: 0;
  display: flex;
  flex-direction: column;
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
  letter-spacing: -.3px;
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
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 0 12px;
  height: 38px;
  min-width: 220px;
}
.search svg {
  width: 16px;
  height: 16px;
  color: var(--ink-3);
  flex: none;
}
.search input {
  border: 0;
  background: transparent;
  outline: none;
  width: 100%;
  font: 400 14px var(--font-ui);
  color: var(--ink);
}
.search input::placeholder { color: var(--ink-3); }
.filterseg {
  display: flex;
  gap: 2px;
  background: var(--surface-2);
  padding: 3px;
  border-radius: var(--r-sm);
}
.filterseg button {
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  padding: 8px 13px;
  border-radius: var(--r-xs);
  cursor: pointer;
}
.filterseg button:hover { color: var(--ink); }
.filterseg button.on {
  background: var(--accent-soft);
  color: var(--accent-ink);
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
  letter-spacing: .12em;
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
.btn-admin:hover { border-color: var(--accent); color: var(--accent-ink); }
.btn-admin:disabled { opacity: .5; cursor: default; }

/* ── Family chips ── */
.fam-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 30px 16px;
}
.fam-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: background .14s, border-color .14s, color .14s;
}
.fam-chip:hover { background: var(--surface-2); color: var(--ink); }
.fc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--fh));
}
.fc-n {
  font: 600 11px/1 var(--font-mono);
  color: var(--ink-3);
}
.fam-chip.on {
  background: var(--accent-soft);
  border-color: transparent;
  color: var(--accent-ink);
}
.fam-chip.on .fc-n { color: var(--accent-ink); }

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

/* ── Skeleton loading ── */
.skeleton-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.sk-art {
  height: 130px;
  background: var(--surface-2);
  animation: shimmer 1.2s ease-in-out infinite alternate;
}
.sk-body { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.sk-line {
  height: 14px;
  border-radius: 4px;
  background: var(--surface-2);
  animation: shimmer 1.2s ease-in-out infinite alternate;
}
.sk-line.w60 { width: 60%; }
.sk-line.w40 { width: 40%; }
@keyframes shimmer {
  from { opacity: .6; }
  to { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .sk-art, .sk-line { animation: none; }
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
.sentinel.on { display: flex; }
.spin {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--line-2);
  border-top-color: var(--accent);
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin { animation: none; } }

/* ── Responsive (container queries on .app) ── */
@container (max-width: 820px) {
  .head-tools { width: 100%; margin-left: 0; }
  .search { flex: 1; min-width: 0; }
}
@container (max-width: 720px) {
  .genre-grid { grid-template-columns: 1fr 1fr; }
}
@container (max-width: 640px) {
  .page-head, .genre-grid, .admin-strip, .fam-chips, .sentinel {
    padding-left: 18px;
    padding-right: 18px;
  }
  .admin-strip { margin-left: 0; margin-right: 0; padding-left: 18px; padding-right: 18px; }
}
@container (max-width: 520px) {
  .genre-grid { grid-template-columns: 1fr; }
}
</style>
