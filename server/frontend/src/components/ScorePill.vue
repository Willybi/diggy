<template>
  <span class="score-pill">
    <span class="meter">
      <i v-for="n in 10" :key="n" :class="{ 'is-on': n <= score }" />
    </span>
    {{ score }}<span class="total">/10</span>
  </span>
</template>

<script setup>
defineProps({
  score: { type: Number, required: true },
})
</script>

<style scoped>
.score-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-radius: var(--r-xs);
  padding: 4px 11px 4px 9px;
  font: 500 12px/1 var(--font-mono);
}
.meter {
  display: inline-flex;
  gap: 2px;
}
.meter i {
  width: 3px;
  height: 11px;
  border-radius: 1px;
  background: currentColor;
  opacity: 0.28;
  font-style: normal;
}
.meter i.is-on {
  opacity: 1;
}
.total {
  opacity: 0.5;
}
</style>
