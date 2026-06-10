<template>
  <span class="style-tag" :style="{ '--th': tone.hue, '--ts': tone.shade }">
    {{ name }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { styleTone } from '../composables/useStyleMap.js'

const props = defineProps({
  name: { type: String, required: true },
})

const tone = computed(() => styleTone(props.name))
</script>

<style scoped>
.style-tag {
  --th: 0;
  --ts: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: oklch(calc(var(--tag-bg-l) + var(--ts)) var(--tag-bg-c) var(--th));
  color: oklch(calc(var(--tag-fg-l) - var(--ts)) var(--tag-fg-c) var(--th));
  font: 500 11.5px/1 var(--font-ui);
  letter-spacing: 0.005em;
  padding: 3px 9px 3px 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.style-tag::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: oklch(calc(var(--tag-dot-l) + var(--ts)) var(--tag-dot-c) var(--th));
  flex: none;
}
</style>
