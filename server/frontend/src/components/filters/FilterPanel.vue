<template>
  <section class="fpanel">
    <div class="fpanel-grid">
      <slot />
    </div>
    <footer class="fpanel-foot">
      <span class="fpanel-count">{{ countText }}</span>
      <span class="fpanel-actions">
        <button class="btn btn--sm" type="button" @click="emit('reset')">Réinitialiser</button>
        <button class="btn btn--sm btn--accent" type="button" @click="emit('close')">Fermer</button>
      </span>
    </footer>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import './filter-fields.css'

const props = defineProps({
  resultCount: { type: Number, default: null },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['reset', 'close'])

const countText = computed(() => {
  if (props.loading) return '…'
  if (props.resultCount == null) return ''
  const n = props.resultCount
  return `${n.toLocaleString('fr-FR')} ${n > 1 ? 'résultats' : 'résultat'}`
})
</script>

<style scoped>
/* Inline card: pushes the content below, never an overlay. Plain show/hide
   (no height animation) — transitions stay reserved to hover/selected states. */
.fpanel {
  container-type: inline-size;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  padding: var(--space-5);
}
.fpanel-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: var(--space-4) var(--space-5);
}
@container (max-width: 859px) {
  .fpanel-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .fpanel-grid > :deep(.flt-field) {
    grid-column: span 1;
  }
  .fpanel-grid > :deep(.flt-field--4),
  .fpanel-grid > :deep(.flt-field--6) {
    grid-column: 1 / -1;
  }
}
@container (max-width: 699px) {
  .fpanel-grid {
    grid-template-columns: 1fr;
  }
  .fpanel-grid > :deep(.flt-field),
  .fpanel-grid > :deep(.flt-field--4),
  .fpanel-grid > :deep(.flt-field--6) {
    grid-column: 1 / -1;
  }
}

.fpanel-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--line);
}
.fpanel-count {
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
}
.fpanel-actions {
  display: flex;
  gap: var(--space-2);
}
</style>
