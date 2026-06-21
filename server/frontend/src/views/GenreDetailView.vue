<template>
  <div class="detail-view">
    <header class="view-header">
      <RouterLink to="/tags" class="back-link">← Genres</RouterLink>
      <div class="genre-header">
        <StyleTag :name="genreName" />
        <span class="genre-total">{{ total }} tracks</span>
      </div>
    </header>

    <!-- Search -->
    <div class="search-bar">
      <input
        v-model="search"
        class="search-input"
        placeholder="Rechercher dans ce genre…"
        @input="onSearch"
      />
    </div>

    <!-- Tracks -->
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!tracks.length" class="state">Aucun track.</div>
    <div v-else class="track-list">
      <RouterLink
        v-for="t in tracks"
        :key="t.id"
        :to="`/catalog/${t.id}`"
        class="track-row"
      >
        <div class="cover-thumb">
          <img v-if="t.has_artwork" :src="`/storage/catalog-artworks/${t.id}.jpg`" />
          <span v-else class="fallback">{{ (t.title || '?')[0] }}</span>
        </div>
        <div class="track-info">
          <span class="track-title">{{ t.title }}</span>
          <span class="track-artist">{{ t.artist }}</span>
        </div>
        <span v-if="t.bpm" class="track-meta mono">{{ Math.round(t.bpm) }}</span>
        <span v-if="t.key" class="track-meta mono">{{ t.key }}</span>
        <span v-if="t.in_lib" class="lib-badge">IN LIB</span>
      </RouterLink>
    </div>

    <!-- Pagination -->
    <div v-if="total > limit" class="pagination">
      <button :disabled="skip === 0" class="btn-page" @click="goPage(-1)">← Précédent</button>
      <span class="page-info mono">{{ Math.floor(skip / limit) + 1 }} / {{ Math.ceil(total / limit) }}</span>
      <button :disabled="skip + limit >= total" class="btn-page" @click="goPage(1)">Suivant →</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import StyleTag from '../components/StyleTag.vue'

const route = useRoute()
const genreName = ref(decodeURIComponent(route.params.genre || ''))
const tracks = ref([])
const total = ref(0)
const loading = ref(false)
const search = ref('')
const skip = ref(0)
const limit = 50
let searchTimer = null

async function fetchTracks() {
  loading.value = true
  try {
    const params = { genre: genreName.value, skip: skip.value, limit }
    if (search.value.trim()) params.search = search.value.trim()
    const { data } = await axios.get('/api/catalog/', { params })
    tracks.value = data.items
    total.value = data.total
  } catch {
    tracks.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onSearch() {
  clearTimeout(searchTimer)
  skip.value = 0
  searchTimer = setTimeout(fetchTracks, 300)
}

function goPage(dir) {
  skip.value = Math.max(0, skip.value + dir * limit)
  fetchTracks()
}

watch(() => route.params.genre, (g) => {
  genreName.value = decodeURIComponent(g || '')
  skip.value = 0
  search.value = ''
  fetchTracks()
})

onMounted(fetchTracks)
</script>

<style scoped>
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 900px;
}
.view-header {
  margin-bottom: 20px;
}
.back-link {
  font: 400 12px/1 var(--font-ui);
  color: var(--ink-3);
  text-decoration: none;
  display: inline-block;
  margin-bottom: 10px;
}
.back-link:hover { color: var(--ink); }
.genre-header {
  display: flex;
  align-items: center;
  gap: 14px;
}
.genre-total {
  font: 400 13px/1 var(--font-mono);
  color: var(--ink-3);
}

.search-bar {
  margin-bottom: 16px;
}
.search-input {
  width: 100%;
  max-width: 400px;
  padding: 8px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink);
  font: 400 13px/1.4 var(--font-ui);
}
.search-input:focus {
  outline: none;
  border-color: var(--accent);
}

.track-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.track-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: var(--r-sm);
  text-decoration: none;
  color: var(--ink);
  transition: background 0.1s;
}
.track-row:hover {
  background: var(--surface-2);
}
.cover-thumb {
  width: 36px;
  height: 36px;
  border-radius: 4px;
  background: var(--surface-2);
  border: 1px solid var(--line);
  overflow: hidden;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover-thumb img { width: 100%; height: 100%; object-fit: cover; }
.fallback { font: 600 14px/1 var(--font-ui); color: var(--ink-3); }
.track-info {
  flex: 1;
  min-width: 0;
}
.track-title {
  display: block;
  font: 500 13px/1.2 var(--font-ui);
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track-artist {
  display: block;
  font: 400 11px/1.2 var(--font-ui);
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track-meta {
  font: 400 11px/1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}
.lib-badge {
  font: 600 9px/1 var(--font-mono);
  letter-spacing: 0.08em;
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: 3px 6px;
  border-radius: 4px;
  white-space: nowrap;
}
.mono { font-family: var(--font-mono); }

.pagination {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
  justify-content: center;
}
.btn-page {
  padding: 6px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 12px/1 var(--font-ui);
  cursor: pointer;
}
.btn-page:disabled { opacity: 0.4; cursor: default; }
.btn-page:hover:not(:disabled) { background: var(--surface-2); }
.page-info {
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
}
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>
