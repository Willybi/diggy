<template>
  <div>
    <h1>Tracks ({{ total }})</h1>
    <input v-model="search" placeholder="Rechercher un artiste..." @input="fetchTracks" />
    <table v-if="tracks.length">
      <thead>
        <tr>
          <th>Titre</th><th>Artiste</th><th>BPM</th><th>Key</th><th>Rating</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in tracks" :key="t.id">
          <td>{{ t.title }}</td>
          <td>{{ t.artist }}</td>
          <td>{{ t.bpm }}</td>
          <td>{{ t.key }}</td>
          <td>{{ t.rating }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else>Aucun track.</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const tracks = ref([])
const total = ref(0)
const search = ref('')

async function fetchTracks() {
  const params = search.value ? { artist: search.value } : {}
  const { data } = await axios.get('/api/tracks/', { params })
  tracks.value = data.items
  total.value = data.total
}

onMounted(fetchTracks)
</script>

<style scoped>
h1 { margin-bottom: 1rem; }
input { margin-bottom: 1rem; padding: 0.4rem; background: #222; color: #eee; border: 1px solid #444; border-radius: 4px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #333; text-align: left; }
th { background: #222; }
</style>
