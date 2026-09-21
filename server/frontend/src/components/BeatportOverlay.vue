<template>
  <AddModal
    :open="overlay.visible"
    title="Extrait Beatport"
    bottom-sheet
    @update:open="onOpenChange"
  >
    <div v-if="overlay.track" class="bpo-body">
      <div class="bpo-track">
        <span class="bpo-title">{{ overlay.track.title }}</span>
        <span v-if="overlay.track.artist" class="bpo-artist">{{ overlay.track.artist }}</span>
      </div>
      <!-- Official embed, eager: the modal is visible by construction, the
           lazy IntersectionObserver would only flash the placeholder. The
           iframe stays a black box — no autoplay, no audio bridge, ever. -->
      <BeatportEmbed :beatport-id="overlay.track.beatport_id" eager />
    </div>
  </AddModal>
</template>

<script setup>
import AddModal from './AddModal.vue'
import BeatportEmbed from './BeatportEmbed.vue'
import { useBeatportOverlay } from '../stores/beatportOverlay.js'

const overlay = useBeatportOverlay()

// AddModal only ever emits update:open=false (✕ button, backdrop, Escape).
function onOpenChange(open) {
  if (!open) overlay.close()
}
</script>

<style scoped>
.bpo-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.bpo-track {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.bpo-title {
  font: 600 var(--fs-base) / 1.25 var(--font-ui);
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bpo-artist {
  font: 400 var(--fs-sm) / 1.25 var(--font-ui);
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
