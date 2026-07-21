<template>
  <div class="sms" :class="{ 'sms--drawer': variant === 'drawer' }">
    <div v-for="group in groups" :key="group.pillar" class="sms-row">
      <span class="sms-pillar">{{ group.label }}</span>
      <div class="sms-chips">
        <button
          v-for="item in group.items"
          :key="item.name"
          type="button"
          class="sms-chip"
          :class="{ on: isOn(item.name) }"
          v-bind="item.attrs"
          :aria-pressed="isOn(item.name)"
          @click="toggleStyle(item.name)"
        >
          <span class="sms-dot"></span>
          <span class="sms-name">{{ item.name }}</span>
          <span v-if="item.count != null" class="sms-count">{{ item.count }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { styleTone, tagAttrs, PILLAR_ORDER, PILLAR_LABELS } from '../../composables/useStyleMap.js'

const props = defineProps({
  // Selected genre names.
  modelValue: { type: Array, default: () => [] },
  // Flat list { name, count, pillar, depth } (GET /api/catalog/genres) —
  // the component groups by pillar itself, fixed pillar order, empty pillar omitted.
  options: { type: Array, default: () => [] },
  variant: { type: String, default: 'panel' }, // 'panel' (24px) | 'drawer' (30px)
})
const emit = defineEmits(['update:modelValue'])

const groups = computed(() => {
  const byPillar = new Map(PILLAR_ORDER.map((p) => [p, []]))
  for (const opt of props.options) {
    const tone = styleTone(opt)
    byPillar.get(tone.pillar).push({ ...opt, attrs: tagAttrs(tone) })
  }
  return PILLAR_ORDER.filter((p) => byPillar.get(p).length).map((p) => ({
    pillar: p,
    label: PILLAR_LABELS[p],
    items: byPillar.get(p),
  }))
})

function isOn(name) {
  return props.modelValue.includes(name)
}

function toggleStyle(name) {
  const next = isOn(name) ? props.modelValue.filter((v) => v !== name) : [...props.modelValue, name]
  emit('update:modelValue', next)
}
</script>

<style scoped>
.sms {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.sms-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}
.sms-pillar {
  flex: none;
  width: 78px;
  font: 500 var(--fs-nano) var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-3);
}
.sms-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  min-width: 0;
}

/* Pillar hue formulas — same as StyleTag (bg/fg/dot from --tag-*-l/c, chroma
   attenuated by depth --d, hue per pillar; Autres = chroma 0). */
.sms-chip[data-fam='house'] {
  --th: var(--hue-house);
}
.sms-chip[data-fam='techno'] {
  --th: var(--hue-techno);
}
.sms-chip[data-fam='trance'] {
  --th: var(--hue-trance);
}
.sms-chip[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.sms-chip[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.sms-chip[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.sms-chip[data-fam='autres'] {
  --th: 0;
  --tag-bg-c: 0;
  --tag-fg-c: 0;
  --tag-dot-c: 0;
}

.sms-chip {
  --th: 0;
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 24px;
  padding: 0 var(--space-25) 0 var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--r-pill);
  background: oklch(var(--tag-bg-l) calc(var(--tag-bg-c) * (1 - 0.17 * var(--d, 0))) var(--th));
  color: oklch(var(--tag-fg-l) calc(var(--tag-fg-c) * (1 - 0.1 * var(--d, 0))) var(--th));
  font: 500 var(--fs-xs) var(--font-ui);
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color 0.12s,
    box-shadow 0.12s;
}
.sms--drawer .sms-chip {
  height: 30px;
}
.sms-chip:hover {
  box-shadow: 0 0 0 1px var(--line-2);
}
/* Selected = accent ring, pillar colour preserved (principle 4). */
.sms-chip.on {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}
.sms-chip:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.sms-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
  background: oklch(
    calc(var(--tag-dot-l) + 0.04 * var(--d, 0)) calc(var(--tag-dot-c) * (1 - 0.19 * var(--d, 0)))
      var(--th)
  );
}
.sms-name {
  overflow: hidden;
  text-overflow: ellipsis;
}
.sms-count {
  font: 500 var(--fs-nano) var(--font-mono);
  opacity: 0.75;
}
</style>
