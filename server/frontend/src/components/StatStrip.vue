<template>
  <div class="stat-strip">
    <div v-for="(s, i) in stats" :key="i" class="stat-cell">
      <span class="stat-value">{{ s.value }}</span>
      <span class="stat-label">{{ s.label }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  stats: { type: Array, required: true },
  // each: { label: string, value: string|number }
})
</script>

<style scoped>
.stat-strip {
  display: flex;
  gap: 0;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--surface);
}
.stat-cell {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 16px;
  border-right: 1px solid var(--line);
}
.stat-cell:last-child { border-right: none; }
.stat-value {
  font: 600 15px/1 var(--font-mono);
  color: var(--ink);
}
.stat-label {
  font: 400 10.5px/1 var(--font-mono);
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 4px;
}
</style>
