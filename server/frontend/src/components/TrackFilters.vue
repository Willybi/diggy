<template>
  <div class="filter-bar">
    <label class="filter-field">
      <span class="label">Style</span>
      <select :value="styleFilter" @change="$emit('update:styleFilter', $event.target.value)">
        <option value="">Tous</option>
        <option v-for="s in allStyles" :key="s" :value="s">{{ s }}</option>
      </select>
    </label>

    <label class="filter-field">
      <span class="label">BPM min</span>
      <input type="number" :value="bpmMin" min="60" max="200" step="1"
        @input="$emit('update:bpmMin', Number($event.target.value) || null)"
        placeholder="—"
      />
    </label>

    <label class="filter-field">
      <span class="label">BPM max</span>
      <input type="number" :value="bpmMax" min="60" max="200" step="1"
        @input="$emit('update:bpmMax', Number($event.target.value) || null)"
        placeholder="—"
      />
    </label>

    <button class="chip-toggle" :class="{ 'is-on': inLibOnly }"
      @click="$emit('update:inLibOnly', !inLibOnly)"
    >
      <span class="switch" />
      In lib only
    </button>
  </div>
</template>

<script setup>
import { FAMILY_MEMBERS } from '../composables/useStyleMap.js'

defineProps({
  styleFilter: { type: String,  default: '' },
  bpmMin:      { type: Number,  default: null },
  bpmMax:      { type: Number,  default: null },
  inLibOnly:   { type: Boolean, default: false },
})

defineEmits(['update:styleFilter', 'update:bpmMin', 'update:bpmMax', 'update:inLibOnly'])

const allStyles = Object.values(FAMILY_MEMBERS).flat()
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.filter-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  padding: 7px 11px;
  font-size: 13px;
  color: var(--ink-2);
  cursor: pointer;
  transition: border-color 0.12s;
}
.filter-field:hover {
  border-color: var(--ink-3);
}
.label {
  font: 500 10.5px/1 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.filter-field select,
.filter-field input {
  border: none;
  background: transparent;
  font: inherit;
  color: var(--ink);
  font-weight: 500;
  outline: none;
  cursor: pointer;
  min-width: 0;
  width: 80px;
}
.filter-field input[type="number"] {
  width: 60px;
  font-family: var(--font-mono);
}
/* hide number spinners */
.filter-field input[type="number"]::-webkit-inner-spin-button,
.filter-field input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
}

.chip-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 13px 7px 11px;
  border-radius: 999px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  font: 500 13px/1 var(--font-ui);
  color: var(--ink-2);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.chip-toggle.is-on {
  background: var(--pos-soft);
  border-color: transparent;
  color: var(--pos-ink);
}
.switch {
  width: 30px;
  height: 18px;
  border-radius: 999px;
  background: var(--line-2);
  position: relative;
  transition: background 0.18s;
  flex: none;
}
.chip-toggle.is-on .switch {
  background: var(--pos);
}
.switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--surface);
  transition: left 0.18s;
  box-shadow: var(--shadow-sm);
}
.chip-toggle.is-on .switch::after {
  left: 14px;
}
</style>
