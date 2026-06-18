<template>
  <div class="artists-view">
    <header class="view-header">
      <div>
        <h1 class="view-title">Artistes</h1>
        <span class="view-sub">{{ total }} artiste{{ total !== 1 ? 's' : '' }}</span>
      </div>
      <input
        v-model="search"
        class="search-input"
        placeholder="Rechercher…"
        @input="onSearch"
      />
    </header>

    <div v-if="loading" class="state">Chargement…</div>

    <div v-else-if="artists.length === 0" class="state">Aucun artiste trouvé.</div>

    <div v-else class="table-wrap">
      <table class="ar-table">
        <thead>
          <tr>
            <th class="col-cover" />
            <th class="col-name">Artiste</th>
            <th class="col-genres">Genres</th>
            <th class="col-num num">Catalog</th>
            <th class="col-num num">In lib</th>
            <th class="col-num num">Rating</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="a in artists"
            :key="a.id"
            class="ar-row"
            @click="$router.push(`/artist/${a.id}`)"
          >
            <td class="col-cover">
              <div class="cover-thumb">
                <img v-if="a.has_artwork" :src="`/storage/artist-artworks/${a.id}.jpg`" :alt="a.name" />
                <span v-else class="fallback-letter">{{ a.name[0] }}</span>
              </div>
            </td>
            <td class="col-name">
              <span class="ar-name">{{ a.name }}</span>
              <span v-if="a.real_name" class="ar-real mono muted">{{ a.real_name }}</span>
            </td>
            <td class="col-genres">
              <div class="genre-list">
                <StyleTag v-for="g in a.genres" :key="g" :name="g" />
              </div>
            </td>
            <td class="col-num num"><span class="mono">{{ a.nb_catalog || '—' }}</span></td>
            <td class="col-num num">
              <span class="mono" :class="{ muted: !a.nb_lib }">{{ a.nb_lib || '—' }}</span>
            </td>
            <td class="col-num num">
              <span v-if="a.avg_rating" class="mono">{{ a.avg_rating }}</span>
              <span v-else class="muted">—</span>
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
let debounceTimer = null

const total = computed(() => artists.value.length)

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
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 960px;
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
.search-input {
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 8px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
  width: 220px;
}
.search-input::placeholder { color: var(--ink-3); }

.table-wrap { overflow-x: auto; }
.ar-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  table-layout: fixed;
}
.ar-table thead th {
  text-align: left;
  padding: 0 14px 12px;
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.ar-table thead th.num { text-align: right; }
.ar-table tbody td {
  height: 58px;
  padding: 0 14px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
  overflow: hidden;
}
.ar-table tbody tr:last-child td { border-bottom: none; }
.ar-row { cursor: pointer; }
.ar-row:hover td { background: var(--surface-2); }

.col-cover  { width: 54px; padding: 0 8px !important; }
.col-name   { width: auto; min-width: 160px; }
.col-genres { width: 200px; }
.col-num    { width: 72px; }

.cover-thumb {
  width: 40px; height: 40px;
  border-radius: 50%;
  border: 1px solid var(--line);
  overflow: hidden;
  background: var(--surface-2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.cover-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.fallback-letter {
  font: 600 16px/1 var(--font-ui);
  color: var(--ink-3);
  text-transform: uppercase;
}

.ar-name {
  display: block;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ar-real {
  display: block;
  font-size: 11px;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.genre-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.num { text-align: right; }
.mono { font-family: var(--font-mono); }
.muted { color: var(--ink-3); }

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>
