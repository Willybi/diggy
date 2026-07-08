<template>
  <section class="rel-block">
    <header class="rel-header">
      <h2 class="rel-title">{{ title }}</h2>
      <span v-if="count != null" class="rel-count">{{ count }}</span>
    </header>
    <div class="rel-body">
      <slot />
    </div>
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  count: { type: Number, default: null },
})
</script>

<style scoped>
.rel-block {
  margin-top: var(--space-6);
}
.rel-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.rel-title {
  font: 600 var(--fs-base)/1 var(--font-ui);
  color: var(--ink);
  margin: 0;
  letter-spacing: -0.01em;
}
.rel-count {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
  background: var(--surface-2);
  padding: var(--space-05) var(--space-2);
  border-radius: var(--r-pill);
}
.rel-body {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--surface);
}
</style>
