<template>
  <div class="filterseg">
    <button
      v-for="opt in options"
      :key="opt.value"
      :class="[opt.cls, { on: modelValue === opt.value }]"
      @click="emit('update:modelValue', opt.value)"
    >
      {{ opt.count != null ? `${opt.label} (${opt.count})` : opt.label }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, required: true },
  options: { type: Array, required: true },
})
const emit = defineEmits(['update:modelValue'])
</script>

<style scoped>
.filterseg {
  display: flex;
  gap: var(--space-05);
  background: var(--surface-2);
  padding: var(--space-05);
  border-radius: var(--r-sm);
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.filterseg::-webkit-scrollbar {
  display: none;
}
.filterseg button {
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-xs);
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.filterseg button:hover {
  color: var(--ink);
}
.filterseg button.on {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.filterseg button.liked.on {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.filterseg button.disliked.on {
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.filterseg button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
