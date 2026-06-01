<template>
  <div>
    <h1>Tags</h1>
    <div v-if="grouped" v-for="(tags, group) in grouped" :key="group" class="group">
      <h2>{{ group }}</h2>
      <span v-for="tag in tags" :key="tag.id" class="tag">{{ tag.name }}</span>
    </div>
    <p v-else>Aucun tag.</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const tags = ref([])

const grouped = computed(() => {
  if (!tags.value.length) return null
  return tags.value.reduce((acc, tag) => {
    if (!acc[tag.group]) acc[tag.group] = []
    acc[tag.group].push(tag)
    return acc
  }, {})
})

onMounted(async () => {
  const { data } = await axios.get('/api/tags/')
  tags.value = data
})
</script>

<style scoped>
h1 { margin-bottom: 1rem; }
.group { margin-bottom: 1.5rem; }
h2 { font-size: 0.85rem; text-transform: uppercase; color: #888; margin-bottom: 0.5rem; }
.tag { display: inline-block; background: #2a2a2a; border: 1px solid #444; border-radius: 12px; padding: 0.2rem 0.6rem; margin: 0.2rem; font-size: 0.9rem; }
</style>
