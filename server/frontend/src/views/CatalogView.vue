<template>
  <div class="catalog-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Catalog</h1>
        <span class="view-sub">{{ filteredEntries.length }} / {{ entries.length }} tracks</span>
      </div>
      <div class="filters">
        <input v-model="search" class="search-input" placeholder="Artiste ou titre…" />
        <button class="chip" :class="{ 'chip--on': notInLib }" @click="toggleChip('notInLib')">
          Pas dans RB
        </button>
        <button class="chip" :class="{ 'chip--on': radarMin2 }" @click="toggleChip('radarMin2')">
          Radar ≥ 2
        </button>
      </div>
    </header>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!entries.length" class="state">Aucun résultat.</div>
    <template v-else>
      <div class="table-wrap">
        <table class="track-table">
          <thead>
            <tr>
              <th class="col-play" />
              <th class="col-title sortable" :class="{ 'is-sorted': sortKey === 'title' }" @click="sort('title')">
                Track <span v-if="sortKey === 'title'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-radar sortable" :class="{ 'is-sorted': sortKey === 'nb_radar_playlists' }" @click="sort('nb_radar_playlists')">
                Radar <span v-if="sortKey === 'nb_radar_playlists'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-bpm num sortable" :class="{ 'is-sorted': sortKey === 'bpm' }" @click="sort('bpm')">
                BPM <span v-if="sortKey === 'bpm'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-key num">Key</th>
              <th class="col-duration num sortable" :class="{ 'is-sorted': sortKey === 'duration_ms' }" @click="sort('duration_ms')">
                Durée <span v-if="sortKey === 'duration_ms'" class="sort-indicator">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="col-inlib">In lib</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in pagedEntries" :key="e.id">
              <td class="col-play"><span class="play-btn"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg></span></td>
              <td class="col-title">
                <div class="cell-track">
                  <div class="mini-art">
                    <img v-if="e.has_artwork" :src="`/storage/catalog-artworks/${e.id}.jpg`" :alt="e.title" />
                  </div>
                  <div class="track-info">
                    <span class="track-title">{{ e.title }}</span>
                    <span class="track-artist">{{ e.artist }}</span>
                  </div>
                </div>
              </td>
              <td class="col-radar">
                <span v-if="e.nb_radar_playlists > 0" class="radar-badge">{{ e.nb_radar_playlists }}</span>
                <span v-else class="muted">—</span>
              </td>
              <td class="col-bpm num"><span class="mono">{{ e.bpm ?? '—' }}</span></td>
              <td class="col-key num"><span class="mono key-val">{{ e.key || '—' }}</span></td>
              <td class="col-duration num"><span class="mono">{{ e.duration_ms ? formatDuration(e.duration_ms) : '—' }}</span></td>
              <td class="col-inlib"><InLibBadge :in-lib="e.in_lib" /></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="pagination">
        <button class="page-btn" :disabled="page === 1" @click="page--">←</button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="page === totalPages" @click="page++">→</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import axios from 'axios'
import InLibBadge from '../components/InLibBadge.vue'

const PAGE_SIZE = 50

const entries   = ref([])
const loading   = ref(false)
const search    = ref('')
const notInLib  = ref(false)
const radarMin2 = ref(false)
const sortKey   = ref('nb_radar_playlists')
const sortDir   = ref('desc')
const page      = ref(1)

function toggleChip(chip) {
  if (chip === 'notInLib') notInLib.value = !notInLib.value
  if (chip === 'radarMin2') radarMin2.value = !radarMin2.value
}

function sort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
  page.value = 1
}

function formatDuration(ms) {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

async function fetchEntries() {
  loading.value = true
  page.value = 1
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
  const arr = q
    ? entries.value.filter(e => e.title?.toLowerCase().includes(q) || e.artist?.toLowerCase().includes(q))
    : entries.value

  const k = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...arr].sort((a, b) => {
    const av = a[k] ?? (typeof a[k] === 'number' ? -Infinity : '')
    const bv = b[k] ?? (typeof b[k] === 'number' ? -Infinity : '')
    return av < bv ? -dir : av > bv ? dir : 0
  })
})

const totalPages = computed(() => Math.ceil(filteredEntries.value.length / PAGE_SIZE))

const pagedEntries = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return filteredEntries.value.slice(start, start + PAGE_SIZE)
})

watch([notInLib, radarMin2], fetchEntries)
watch(search, () => { page.value = 1 })
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
  padding: 8px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
  min-width: 180px;
}
.search-input::placeholder { color: var(--ink-3); }
.chip {
  padding: 7px 14px;
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

/* Table — même style que TrackTable */
.table-wrap { overflow-x: auto; }
.track-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
}
.track-table thead th {
  text-align: left;
  padding: 0 14px 12px;
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
.track-table thead th.sortable { cursor: pointer; }
.track-table thead th.sortable:hover { color: var(--ink-2); }
.track-table thead th.is-sorted { color: var(--accent-ink); }
.track-table thead th.num { text-align: right; }
.track-table tbody td {
  height: var(--row-h);
  padding: 0 14px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
}
.track-table tbody tr:hover td { background: var(--surface-2); }
.track-table tbody tr:last-child td { border-bottom: none; }
.sort-indicator { margin-left: 4px; color: var(--accent-ink); }

/* Play btn */
.col-play { width: 30px; padding: 0 8px !important; }
.play-btn {
  width: 26px; height: 26px;
  border-radius: 50%;
  border: 1px solid var(--line-2);
  background: var(--surface);
  display: grid; place-items: center;
  color: var(--ink-2);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s;
}
.play-btn svg { width: 13px; height: 13px; }
.track-table tbody tr:hover .play-btn { opacity: 1; }

/* Track cell */
.cell-track { display: flex; align-items: center; gap: 12px; }
.mini-art {
  width: 38px; height: 38px;
  flex: none;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  overflow: hidden;
  background: repeating-linear-gradient(135deg, var(--surface-2) 0 5px, var(--surface-3) 5px 10px);
}
.mini-art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.track-info { min-width: 0; }
.track-title {
  display: block;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.track-artist {
  display: block;
  font-size: 12px;
  color: var(--ink-2);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* Numeric */
.num { text-align: right; }
.mono { font-family: var(--font-mono); color: var(--ink-2); }
.key-val { color: var(--accent-ink); font-weight: 500; }
.muted { color: var(--ink-3); }

/* Radar badge */
.radar-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 22px; height: 22px; padding: 0 6px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 11px/1 var(--font-mono);
}

/* Pagination */
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

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>
