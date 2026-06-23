<template>
  <span class="ld" :class="{ engaged: modelValue != null }">
    <button
      class="ld-btn like"
      :class="{ on: modelValue === 'liked' }"
      title="Like"
      @click.stop.prevent="toggle('liked')"
    >
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
      </svg>
    </button>
    <button
      class="ld-btn dislike"
      :class="{ on: modelValue === 'disliked' }"
      title="Dislike"
      @click.stop.prevent="toggle('disliked')"
    >
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M15 3H6c-.83 0-1.54.5-1.84 1.22l-3.02 7.05c-.09.23-.14.47-.14.73v2c0 1.1.9 2 2 2h6.31l-.95 4.57c-.02.1-.03.2-.03.31 0 .41.17.79.44 1.06L9.83 23l6.59-6.59c.36-.36.58-.86.58-1.41V5c0-1.1-.9-2-2-2zm4 0v12h4V3h-4z"/>
      </svg>
    </button>
  </span>
</template>

<script setup>
const props = defineProps({ modelValue: { type: String, default: null } })
const emit = defineEmits(['update:modelValue'])

function toggle(val) {
  emit('update:modelValue', props.modelValue === val ? null : val)
}
</script>

<style scoped>
.ld {
  display: inline-flex;
  gap: 6px;
  justify-content: flex-end;
}
.ld-btn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer;
  padding: 0;
  transition: opacity .14s, color .14s, background .14s, border-color .14s;
  opacity: 0;
}
.ld-btn svg { width: 14px; height: 14px; }

/* Show on hover of various parent contexts */
tr:hover .ld-btn,
.artist-card:hover .ld-btn,
.genre-card:hover .ld-btn { opacity: 1; }

/* Always show when engaged */
.ld-btn.on { opacity: 1; }

/* Hover colors */
.ld-btn.like:hover { color: var(--pos); border-color: var(--pos); }
.ld-btn.dislike:hover { color: var(--neg); border-color: var(--neg); }

/* Active states */
.ld-btn.like.on {
  background: var(--pos-soft);
  border-color: transparent;
  color: var(--pos-ink);
}
.ld-btn.dislike.on {
  background: var(--neg-soft);
  border-color: transparent;
  color: var(--neg-ink);
}
</style>
