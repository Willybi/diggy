<template>
  <span class="ld" :class="{ engaged: modelValue != null }">
    <button
      class="ld-btn dislike"
      :class="{ on: modelValue === 'disliked' }"
      title="Dislike"
      @click.stop.prevent="toggle('disliked')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
        <path d="M17 14V5a1 1 0 0 0-1.5-.9l-1.2.7a2 2 0 0 0-1 1.4l-.6 3.3H7.8a2 2 0 0 0-2 2.4l1 5A2 2 0 0 0 8.8 19H17m0-5h2.5a1.5 1.5 0 0 0 1.5-1.5v-4A1.5 1.5 0 0 0 19.5 5H17z"/>
      </svg>
    </button>
    <button
      class="ld-btn like"
      :class="{ on: modelValue === 'liked' }"
      title="Like"
      @click.stop.prevent="toggle('liked')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
        <path d="M7 10.5V19a1 1 0 0 0 1.5.9l1.2-.7a2 2 0 0 0 1-1.4l.6-3.3h4.9a2 2 0 0 0 2-2.4l-1-5A2 2 0 0 0 14.2 3H7M7 10.5H4.5a1.5 1.5 0 0 1-1.5-1.5v-4A1.5 1.5 0 0 1 4.5 3.5H7z"/>
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
.ld-btn svg { width: 15px; height: 15px; }

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
