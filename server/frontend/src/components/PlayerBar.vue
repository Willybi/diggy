<template>
  <div class="player">
    <div class="pl-shell">
      <!-- Play / Pause -->
      <button class="pl-play" :aria-label="player.playing ? 'Pause' : 'Play'" @click="player.toggle()">
        <svg v-if="!player.playing" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
      </button>

      <!-- Equalizer -->
      <div class="pl-eq" :class="{ active: player.playing }">
        <span class="eq-bar" v-for="i in 5" :key="i" />
      </div>

      <!-- Identity -->
      <div class="pl-id">
        <span class="pl-title">{{ player.track?.title }}</span>
        <span class="pl-artist">{{ player.track?.artist }}</span>
      </div>

      <!-- BPM · Key -->
      <div class="pl-stats">
        <div class="pl-stat">
          <span class="pl-stat-val">{{ player.track?.bpm ? Math.round(player.track.bpm) : '—' }}</span>
          <span class="pl-stat-lbl">BPM</span>
        </div>
        <div class="pl-stat pl-stat--key">
          <span class="pl-stat-val">{{ player.track?.key || '—' }}</span>
          <span class="pl-stat-lbl">KEY</span>
        </div>
      </div>

      <!-- Timeline -->
      <span class="pl-elapsed mono">{{ fmtSec(player.currentTime) }}</span>
      <div
        class="pl-rail"
        role="slider"
        aria-label="Seek"
        :aria-valuenow="Math.round(player.currentTime)"
        :aria-valuemax="Math.round(player.duration)"
        aria-valuemin="0"
        @pointerdown="onScrubStart"
      >
        <div class="pl-fill" :style="{ width: (player.progress * 100) + '%' }">
          <div class="pl-thumb" />
        </div>
      </div>
      <span class="pl-remain mono">{{ fmtSec(player.currentTime - player.duration) }}</span>

      <!-- Volume -->
      <div class="pl-vol">
        <button class="pl-vol-icon" aria-label="Mute" @click="player.toggleMute()">
          <!-- muted -->
          <svg v-if="player.muted || player.volume === 0" viewBox="0 0 24 24" fill="currentColor">
            <path d="M3.63 3.63a.996.996 0 000 1.41L7.29 8.7 7 9H4c-.55 0-1 .45-1 1v4c0 .55.45 1 1 1h3l3.29 3.29c.63.63 1.71.18 1.71-.71v-4.17l4.18 4.18c-.49.37-1.02.68-1.6.91-.36.15-.58.53-.58.92 0 .72.73 1.18 1.39.91.8-.33 1.55-.77 2.22-1.31l1.34 1.34a.996.996 0 101.41-1.41L5.05 3.63c-.39-.39-1.02-.39-1.42 0zM19 12c0 .82-.15 1.61-.41 2.34l1.53 1.53c.56-1.17.88-2.48.88-3.87 0-3.83-2.4-7.11-5.78-8.4-.59-.23-1.22.23-1.22.86v.19c0 .38.25.71.61.85C17.18 6.54 19 9.06 19 12zm-8.71-6.29l-.17.17L12 7.76V6.41c0-.89-1.08-1.33-1.71-.7zM16.5 12A4.5 4.5 0 0014 7.97v1.79l2.48 2.48c.01-.08.02-.16.02-.24z"/>
          </svg>
          <!-- low volume -->
          <svg v-else-if="player.volume < 0.5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M18.5 12A4.5 4.5 0 0016 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z"/>
          </svg>
          <!-- high volume -->
          <svg v-else viewBox="0 0 24 24" fill="currentColor">
            <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0014 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
          </svg>
        </button>
        <input
          type="range"
          class="pl-vol-slider"
          min="0" max="1" step="0.01"
          :value="player.volume"
          aria-label="Volume"
          @input="e => player.setVolume(parseFloat(e.target.value))"
        />
      </div>

      <!-- Close -->
      <button class="pl-close" aria-label="Fermer le lecteur" @click="player.close()">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtSec } from '../utils/format'

const player = useAudioPlayer()

function onScrubStart(e) {
  const rail = e.currentTarget
  rail.setPointerCapture(e.pointerId)

  const seek = (ev) => {
    const rect = rail.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
    player.seek(ratio * player.duration)
  }

  seek(e)
  const onMove = (ev) => seek(ev)
  const onUp = () => {
    rail.removeEventListener('pointermove', onMove)
    rail.removeEventListener('pointerup', onUp)
  }
  rail.addEventListener('pointermove', onMove)
  rail.addEventListener('pointerup', onUp)
}
</script>

<style scoped>
.player {
  position: fixed;
  bottom: 18px;
  left: calc(232px + 24px);
  right: 24px;
  max-width: 1200px;
  margin: 0 auto;
  z-index: 1000;
}

.pl-shell {
  container-type: inline-size;
  container-name: player;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
}

/* ── Play/Pause ── */
.pl-play {
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: background 0.12s;
}
.pl-play:hover { background: var(--accent-hover); }
.pl-play svg { width: 18px; height: 18px; }

/* ── Equalizer ── */
.pl-eq {
  flex: none;
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 20px;
}
.eq-bar {
  width: 3px;
  background: var(--accent);
  border-radius: 1px;
  transform-origin: bottom;
  animation: eq-dance 1s ease-in-out infinite alternate;
  animation-play-state: paused;
}
.pl-eq.active .eq-bar { animation-play-state: running; }
.eq-bar:nth-child(1) { height: 14px; animation-duration: 0.85s; }
.eq-bar:nth-child(2) { height: 10px; animation-duration: 1.0s; animation-delay: -0.3s; }
.eq-bar:nth-child(3) { height: 18px; animation-duration: 1.15s; animation-delay: -0.5s; }
.eq-bar:nth-child(4) { height: 8px;  animation-duration: 1.35s; animation-delay: -0.1s; }
.eq-bar:nth-child(5) { height: 12px; animation-duration: 1.55s; animation-delay: -0.7s; }

@keyframes eq-dance {
  0%   { transform: scaleY(0.3); }
  100% { transform: scaleY(1); }
}

/* ── Identity ── */
.pl-id {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pl-title {
  font: 600 13px/1.2 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pl-artist {
  font: 400 11.5px/1.2 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── BPM / Key ── */
.pl-stats {
  flex: none;
  display: flex;
  gap: 12px;
}
.pl-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}
.pl-stat + .pl-stat {
  padding-left: 12px;
  border-left: 1px solid var(--line);
}
.pl-stat-val {
  font: 500 13px/1 var(--font-mono);
  color: var(--ink-2);
}
.pl-stat--key .pl-stat-val {
  color: var(--accent-ink);
}
.pl-stat-lbl {
  font: 400 9px/1 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
}

/* ── Timeline ── */
.mono {
  font-family: var(--font-mono);
  font-size: 11px;
  flex: none;
  min-width: 32px;
  text-align: center;
}
.pl-elapsed { color: var(--ink-2); }
.pl-remain  { color: var(--ink-3); }

.pl-rail {
  flex: 1;
  min-width: 60px;
  height: 4px;
  background: var(--line-2);
  border-radius: 2px;
  cursor: pointer;
  position: relative;
  touch-action: none;
}
.pl-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  position: relative;
}
.pl-thumb {
  position: absolute;
  right: -5px;
  top: 50%;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  transform: translateY(-50%) scale(0);
  transition: transform 0.12s;
}
.pl-rail:hover .pl-thumb,
.pl-rail:active .pl-thumb {
  transform: translateY(-50%) scale(1);
}

/* ── Volume ── */
.pl-vol {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.pl-vol-icon {
  background: none;
  border: none;
  color: var(--ink-2);
  cursor: pointer;
  padding: 2px;
  display: grid;
  place-items: center;
  transition: color 0.12s;
}
.pl-vol-icon:hover { color: var(--ink); }
.pl-vol-icon svg { width: 18px; height: 18px; }

.pl-vol-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 84px;
  height: 4px;
  background: var(--line-2);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.pl-vol-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ink-2);
  cursor: pointer;
}
.pl-vol-slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ink-2);
  border: none;
  cursor: pointer;
}

/* ── Close ── */
.pl-close {
  flex: none;
  background: none;
  border: none;
  color: var(--ink-3);
  cursor: pointer;
  padding: 4px;
  display: grid;
  place-items: center;
  border-radius: var(--r-xs);
  transition: color 0.12s;
}
.pl-close:hover { color: var(--ink); }
.pl-close svg { width: 18px; height: 18px; }

/* ── Container queries ── */
@container player (max-width: 720px) {
  .pl-stats { display: none; }
}
@container player (max-width: 560px) {
  .pl-elapsed, .pl-remain { display: none; }
}
@container player (max-width: 440px) {
  .pl-shell { gap: 8px; padding: 8px 12px; }
  .pl-vol { display: none; }
}

/* ── Sidebar responsive ── */
@media (max-width: 900px) {
  .player { left: calc(66px + 24px); }
}

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  .eq-bar { animation-play-state: paused !important; }
}
</style>
