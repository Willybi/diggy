<template>
  <span
    class="style-tag"
    :class="{ misc: tone.family === 'misc' }"
    :style="tone.family !== 'misc' ? { '--th': tone.hue, '--ts': tone.shade } : undefined"
    :title="name"
  >
    <span class="dot"></span><span class="lbl">{{ shortLabel }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { styleTone } from '../composables/useStyleMap.js'

const props = defineProps({
  name: { type: String, required: true },
})

const tone = computed(() => styleTone(props.name))
const shortLabel = computed(() => props.name.split('/')[0].trim())
</script>

<style scoped>
.style-tag {
  --th: 0;
  --ts: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  max-width: 100%;
  background: oklch(calc(var(--tag-bg-l) + var(--ts)) var(--tag-bg-c) var(--th));
  color: oklch(calc(var(--tag-fg-l) - var(--ts)) var(--tag-fg-c) var(--th));
  font: 500 12px var(--font-ui);
  white-space: nowrap;
  padding: 4px 10px 4px 8px;
  border-radius: 999px;
}
.lbl {
  overflow: hidden;
  text-overflow: ellipsis;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
  background: oklch(calc(var(--tag-dot-l) + var(--ts)) var(--tag-dot-c) var(--th));
}
.style-tag.misc {
  background: var(--surface-2);
  color: var(--ink-2);
}
.style-tag.misc .dot {
  background: var(--ink-3);
}
</style>
