<template>
  <div
    v-if="open"
    class="add-overlay"
    :class="{ 'add-overlay--sheet': bottomSheet }"
    @click.self="close"
  >
    <div class="add-modal" role="dialog" aria-modal="true" :aria-label="title">
      <div class="add-modal-head">
        <h2 class="add-modal-title">{{ title }}</h2>
        <button class="add-modal-x" type="button" aria-label="Fermer" @click="close">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
          </svg>
        </button>
      </div>
      <!-- Body : each view supplies its own fields (Sets = 2 tabs, Watchlist = 1 URL). -->
      <slot />
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  // Opt-in : dock the card to the bottom on mobile (Watchlist). position: fixed
  // is the one sanctioned @media exception, so it lives here, gated by the prop.
  bottomSheet: { type: Boolean, default: false },
})
const emit = defineEmits(['update:open'])

function close() {
  emit('update:open', false)
}

// Escape closes the modal — only acts while open (mirrors the per-view keydown
// handler this component replaces). The listener is cheap and always attached.
function onKeydown(e) {
  if (e.key === 'Escape' && props.open) close()
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.add-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--overlay-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6);
}
.add-modal {
  width: min(460px, 100vw - 32px);
  max-height: min(88vh, 720px);
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.add-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.add-modal-title {
  margin: 0;
  font: 700 var(--fs-md) / 1.2 var(--font-ui);
  color: var(--ink);
}
.add-modal-x {
  width: 30px;
  height: 30px;
  flex: none;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
}
.add-modal-x:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.add-modal-x svg {
  width: 16px;
  height: 16px;
}

/* Bottom-sheet on mobile (opt-in via the `bottom-sheet` prop). position: fixed
   is the sanctioned @media exception — it previously lived in WatchlistView. */
@media (max-width: 640px) {
  .add-overlay--sheet {
    align-items: flex-end;
    padding: 0;
  }
  .add-overlay--sheet .add-modal {
    width: 100%;
    max-width: none;
    max-height: 90vh;
    border-radius: var(--r-xl) var(--r-xl) 0 0;
    border-bottom: 0;
  }
}
</style>
