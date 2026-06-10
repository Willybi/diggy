<template>
  <div class="tags-view">
    <header class="view-header">
      <h1 class="view-title">Style Tags</h1>
      <span class="view-sub">{{ tags.length }} styles</span>
    </header>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!tags.length" class="state">Aucun tag.</div>
    <div v-else class="tags-grid">
      <StyleTag v-for="tag in tags" :key="tag" :name="tag" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import StyleTag from '../components/StyleTag.vue'

const tags    = ref([])
const loading = ref(false)

async function fetchTags() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/tracks/tags')
    tags.value = data
  } catch {
    tags.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchTags)
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
.tags-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
}
</style>
