<template>
  <span class="src-badge" :class="source.toLowerCase()">{{ source.toUpperCase() }}</span>
</template>

<script setup>
defineProps({
  source: { type: String, required: true },
})
</script>

<style scoped>
.src-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 7px;
  border-radius: 4px;
  font: 600 10px/1 var(--font-mono);
  letter-spacing: 0.06em;
  white-space: nowrap;
  flex: none;
}
.src-badge.deezer {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.src-badge.tidal {
  background: var(--surface-3);
  color: var(--ink-2);
  border: 1px solid var(--line-2);
}
.src-badge.spotify {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
</style>
