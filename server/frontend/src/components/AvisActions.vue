<template>
  <span class="acts">
    <span
      class="act dislike"
      :class="{ on: modelValue === 'disliked' }"
      title="Dislike"
      @click.stop="toggle('disliked')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M7 10.5V19a1 1 0 0 0 1.5.9l1.2-.7a2 2 0 0 0 1-1.4l.6-3.3h4.9a2 2 0 0 0 2-2.4l-1-5A2 2 0 0 0 14.2 3H7M7 10.5H4.5a1.5 1.5 0 0 1-1.5-1.5v-4A1.5 1.5 0 0 1 4.5 3.5H7z" stroke-linejoin="round"/></svg>
    </span>
    <span
      class="act like"
      :class="{ on: modelValue === 'liked' }"
      title="Like"
      @click.stop="toggle('liked')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20s-7-4.4-7-9.3A3.7 3.7 0 0 1 12 8a3.7 3.7 0 0 1 7 2.7C19 15.6 12 20 12 20z" stroke-linejoin="round"/></svg>
    </span>
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
.acts {
  display: inline-flex;
  gap: 6px;
  justify-content: flex-end;
}
.act {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer;
  transition: opacity .12s, color .12s, background .12s, border-color .12s;
  opacity: 0;
}
tr:hover .act { opacity: 1; }
.act svg { width: 16px; height: 16px; }
.act.like:hover { color: var(--pos); border-color: var(--pos); }
.act.dislike:hover { color: var(--neg); border-color: var(--neg); }
.act.on { opacity: 1; }
.act.like.on { background: var(--pos-soft); border-color: transparent; color: var(--pos-ink); }
.act.dislike.on { background: var(--neg-soft); border-color: transparent; color: var(--neg-ink); }
</style>
