<template>
  <div class="catalog-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Catalog</h1>
        <span class="view-sub">
          {{ displayedEntries.length }}
          <template v-if="displayedEntries.length !== entries.length"> / {{ entries.length }}</template>
          tracks
        </span>
      </div>
      <div class="filters">
        <input v-model="search" class="search-input" placeholder="Artiste ou titre…" />
        <button class="chip" :class="{ 'chip--on': notInLib }" @click="notInLib = !notInLib">
          Pas dans RB
        </button>
        <button class="chip" :class="{ 'chip--on': radarMin2 }" @click="radarMin2 = !radarMin2">
          Radar ≥ 2
        </button>
      </div>
    </header>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!entries.length" class="state">Aucun résultat.</div>
    <table v-else class="catalog-table">
      <thead>
        <tr>
          <th @click="sort('title')">Track <SortIcon :active="sortKey === 'title'" :dir="sortDir" /></th>
          <th @click="sort('nb_radar_playlists')">Radar <SortIcon :active="sortKey === 'nb_radar_playlists'" :dir="sortDir" /></th>
          <th @click="sort('bpm')">BPM <SortIcon :active="sortKey === 'bpm'" :dir="sortDir" /></th>
          <th @click="sort('key')">Key <SortIcon :active="sortKey === 'key'" :dir="sortDir" /></th>
          <th @click="sort('duration_ms')">Durée <SortIcon :active="sortKey === 'duration_ms'" :dir="sortDir" /></th>
          <th>In lib</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in displayedEntries" :key="e.id">
          <td class="col-track">
            <span class="track-title">{{ e.title }}</span>
            <span class="track-artist">{{ e.artist }}</span>
          </td>
          <td>
            <span v-if="e.nb_radar_playlists > 0" class="radar-badge">{{ e.nb_radar_playlists }}</span>
            <span v-else class="muted">—</span>
          </td>
          <td class="mono">{{ e.bpm != null ? e.bpm : '—' }}</td>
          <td class="key">{{ e.key || '—' }}</td>
          <td class="mono">{{ e.duration_ms ? formatDuration(e.duration_ms) : '—' }}</td>
          <td><InLibBadge :in-lib="e.in_lib" /></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import axios from 'axios'
import InLibBadge from '../components/InLibBadge.vue'

// — Inline micro-component for sort icon
const SortIcon = {
  props: { active: Boolean, dir: String },
  template: `<span class="sort-icon" :class="{ 'sort-icon--on': active }">{{ active ? (dir === 'asc' ? '↑' : '↓') : '↕' }}</span>`,
}

const entries  = ref([])
const loading  = ref(false)
const search   = ref('')
const notInLib = ref(false)
const radarMin2 = ref(false)

const sortKey = ref('nb_radar_playlists')
const sortDir = ref('desc')

function sort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}

function formatDuration(ms) {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

async function fetchEntries() {
  loading.value = true
  try {
    const params = {}
    if (notInLib.value)  params.in_lib = false
    if (radarMin2.value) params.min_radar_playlists = 2
    const { data } = await axios.get('/api/catalog/', { params })
    entries.value = data
  } finally {
    loading.value = false
  }
}

const filteredEntries = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return entries.value
  return entries.value.filter(e =>
    e.title?.toLowerCase().includes(q) || e.artist?.toLowerCase().includes(q)
  )
})

const displayedEntries = computed(() => {
  const arr = [...filteredEntries.value]
  const k = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  arr.sort((a, b) => {
    const av = a[k] ?? (typeof a[k] === 'number' ? -Infinity : '')
    const bv = b[k] ?? (typeof b[k] === 'number' ? -Infinity : '')
    return av < bv ? -dir : av > bv ? dir : 0
  })
  return arr
})

watch([notInLib, radarMin2], fetchEntries)
onMounted(fetchEntries)
</script>

<style scoped>
.catalog-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
}
.view-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
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
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.search-input {
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 6px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
  min-width: 180px;
}
.search-input::placeholder { color: var(--ink-3); }
.chip {
  padding: 5px 12px;
  border-radius: 999px;
  font: 500 12px/1 var(--font-ui);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.chip--on {
  background: var(--pos-soft);
  color: var(--pos-ink);
  border-color: transparent;
}
.catalog-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.catalog-table thead th {
  text-align: left;
  padding: 6px 12px;
  font: 500 11px/1 var(--font-ui);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line-2);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.catalog-table tbody tr {
  height: var(--row-h, 40px);
  border-bottom: 1px solid var(--line-1);
}
.catalog-table tbody tr:hover { background: var(--surface-2); }
.catalog-table td {
  padding: 0 12px;
  vertical-align: middle;
}
.col-track {
  max-width: 320px;
}
.track-title {
  display: block;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.track-artist {
  display: block;
  font-size: 11.5px;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.radar-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 11px/1 var(--font-mono);
}
.mono  { font-family: var(--font-mono); color: var(--ink-2); }
.key   { font-family: var(--font-mono); color: var(--accent-ink); }
.muted { color: var(--ink-3); }
.sort-icon {
  font-size: 10px;
  color: var(--ink-3);
  margin-left: 3px;
}
.sort-icon--on { color: var(--accent-ink); }
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>
