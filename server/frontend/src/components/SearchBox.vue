<template>
  <label class="search" aria-label="Rechercher">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.2-3.2" stroke-linecap="round" />
    </svg>
    <input v-model="inner" type="text" :placeholder="placeholder" @input="onInput" />
    <button v-if="inner" class="clear-btn" type="button" aria-label="Effacer" @click="clear">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
      </svg>
    </button>
  </label>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Rechercher...' },
  debounce: { type: Number, default: 300 },
})
const emit = defineEmits(['update:modelValue'])

const inner = ref(props.modelValue)
let timer = null

watch(
  () => props.modelValue,
  (v) => {
    if (v !== inner.value) inner.value = v
  },
)

function onInput() {
  clearTimeout(timer)
  timer = setTimeout(() => emit('update:modelValue', inner.value), props.debounce)
}

function clear() {
  inner.value = ''
  clearTimeout(timer)
  emit('update:modelValue', '')
}
</script>

<style scoped>
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 0 12px;
  height: 38px;
  min-width: 220px;
  cursor: text;
}
.search svg {
  width: 16px;
  height: 16px;
  color: var(--ink-3);
  flex: none;
}
.search input {
  border: 0;
  background: transparent;
  outline: none;
  width: 100%;
  font: 400 14px var(--font-ui);
  color: var(--ink);
}
.search input::placeholder {
  color: var(--ink-3);
}
.clear-btn {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  color: var(--ink-3);
  display: grid;
  place-items: center;
  flex: none;
}
.clear-btn:hover {
  color: var(--ink);
}
.clear-btn svg {
  width: 14px;
  height: 14px;
}
</style>
