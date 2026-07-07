<template>
  <span class="style-tag" v-bind="attrs" :title="name">
    <span class="dot"></span><span class="lbl">{{ shortLabel }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { styleTone, tagAttrs } from '../composables/useStyleMap.js'

const props = defineProps({
  name: { type: String, required: true },
  family: { type: String, default: 'autres' },
  depth: { type: Number, default: 0 },
})

const tone = computed(() => styleTone({ pillar: props.family, depth: props.depth }))
const attrs = computed(() => tagAttrs(tone.value))
const shortLabel = computed(() => props.name.split('/')[0].trim())
</script>

<style scoped>
.style-tag[data-fam='house'] {
  --th: var(--hue-house);
}
.style-tag[data-fam='techno'] {
  --th: var(--hue-techno);
}
.style-tag[data-fam='trance'] {
  --th: var(--hue-trance);
}
.style-tag[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.style-tag[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.style-tag[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.style-tag[data-fam='autres'] {
  --th: 0;
  --tag-bg-c: 0;
  --tag-fg-c: 0;
  --tag-dot-c: 0;
}

.style-tag {
  --th: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  max-width: 100%;
  background: oklch(var(--tag-bg-l) calc(var(--tag-bg-c) * (1 - 0.17 * var(--d, 0))) var(--th));
  color: oklch(var(--tag-fg-l) calc(var(--tag-fg-c) * (1 - 0.1 * var(--d, 0))) var(--th));
  font: 500 12px var(--font-ui);
  white-space: nowrap;
  padding: 4px 10px 4px 8px;
  border-radius: var(--r-pill);
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
  background: oklch(
    calc(var(--tag-dot-l) + 0.04 * var(--d, 0)) calc(var(--tag-dot-c) * (1 - 0.19 * var(--d, 0)))
      var(--th)
  );
  box-shadow: 0 0 0 1px
    oklch(
      calc(var(--tag-dot-l) + 0.04 * var(--d, 0)) calc(var(--tag-dot-c) * (1 - 0.19 * var(--d, 0)))
        var(--th) / 0.28
    );
}
</style>
