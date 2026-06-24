<template>
  <div class="ld" :data-state="state">
    <button
      class="ld-btn like"
      title="J'aime"
      :aria-pressed="state === 'liked'"
      @click.stop.prevent="toggle('liked')"
    >
      <svg viewBox="0 0 24 24">
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
      </svg>
    </button>
    <button
      class="ld-btn dislike"
      title="Je n'aime pas"
      :aria-pressed="state === 'disliked'"
      @click.stop.prevent="toggle('disliked')"
    >
      <svg viewBox="0 0 24 24">
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
        <path d="M4.5 19.5 22 2"/>
      </svg>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ modelValue: { type: String, default: null } })
const emit = defineEmits(['update:modelValue'])

const state = computed(() => props.modelValue || 'none')

function toggle(val) {
  emit('update:modelValue', props.modelValue === val ? null : val)
}
</script>

<style scoped>
.ld { display: inline-flex; align-items: center; gap: 6px; }
.ld-btn {
  width: 30px; height: 30px; flex: none;
  display: grid; place-items: center;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer; padding: 0;
  transition: color .14s, border-color .14s, background .14s, opacity .16s;
}
.ld-btn svg {
  width: 15px; height: 15px; pointer-events: none; display: block;
  fill: none; stroke: currentColor;
  stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round;
}

.ld-btn.like:hover    { color: var(--pos); border-color: var(--pos); }
.ld-btn.dislike:hover { color: var(--neg); border-color: var(--neg); }

.ld[data-state="liked"] .ld-btn.like {
  background: var(--pos-soft); border-color: transparent; color: var(--pos-ink);
}
.ld[data-state="liked"] .ld-btn.like svg { fill: var(--pos-ink); stroke: var(--pos-ink); }

.ld[data-state="disliked"] .ld-btn.dislike {
  background: var(--neg-soft); border-color: transparent; color: var(--neg-ink);
}
</style>
