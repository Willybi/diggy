<template>
  <div class="tags-view">
    <header class="view-header">
      <h1 class="view-title">Genres</h1>
      <span class="view-sub">{{ genres.length }} genres</span>
    </header>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!genres.length" class="state">Aucun genre.</div>
    <div v-else class="genre-grid">
      <RouterLink
        v-for="g in genres"
        :key="g.name"
        :to="`/style/${encodeURIComponent(g.name)}`"
        class="genre-card"
      >
        <StyleTag :name="g.name" />
        <span class="genre-count">{{ g.count }} {{ g.count === 1 ? 'track' : 'tracks' }}</span>
      </RouterLink>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import StyleTag from '../components/StyleTag.vue'

const genres  = ref([])
const loading = ref(false)

async function fetchGenres() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/catalog/genres')
    genres.value = data
  } catch {
    genres.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchGenres)
</script>

<style scoped>
.tags-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
}
.view-header {
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
.genre-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.genre-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  text-decoration: none;
  transition: background 0.12s, border-color 0.12s;
}
.genre-card:hover {
  background: var(--surface-2);
  border-color: var(--accent);
}
.genre-count {
  margin-left: auto;
  font: 400 12px/1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>
