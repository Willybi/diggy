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
  gap: 2px;
  background: var(--surface-2);
  padding: 3px;
  border-radius: var(--r-sm);
}
.filterseg button {
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  padding: 8px 14px;
  border-radius: var(--r-xs);
  cursor: pointer;
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
</style>
