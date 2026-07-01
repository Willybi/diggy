<template>
  <span class="artist-links">
    <template v-if="artists?.length">
      <template v-for="(a, i) in artists" :key="a.id">
        <span v-if="i > 0 && a.role === 'featured'" class="art-sep"> feat. </span>
        <span v-else-if="i > 0" class="art-sep">, </span>
        <RouterLink :to="`/artist/${a.id}`" class="art-link">{{ a.name }}</RouterLink>
      </template>
    </template>
    <span v-else>{{ fallback }}</span>
  </span>
</template>

<script setup>
defineProps({
  artists: { type: Array, default: () => [] },
  fallback: { type: String, default: '' },
})
</script>

<style scoped>
.artist-links {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.art-link {
  color: inherit;
  text-decoration: none;
}
.art-link:hover {
  text-decoration: underline;
  color: var(--accent);
}
.art-sep {
  color: var(--ink-3);
}
</style>
