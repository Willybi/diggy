<template>
  <!-- Docked full-width Beatport preview bar (D12 v2): non-blocking — the
       site stays usable while the embed shows, so NO modal chrome (no
       backdrop, no Escape, no dialog role). Close = the ✕ button, or a
       Deezer play (see the watcher below). -->
  <div
    v-if="bar.track"
    class="bp-bar"
    :class="{ 'has-player': player.visible }"
    role="region"
    aria-label="Extrait Beatport"
  >
    <div class="bpb-shell">
      <div class="bpb-head">
        <span class="bpb-label">Extrait Beatport</span>
        <div class="bpb-track">
          <span class="bpb-title">{{ bar.track.title }}</span>
          <span v-if="bar.track.artist" class="bpb-sep" aria-hidden="true">·</span>
          <span v-if="bar.track.artist" class="bpb-artist">{{ bar.track.artist }}</span>
        </div>
        <button
          class="bpb-close"
          type="button"
          aria-label="Fermer l'extrait Beatport"
          @click="bar.close()"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path
              d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"
            />
          </svg>
        </button>
      </div>
      <!-- Eager: the bar is visible by construction, the lazy IO would only
           flash the placeholder. :key forces a clean iframe reload when
           open() swaps the track. The iframe stays a black box — no
           autoplay, no audio bridge, ever. -->
      <BeatportEmbed :key="bar.track.beatport_id" :beatport-id="bar.track.beatport_id" eager />
    </div>
  </div>
</template>

<script setup>
import { watch } from 'vue'
import BeatportEmbed from './BeatportEmbed.vue'
import { useBeatportBar } from '../stores/beatportBar.js'
import { useAudioPlayer } from '../stores/audioPlayer.js'

const bar = useBeatportBar()
const player = useAudioPlayer()

// Inverse "never two audios" guard: open() already pauses Deezer; here a
// Deezer play/resume closes the bar — unmounting the iframe is the ONLY way
// to cut its audio (the embed has no pause API).
watch(
  () => player.playing,
  (playing) => {
    if (playing) bar.close()
  },
)
</script>

<style scoped>
.bp-bar {
  position: fixed;
  bottom: 0;
  /* Content-area width: same --sidebar-w mechanic as PlayerBar (the variable
     collapses to 66px then 0px at the App.vue container paliers). */
  left: var(--sidebar-w, 232px);
  right: 0;
  /* Sandwich: page content < bar < AddModal (200) — the bar is furniture,
     real modals must cover it. No overlap with BottomNav (999) or PlayerBar
     (1000): both are cleared geometrically below. */
  z-index: 150;
  background: var(--surface);
  border-top: 1px solid var(--line);
  box-shadow: var(--shadow-lg);
}
/* PlayerBar visible: clear its floating card (bottom 18px + ~68px of bar);
   100px = the reservation App.vue already uses for .app-main.has-player. */
.bp-bar.has-player {
  bottom: 100px;
}

.bpb-shell {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--space-3) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* ── Header line ── */
.bpb-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}
.bpb-label {
  flex: none;
  font: 500 var(--fs-nano) / 1 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--chart-beatport);
}
.bpb-track {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: var(--space-1);
  overflow: hidden;
}
.bpb-title {
  font: 600 var(--fs-sm) / 1.2 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bpb-sep {
  flex: none;
  color: var(--ink-3);
}
.bpb-artist {
  font: 400 var(--fs-xs) / 1.2 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bpb-close {
  flex: none;
  background: none;
  border: none;
  color: var(--ink-3);
  cursor: pointer;
  padding: var(--space-1);
  display: grid;
  place-items: center;
  border-radius: var(--r-xs);
  transition: color 0.12s;
}
.bpb-close:hover {
  color: var(--ink);
}
.bpb-close svg {
  width: 18px;
  height: 18px;
}

/* ── Mobile: dock above BottomNav (same mechanic as PlayerBar) ── */
@media (max-width: 640px) {
  .bp-bar {
    left: 0;
    bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px));
  }
  /* Above BottomNav AND the PlayerBar card (nav + 8px gap + ~68px bar ≈ the
     90px reservation App.vue uses for mobile .has-player). */
  .bp-bar.has-player {
    bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px) + 90px);
  }
}
</style>
