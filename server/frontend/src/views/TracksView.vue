<template>
  <div class="tracks-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Live Library</h1>
        <span class="view-sub">{{ total }} tracks</span>
      </div>
      <div class="search-wrap">
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2" stroke-linecap="round"/>
        </svg>
        <input v-model="search" class="search-input" placeholder="Artiste…" @input="fetchTracks" />
      </div>
    </header>

    <div class="filters-wrap">
      <TrackFilters
        v-model:styleFilter="styleFilter"
        v-model:bpmMin="bpmMin"
        v-model:bpmMax="bpmMax"
        v-model:inLibOnly="inLibOnly"
      />
    </div>

    <TrackTable :tracks="pagedTracks" :loading="loading" />

    <div v-if="totalPages > 1" class="pagination">
      <button class="page-btn" :disabled="page === 1" @click="page--">←</button>
      <span class="page-info">{{ page }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="page === totalPages" @click="page++">→</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import axios from 'axios'
import TrackTable from '../components/TrackTable.vue'
import TrackFilters from '../components/TrackFilters.vue'

const PAGE_SIZE = 50

const tracks  = ref([])
const total   = ref(0)
const loading = ref(false)
const search  = ref('')
const page    = ref(1)

const styleFilter = ref('')
const bpmMin      = ref(null)
const bpmMax      = ref(null)
const inLibOnly   = ref(false)

async function fetchTracks() {
  loading.value = true
  page.value = 1
  try {
    const params = {}
    if (search.value)      params.artist = search.value
    if (styleFilter.value) params.tag    = styleFilter.value
    if (bpmMin.value)      params.bpmMin = bpmMin.value
    if (bpmMax.value)      params.bpmMax = bpmMax.value
    const { data } = await axios.get('/api/tracks/', { params })
    tracks.value = data.items
    total.value  = data.total
  } finally {
    loading.value = false
  }
}

const totalPages  = computed(() => Math.ceil(tracks.value.length / PAGE_SIZE))
const pagedTracks = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return tracks.value.slice(start, start + PAGE_SIZE)
})

watch([styleFilter, bpmMin, bpmMax], fetchTracks)
onMounted(fetchTracks)
</script>

<style scoped>
.tracks-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1400px;
  margin: 0 auto;
}
.view-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
.view-title {
  font: 600 22px/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}
.view-sub {
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
  margin-top: 4px;
  display: block;
}
.search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 8px 12px;
  min-width: 200px;
}
.search-icon {
  width: 14px;
  height: 14px;
  color: var(--ink-3);
  flex: none;
}
.search-input {
  border: none;
  background: transparent;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
  flex: 1;
  min-width: 0;
}
.search-input::placeholder {
  color: var(--ink-3);
}
.filters-wrap {
  margin-bottom: 16px;
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 20px;
}
.page-btn {
  padding: 6px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
}
.page-btn:hover:not(:disabled) { background: var(--surface-2); }
.page-btn:disabled { opacity: 0.35; cursor: default; }
.page-info {
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
  min-width: 60px;
  text-align: center;
}
</style>
