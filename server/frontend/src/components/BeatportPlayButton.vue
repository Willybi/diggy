<template>
  <!-- Same footprint as the Deezer play button (30px round, ▶ glyph) but a
       DISTINCT Beatport identity (green ring + tooltip): clicking opens the
       docked embed bar, it never starts audio directly. @click.stop because
       the button lives above stretched NavCover links in the listing rows. -->
  <button
    class="bpp-btn"
    type="button"
    aria-label="Extrait Beatport"
    title="Extrait Beatport"
    @click.stop="onClick"
  >
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M8 5.5v13l11-6.5z" />
    </svg>
  </button>
</template>

<script setup>
import { useBeatportBar } from '../stores/beatportBar.js'

const props = defineProps({
  // Row-shaped track; needs beatport_id (+ id/catalog_id, title, artist).
  track: { type: Object, required: true },
})

const bar = useBeatportBar()

function onClick() {
  bar.open(props.track)
}
</script>

<style scoped>
.bpp-btn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--chart-beatport);
  background: var(--surface);
  color: var(--chart-beatport);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}
.bpp-btn:hover {
  background: var(--chart-beatport);
  color: var(--on-accent);
}
.bpp-btn:focus-visible {
  outline: 2px solid var(--chart-beatport);
  outline-offset: 2px;
}
.bpp-btn svg {
  width: 11px;
  height: 11px;
}
</style>
