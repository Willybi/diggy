<template>
  <!-- Floating Beatport preview card (D12 v2, reskin): compact card centered
       on the content area that visually REPLACES the Deezer player card
       (App.vue hides <PlayerBar> while this is visible — "replace + resume
       chip" pattern). Non-blocking — no backdrop, no Escape, no dialog role.
       Close = the ✕ button, or a Deezer play (see the watcher below). No text
       in the surface: the iframe already carries title, artist and brand. -->
  <div v-if="bar.track" class="bp-card" role="region" aria-label="Extrait Beatport">
    <div class="bpc-row">
      <button v-if="player.track" class="bpc-resume" type="button" @click="resumeDeezer">
        <span class="bpc-eq" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
        <span class="bpc-t">
          Reprendre la preview Deezer
          <em v-if="player.track.title">· {{ player.track.title }}</em>
        </span>
      </button>
      <span class="bpc-sp"></span>
      <RouterLink
        class="bpc-ghost bpc-link"
        :to="`/catalog/${bar.track.id}`"
        aria-label="Ouvrir la fiche du son"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M7 17 17 7M9 7h8v8" />
        </svg>
      </RouterLink>
      <button
        class="bpc-ghost bpc-close"
        type="button"
        aria-label="Fermer l'extrait Beatport"
        @click="bar.close()"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
        </svg>
      </button>
    </div>
    <!-- Eager: the card is visible by construction, the lazy IO would only
         flash the placeholder. :key forces a clean iframe reload when
         open() swaps the track. hide-link: the "Voir sur Beatport" link is
         redundant here (the ↗ ghost opens the track page, which carries it).
         The iframe stays a black box — no autoplay, no audio bridge, ever. -->
    <BeatportEmbed
      :key="bar.track.beatport_id"
      :beatport-id="bar.track.beatport_id"
      eager
      hide-link
    />
  </div>
</template>

<script setup>
import { watch } from 'vue'
import BeatportEmbed from './BeatportEmbed.vue'
import { useBeatportBar } from '../stores/beatportBar.js'
import { useAudioPlayer } from '../stores/audioPlayer.js'

const bar = useBeatportBar()
const player = useAudioPlayer()

// Resume chip: close the card (PlayerBar re-renders, paused) then resume the
// SAME paused audio — toggle(), never play() which would reload the preview.
function resumeDeezer() {
  bar.close()
  player.toggle()
}

// Inverse "never two audios" guard: open() already pauses Deezer; here a
// Deezer play/resume closes the card — unmounting the iframe is the ONLY way
// to cut its audio (the embed has no pause API).
watch(
  () => player.playing,
  (playing) => {
    if (playing) bar.close()
  },
)
</script>

<style scoped>
.bp-card {
  position: fixed;
  bottom: 18px;
  /* Centered on the content area: same --sidebar-w mechanic as PlayerBar
     (collapses 232 → 66 → 0 at the App.vue container paliers). The card hugs
     the embed; everything around it stays transparent and clickable. */
  left: var(--sidebar-w, 232px);
  right: 0;
  margin: 0 auto;
  width: min(608px, calc(100% - var(--sidebar-w, 232px) - 48px));
  /* Sandwich: page content < card < AddModal (200). PlayerBar (1000) is never
     visible at the same time (App.vue hides it), BottomNav (999) is cleared
     geometrically on mobile — the pilote's 50/70/70 scale is NOT the app's. */
  z-index: 150;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  padding: 0 4px 4px;
  display: flex;
  flex-direction: column;
  gap: 0;
  animation: bp-in 0.34s cubic-bezier(0.22, 0.61, 0.36, 1);
}
@keyframes bp-in {
  from {
    transform: translateY(calc(100% + 28px));
    opacity: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .bp-card {
    animation: bp-fade 0.2s ease;
  }
  @keyframes bp-fade {
    from {
      opacity: 0;
    }
  }
}

/* The embed's own rounding is for its standalone usage; inside the card the
   iframe stays un-clipped and square (pilote annotation). */
.bp-card :deep(.bp-frame) {
  border-radius: 0;
}

/* ── Top row (the only control row): chip · space · ↗ · ✕ ── */
.bpc-row {
  display: flex;
  align-items: center;
  gap: 0;
  min-height: 20px;
  /* the ghost rounds bleed 2px past the 4px card padding so they sit flush
     with the iframe edge (pilote) */
  margin: 0 -2px;
}
.bpc-sp {
  flex: 1;
}

.bpc-ghost {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--ink-3);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex: none;
  text-decoration: none;
}
.bpc-ghost:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.bpc-ghost svg {
  width: 11px;
  height: 11px;
}

/* ── Resume-Deezer chip — only when a Deezer preview was loaded ── */
.bpc-resume {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 18px;
  padding: 0 8px 0 6px;
  border-radius: 999px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 11.5px var(--font-ui);
  cursor: pointer;
  max-width: 100%;
  min-width: 0;
}
.bpc-resume:hover {
  border-color: var(--ink-3);
  color: var(--ink);
}
.bpc-eq {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 12px;
  flex: none;
}
.bpc-eq i {
  width: 2px;
  border-radius: 2px;
  background: var(--ink-3);
}
.bpc-eq i:nth-child(1) {
  height: 5px;
}
.bpc-eq i:nth-child(2) {
  height: 11px;
}
.bpc-eq i:nth-child(3) {
  height: 7px;
}
.bpc-eq i:nth-child(4) {
  height: 9px;
}
.bpc-t {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bpc-t em {
  font-style: normal;
  color: var(--ink-3);
}

/* ── Mobile: full width (−8px), above the BottomNav (fixed → @media) ── */
@media (max-width: 640px) {
  .bp-card {
    left: 8px;
    right: 8px;
    width: auto;
    bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px) + 8px);
  }
  .bp-card :deep(.bp-embed) {
    max-width: none;
  }
  /* keep the chip on one line: drop the Deezer title */
  .bpc-t em {
    display: none;
  }
}
</style>
