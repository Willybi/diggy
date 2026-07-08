<template>
  <component :is="to ? 'RouterLink' : 'div'" :to="to" class="appear-row">
    <div class="appear-info">
      <span class="appear-title">{{ title }}</span>
      <span v-if="subtitle" class="appear-sub">{{ subtitle }}</span>
    </div>
    <span v-if="to" class="appear-arrow">&#8250;</span>
  </component>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: null },
  to: { type: String, default: null },
})
</script>

<style scoped>
.appear-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-25) var(--space-3);
  border-bottom: 1px solid var(--line);
  text-decoration: none;
  color: inherit;
  transition: background 0.1s;
}
.appear-row:last-child {
  border-bottom: none;
}
.appear-row:hover {
  background: var(--surface-2);
}
.appear-info {
  min-width: 0;
  flex: 1;
}
.appear-title {
  display: block;
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.appear-sub {
  display: block;
  font: 400 var(--fs-sm)/1.3 var(--font-mono);
  color: var(--ink-3);
  margin-top: var(--space-05);
}
.appear-arrow {
  flex: none;
  font-size: var(--fs-md);
  color: var(--ink-3);
  margin-left: var(--space-2);
}
</style>
