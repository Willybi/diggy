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
  margin-top: 24px;
}
.rel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rel-title {
  font: 600 14px/1 var(--font-ui);
  color: var(--ink);
  margin: 0;
  letter-spacing: -0.01em;
}
.rel-count {
  font: 500 11px/1 var(--font-mono);
  color: var(--ink-3);
  background: var(--surface-2);
  padding: 2px 8px;
  border-radius: var(--r-pill);
}
.rel-body {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--surface);
}
</style>
