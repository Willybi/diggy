<template>
  <label class="si" :class="{ 'si--drawer': variant === 'drawer', 'is-disabled': disabled }">
    <svg
      v-if="icon"
      class="si-loupe"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.2-3.2" stroke-linecap="round" />
    </svg>
    <input
      v-model="inner"
      class="si-input"
      type="text"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="onInput"
    />
  </label>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Rechercher…' },
  // Label variant: no magnifier, example placeholder provided by the page.
  icon: { type: Boolean, default: true },
  debounce: { type: Number, default: 250 },
  variant: { type: String, default: 'panel' }, // 'panel' | 'drawer' (44px target)
  disabled: { type: Boolean, default: false },
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
  timer = setTimeout(emitValue, props.debounce)
}

function emitValue() {
  emit('update:modelValue', inner.value)
}

onUnmounted(() => clearTimeout(timer))
</script>

<style scoped>
.si {
  position: relative;
  display: block;
  width: 100%;
}
.si-loupe {
  position: absolute;
  left: var(--space-25);
  top: 50%;
  transform: translateY(-50%);
  width: 15px;
  height: 15px;
  color: var(--ink-3);
  pointer-events: none;
}
.si-input {
  width: 100%;
  height: 38px;
  padding: 0 var(--space-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  font: 400 var(--fs-input) var(--font-ui);
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.si-loupe + .si-input {
  padding-left: 34px;
}
.si-input::placeholder {
  color: var(--ink-3);
}
.si-input:focus {
  outline: none;
  border-color: var(--accent);
}
.si--drawer .si-input {
  height: var(--touch-min);
}
.is-disabled {
  opacity: 0.45;
  pointer-events: none;
}
</style>
