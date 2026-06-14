<template>
  <span class="rating">
    <span v-for="n in max" :key="n" class="star" :class="{ 'is-on': n <= value }">★</span>
  </span>
</template>

<script setup>
defineProps({
  value: { type: Number, default: 0 },
  max:   { type: Number, default: 5 },
})
</script>

<style scoped>
.rating { display: inline-flex; gap: 1px; }
.star { font-size: 13px; color: var(--line-2); line-height: 1; }
.star.is-on { color: var(--accent); }
</style>
