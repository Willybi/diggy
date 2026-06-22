<template>
  <div class="artists-view">
    <div class="page-head">
      <div class="titles">
        <h1>Artistes</h1>
        <div class="sub">{{ total }} artiste{{ total !== 1 ? 's' : '' }}</div>
      </div>
      <div class="head-tools">
        <label class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2" stroke-linecap="round"/></svg>
          <input
            v-model="search"
            type="text"
            placeholder="Rechercher…"
            @input="onSearch"
          />
        </label>
      </div>
    </div>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="artists.length === 0" class="state">Aucun artiste trouvé.</div>

    <div v-else class="table-wrap">
      <table class="tt">
        <colgroup>
          <col class="w-artist">
          <col class="w-genres col-genres">
          <col class="w-catalog">
          <col class="w-inlib col-inlib">
          <col class="w-rating col-rating">
        </colgroup>
        <thead>
          <tr>
            <th>Artiste</th>
            <th class="col-genres">Genres</th>
            <th class="num sortable" @click="toggleSort('nb_catalog')">
              Catalog
              <span v-if="sortKey === 'nb_catalog'" class="arr">{{ sortDir === 'desc' ? '↓' : '↑' }}</span>
            </th>
            <th class="num col-inlib sortable" @click="toggleSort('nb_lib')">
              In lib
              <span v-if="sortKey === 'nb_lib'" class="arr">{{ sortDir === 'desc' ? '↓' : '↑' }}</span>
            </th>
            <th class="num col-rating sortable" @click="toggleSort('avg_rating')">
              Rating
              <span v-if="sortKey === 'avg_rating'" class="arr">{{ sortDir === 'desc' ? '↓' : '↑' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="a in sortedArtists"
            :key="a.id"
            @click="$router.push(`/artist/${a.id}`)"
          >
            <td>
              <div class="artist-cell">
                <span class="av">
                  <img v-if="a.has_artwork" :src="`/storage/artist-artworks/${a.id}.jpg`" :alt="a.name" />
                </span>
                <span class="artist-name">{{ a.name }}</span>
              </div>
            </td>
            <td class="col-genres">
              <div v-if="a.genres && a.genres.length" class="genre-list">
                <StyleTag v-for="g in a.genres" :key="g" :name="g" />
              </div>
              <span v-else class="td-empty">—</span>
            </td>
            <td class="num">
              <span v-if="a.nb_catalog" class="td-num">{{ a.nb_catalog }}</span>
              <span v-else class="td-empty">—</span>
            </td>
            <td class="num col-inlib">
              <span v-if="a.nb_lib" class="td-num">{{ a.nb_lib }}</span>
              <span v-else class="td-empty">—</span>
            </td>
            <td class="num col-rating">
              <span v-if="a.avg_rating" class="td-rat">{{ Number(a.avg_rating).toFixed(1) }}</span>
              <span v-else class="td-empty">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import StyleTag from '../components/StyleTag.vue'

const artists = ref([])
const loading = ref(false)
const search = ref('')
const sortKey = ref(null)
const sortDir = ref('desc')
let debounceTimer = null

const total = computed(() => artists.value.length)

const sortedArtists = computed(() => {
  if (!sortKey.value) return artists.value
  const key = sortKey.value
  const dir = sortDir.value === 'desc' ? -1 : 1
  return [...artists.value].sort((a, b) => {
    const va = a[key] ?? 0
    const vb = b[key] ?? 0
    return (va - vb) * dir
  })
})

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}

async function fetchArtists() {
  loading.value = true
  try {
    const params = {}
    if (search.value.trim()) params.q = search.value.trim()
    const { data } = await axios.get('/api/artists/', { params })
    artists.value = data
  } finally {
    loading.value = false
  }
}

function onSearch() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(fetchArtists, 300)
}

onMounted(fetchArtists)
</script>

<style scoped>
.artists-view {
  container-type: inline-size;
}

.page-head {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 26px 30px 18px;
  flex-wrap: wrap;
}
.page-head .titles h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.3px;
}
.page-head .sub {
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
  min-width: 230px;
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

.table-wrap {
  padding: 4px 30px 30px;
  overflow-x: auto;
}
table.tt {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 440px;
}
table.tt col.w-artist  { width: auto; }
table.tt col.w-genres  { width: 260px; }
table.tt col.w-catalog { width: 90px; }
table.tt col.w-inlib   { width: 88px; }
table.tt col.w-rating  { width: 88px; }

table.tt thead th {
  position: sticky;
  top: 0;
  font: 600 10.5px/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 14px 11px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.num, table.tt td.num { text-align: center; }
table.tt th.sortable { cursor: pointer; }
table.tt th .arr { color: var(--accent-ink); margin-left: 4px; }
table.tt tbody tr {
  border-bottom: 1px solid var(--line);
  cursor: pointer;
}
table.tt tbody tr:hover { background: var(--surface-2); }
table.tt td { padding: 10px 14px; vertical-align: middle; }

.artist-cell {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
}
.av {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex: none;
  background: var(--surface-3);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.av img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.artist-name {
  font: 500 14.5px var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.genre-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  align-items: flex-start;
}

.td-num { font: 600 13px var(--font-mono); color: var(--ink); }
.td-rat { font: 600 13px var(--font-mono); color: var(--accent-ink); }
.td-empty { font: 500 13px var(--font-mono); color: var(--ink-3); }

.state {
  padding: 60px 30px;
  color: var(--ink-3);
  font: 400 14px var(--font-ui);
  text-align: center;
}

/* ── responsive (container queries) ── */
@container (max-width: 1040px) { .col-rating { display: none; } }
@container (max-width: 820px) {
  .col-inlib { display: none; }
  .head-tools { width: 100%; margin-left: 0; }
  .search { flex: 1; min-width: 0; }
}
@container (max-width: 640px) {
  .col-genres { display: none; }
  .page-head, .table-wrap { padding-left: 18px; padding-right: 18px; }
}
</style>
