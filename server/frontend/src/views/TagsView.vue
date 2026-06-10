<template>
  <div>
    <h1>Tags</h1>
    <div v-if="tags.length">
      <span v-for="tag in tags" :key="tag" class="tag">{{ tag }}</span>
    </div>
    <p v-else>Aucun tag.</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const tags = ref([])

onMounted(async () => {
  const { data } = await axios.get('/api/tracks/tags')
  tags.value = data
})
</script>

<style scoped>
h1 { margin-bottom: 1rem; }
.group { margin-bottom: 1.5rem; }
h2 { font-size: 0.85rem; text-transform: uppercase; color: #888; margin-bottom: 0.5rem; }
.tag { display: inline-block; background: #2a2a2a; border: 1px solid #444; border-radius: 12px; padding: 0.2rem 0.6rem; margin: 0.2rem; font-size: 0.9rem; }
</style>
