<template>
  <div v-if="open" class="fdrawer">
    <div class="fdrawer-overlay" @click="close"></div>
    <div class="fdrawer-sheet" role="dialog" aria-modal="true" aria-label="Filtres">
      <div class="fdrawer-handle" aria-hidden="true"></div>
      <header class="fdrawer-head">
        <span class="fdrawer-title">Filtres</span>
        <button class="fdrawer-reset" type="button" @click="emit('reset')">Réinitialiser</button>
      </header>
      <div class="fdrawer-body">
        <slot />
      </div>
      <footer class="fdrawer-foot">
        <button class="btn btn--accent fdrawer-cta" type="button" @click="close">
          {{ ctaText }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed, watch, onUnmounted } from 'vue'
import './filter-fields.css'

const props = defineProps({
  open: { type: Boolean, default: false },
  resultCount: { type: Number, default: null },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['update:open', 'reset'])

// Filtering is already applied live — the CTA only closes.
const ctaText = computed(() => {
  if (props.loading || props.resultCount == null) return 'Afficher les résultats'
  const n = props.resultCount
  return `Afficher ${n.toLocaleString('fr-FR')} ${n > 1 ? 'résultats' : 'résultat'}`
})

function close() {
  emit('update:open', false)
}

function onKeydown(e) {
  if (e.key === 'Escape') close()
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) document.addEventListener('keydown', onKeydown)
    else document.removeEventListener('keydown', onKeydown)
  },
  { immediate: true },
)

onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
/* Assumed exception to the container-query rule: the drawer is position: fixed.
   Above everything except the toasts (9000). */
.fdrawer {
  position: fixed;
  inset: 0;
  z-index: 2000;
}
.fdrawer-overlay {
  position: absolute;
  inset: 0;
  background: var(--overlay-modal);
}
.fdrawer-sheet {
  position: absolute;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
  width: 100%;
  max-width: 430px;
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border: 1px solid var(--line);
  border-bottom: 0;
  border-radius: var(--r-xl) var(--r-xl) 0 0;
  box-shadow: var(--shadow-lg);
}
.fdrawer-handle {
  width: 36px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--line-2);
  margin: var(--space-2) auto 0;
  flex: none;
}
.fdrawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  flex: none;
}
.fdrawer-title {
  font: 600 var(--fs-md) var(--font-ui);
  color: var(--ink);
}
.fdrawer-reset {
  border: 0;
  background: transparent;
  padding: 0;
  font: 500 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
  cursor: pointer;
  transition: color 0.12s;
}
.fdrawer-reset:hover {
  color: var(--ink);
}
.fdrawer-reset:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.fdrawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: 0 var(--space-4) var(--space-5);
  overflow-y: auto;
  min-height: 0;
}
.fdrawer-foot {
  position: sticky;
  bottom: 0;
  flex: none;
  padding: var(--space-3) var(--space-4);
  background: var(--surface);
  border-top: 1px solid var(--line);
}
.fdrawer-cta {
  width: 100%;
  height: var(--touch-min);
  justify-content: center;
}
</style>
