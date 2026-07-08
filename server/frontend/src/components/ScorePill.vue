<template>
  <span class="score-pill">
    <span class="meter">
      <span class="meter-fill" :style="{ width: score * 10 + '%' }" />
    </span>
    <span class="meter-text">{{ formatScore(score) }}</span
    ><span class="total">/10</span>
  </span>
</template>

<script setup>
defineProps({
  score: { type: Number, required: true },
})

function formatScore(s) {
  return s % 1 === 0 ? s.toString() : s.toFixed(1)
}
</script>

<style scoped>
.score-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-radius: var(--r-xs);
  padding: var(--space-1) var(--space-25) var(--space-1) var(--space-2);
  font: 500 var(--fs-sm)/1 var(--font-mono);
}
.meter {
  flex: none;
  width: 50px;
  height: 11px;
  border-radius: 2px;
  background: color-mix(in srgb, currentColor 20%, transparent);
  position: relative;
  overflow: hidden;
}
.meter-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: currentColor;
  border-radius: 2px;
  transition: width 0.3s ease;
}
.total {
  opacity: 0.5;
}
</style>
