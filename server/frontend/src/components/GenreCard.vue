<template>
  <div
    class="genre-card"
    :class="{ liked: opinion === 'liked', disliked: opinion === 'disliked', playing: isPlaying }"
    :data-fam="tone.pillar"
    role="link"
    tabindex="0"
    :aria-label="genre.name"
    :title="genre.name"
    @click="goToGenre"
    @keydown.enter="goToGenre"
  >
    <!-- Artwork zone: 2×2 mosaic — cover or pillar-tinted placeholder tile -->
    <div class="gc-art">
      <div v-for="(slot, i) in fourSlots" :key="i" class="gc-tile">
        <img v-if="slot" class="gc-cover" :src="slot" alt="" loading="lazy" @error="onCoverError" />
      </div>
      <div class="gc-scrim"></div>

      <!-- Top-left corner: intentionally empty (G2) -->

      <!-- Artist avatars (bottom-left) -->
      <div v-if="topArtists.length" class="gc-avatars">
        <span
          v-for="a in topArtists"
          :key="a.id"
          class="av"
          :class="{ init: !a.image || broken[a.id] }"
        >
          <img
            v-if="a.image && !broken[a.id]"
            :src="a.image"
            :alt="a.name"
            loading="lazy"
            @error="onAvatarError(a)"
          />
          <template v-else>{{ initialsOf(a.name) }}</template>
        </span>
        <span v-if="genre.artistCount > 3" class="more">+{{ fmtNum(genre.artistCount - 3) }}</span>
      </div>

      <!-- Avis (top-right): hover-reveal, active button pinned via :deep() (G8) -->
      <div class="gc-acts" @click.stop>
        <LikeDislike
          :model-value="opinion"
          @update:model-value="(v) => opinions.set('genre', genre.name, v)"
        />
      </div>

      <!-- Play (bottom-right): hover-reveal, accent + pause when playing (G9) -->
      <button
        class="gc-play"
        :class="{ 'gc-play--playing': isPlaying }"
        :aria-label="isPlaying ? 'Pause' : 'Lecture'"
        @click.stop="onPlay"
      >
        <span class="gc-play-disc">
          <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 5h4v14H6zm8 0h4v14h-4z" />
          </svg>
        </span>
      </button>
    </div>

    <!-- Body: 3 tiers — name / signature (pillar · BPM) / stats (G1) -->
    <div class="gc-body">
      <div class="gc-titlerow">
        <span class="gc-dot"></span>
        <span class="gc-title">{{ genre.name }}</span>
      </div>
      <div class="gc-sig">
        <span class="sig-pillar">{{ pillarLabel }}</span>
        <span class="sig-sep">·</span>
        <span class="sig-bpm">{{ bpmLabel }}</span>
      </div>
      <div class="gc-stats">
        <div class="gc-stat">
          <span class="k">Tracks</span>
          <span class="v">{{ fmtNum(genre.trackCount) }}</span>
        </div>
        <div class="gc-stat">
          <span class="k">Artistes</span>
          <span class="v">{{ fmtNum(genre.artistCount) }}</span>
        </div>
        <div class="gc-stat gc-stat--lib">
          <span class="k">En bib</span>
          <span v-if="genre.inLibCount > 0" class="v v-pos">
            <span class="libdot"></span>{{ fmtNum(genre.inLibCount) }}
          </span>
          <span v-else class="v-empty">&mdash;</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { fmtNum } from '../utils/format'
import { styleTone, PILLAR_LABELS } from '../composables/useStyleMap.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { useOpinionsStore } from '../stores/opinions.js'
import LikeDislike from './LikeDislike.vue'

const props = defineProps({
  genre: { type: Object, required: true },
})

const router = useRouter()
const player = useAudioPlayer()
const opinions = useOpinionsStore()

const isPlaying = computed(() => player.genrePlaying === props.genre.name)
const opinion = computed(() => opinions.get('genre', props.genre.name))

function goToGenre(e) {
  // Keyboard: only navigate when the card itself is focused — an Enter pressed on
  // an inner control (play/avis) bubbles up here, but its target is the control,
  // not the card, so the guard blocks the stray navigation (pattern: ArtistCard).
  if (e.type === 'keydown' && e.target !== e.currentTarget) return
  router.push(`/style/${encodeURIComponent(props.genre.name)}`)
}

function onPlay() {
  if (isPlaying.value) {
    player.close()
  } else {
    player.playRandom(props.genre.name)
  }
}

const tone = computed(() => styleTone({ pillar: props.genre.pillar, depth: props.genre.depth }))
const pillarLabel = computed(() => PILLAR_LABELS[tone.value.pillar] || PILLAR_LABELS.autres)

// Signature BPM: interval, single value when lo == hi, "–" when both absent.
const bpmLabel = computed(() => {
  const { bpmLo, bpmHi } = props.genre
  if (!bpmLo && !bpmHi) return '–'
  const lo = Math.round(bpmLo)
  const hi = Math.round(bpmHi)
  return lo === hi ? `${lo} BPM` : `${lo}–${hi} BPM`
})

// 4 slots: available covers, null = pillar-tinted placeholder (no repeating).
const fourSlots = computed(() => {
  const aw = props.genre.artworks || []
  return [aw[0] || null, aw[1] || null, aw[2] || null, aw[3] || null]
})

const topArtists = computed(() => (props.genre.artists || []).slice(0, 3))

// Per-artist broken-image flags → fall back to initials (G7).
const broken = reactive({})

function initialsOf(name) {
  const words = String(name || '')
    .trim()
    .split(/[\s\-_./]+/)
    .filter((w) => /[a-zA-Z0-9]/.test(w))
  if (!words.length) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

function onCoverError(e) {
  e.target.remove()
}

function onAvatarError(a) {
  broken[a.id] = true
}
</script>

<style scoped>
/* ── Pillar hue mapping ── */
.genre-card[data-fam='house'] {
  --th: var(--hue-house);
}
.genre-card[data-fam='techno'] {
  --th: var(--hue-techno);
}
.genre-card[data-fam='trance'] {
  --th: var(--hue-trance);
}
.genre-card[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.genre-card[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.genre-card[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.genre-card[data-fam='autres'] {
  --th: 0;
  --ct-c: 0;
  --fb-c1: 0;
  --fb-c2: 0;
}
.genre-card[data-fam='autres'] .gc-dot {
  background: var(--ink-3);
  box-shadow: none;
}
.genre-card[data-fam='autres'] .sig-pillar {
  color: var(--ink-3);
}
.genre-card[data-fam='autres'] .av {
  background-color: var(--surface-3);
}
.genre-card[data-fam='autres'] .av.init {
  color: var(--ink-2);
}

.genre-card {
  container-type: inline-size;
  background: var(--surface);
  border: 1px solid var(--ct-line);
  border-radius: var(--r-md);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  color: inherit;
  transition:
    box-shadow 0.12s ease,
    border-color 0.12s ease;
}
/* Hover = shadow only, NO transform (DA rule) */
.genre-card:hover {
  box-shadow: var(--shadow-md);
}
.genre-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* ── Artwork zone — 2×2 mosaic, hue from [data-fam] via --th ── */
.gc-art {
  position: relative;
  aspect-ratio: 5 / 2;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  overflow: hidden;
}

/* Placeholder tile: pillar-tinted fallback gradient + inset hairline */
.gc-tile {
  position: relative;
  overflow: hidden;
  min-height: 0;
  background: linear-gradient(
    155deg,
    oklch(var(--fb-l1) var(--fb-c1) var(--th)) 0%,
    oklch(var(--fb-l2) var(--fb-c2) var(--th)) 100%
  );
  box-shadow: inset 0 0 0 1px var(--ct-line);
}
/* Subtle per-tile lightness so a cover-less genre isn't 4 identical squares */
.gc-tile:nth-child(2) {
  filter: brightness(0.94);
}
.gc-tile:nth-child(3) {
  filter: brightness(1.05);
}
.gc-tile:nth-child(4) {
  filter: brightness(0.97);
}

/* Cover image fills its tile cell — crop, never stretch */
.gc-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
  background: var(--surface-2);
}

/* Vertical scrim: light on top (covers stay readable), heavy at the bottom
   (carries the avatars). Warm near-black, theme-independent (G6). */
.gc-scrim {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background: linear-gradient(
    to bottom,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.06) 0%,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.34) 54%,
    oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.76) 100%
  );
}

/* ── Avatars (bottom-left) ── */
.gc-avatars {
  position: absolute;
  z-index: 3;
  left: 12px;
  bottom: 11px;
  display: flex;
  align-items: center;
}
.av {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  flex: none;
  margin-left: -8px;
  border: 2px solid var(--genre-tile-ink);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  display: grid;
  place-items: center;
  background-color: oklch(var(--tag-bg-l) calc(var(--tag-bg-c) * 0.9) var(--th));
}
.av:first-child {
  margin-left: 0;
}
[data-theme='dark'] .av {
  border-color: var(--genre-tile-border-dark);
}
.av img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.av.init {
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th));
  font: 700 var(--fs-nano)/1 var(--font-ui);
}
.more {
  margin-left: var(--space-15);
  height: 20px;
  display: inline-flex;
  align-items: center;
  padding: 0 var(--space-2);
  border-radius: var(--r-pill);
  background: var(--overlay-soft);
  color: var(--overlay-text);
  font: 600 var(--fs-xs)/1 var(--font-mono);
}

/* ── Play button (bottom-right) — 44px target / 30px disc ── */
.gc-play {
  position: absolute;
  z-index: 4;
  right: 1px;
  bottom: 1px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 0;
  background: transparent;
  padding: 0;
  display: grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.gc-play-disc {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  transition:
    background 0.12s ease,
    color 0.12s ease;
}
.gc-play svg {
  width: 16px;
  height: 16px;
  display: block;
  margin-left: var(--space-05);
}
.genre-card:hover .gc-play,
.gc-play:focus-visible {
  opacity: 1;
}
.gc-play--playing {
  opacity: 1;
}
.gc-play--playing .gc-play-disc {
  background: var(--accent);
  color: var(--on-accent);
}
.gc-play--playing svg {
  margin-left: 0;
}
.gc-play:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -6px;
}

/* ── Avis (top-right) — LikeDislike restyled as overlay discs via :deep() ──
   Hover-reveal by default; the active button stays pinned when an opinion is
   set (G8). LikeDislike itself is NOT modified — it exposes data-state on .ld
   plus .like / .dislike classes, which we target from this scope. */
.gc-acts {
  position: absolute;
  z-index: 4;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
}
.gc-acts :deep(.ld) {
  gap: var(--space-15);
}
.gc-acts :deep(.ld-btn) {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 50%;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  box-shadow: var(--shadow-sm);
  opacity: 0;
  transition:
    opacity 0.12s ease,
    background 0.12s ease,
    color 0.12s ease;
}
/* Reveal on card hover / keyboard focus */
.genre-card:hover .gc-acts :deep(.ld-btn),
.gc-acts:focus-within :deep(.ld-btn) {
  opacity: 1;
}
/* Pin the active button visible even at rest (the card already carries the
   halo/estompe state; only the concerned button needs to stay shown) */
.gc-acts :deep(.ld[data-state='liked'] .ld-btn.like),
.gc-acts :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  opacity: 1;
}

/* ── Card liked / disliked / playing states (G10) ── */
.genre-card.liked {
  border-color: var(--pos);
  box-shadow:
    0 0 0 1px var(--pos-soft),
    var(--shadow-sm);
}
.genre-card.liked:hover {
  box-shadow:
    0 0 0 1px var(--pos-soft),
    var(--shadow-md);
}
.genre-card.disliked {
  opacity: 0.45;
}
.genre-card.disliked:hover {
  opacity: 0.8;
}
/* Playing border wins over liked */
.genre-card.playing {
  border-color: var(--accent);
}

/* ── Body (tinted) ── */
.gc-body {
  padding: var(--pad);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex: 1;
  background: oklch(var(--ct-l) var(--ct-c) var(--th));
}
.gc-titlerow {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.gc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th));
  box-shadow: 0 0 0 1px oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th) / 0.28);
}
.gc-title {
  font: 600 var(--fs-title)/1.15 var(--font-ui);
  letter-spacing: -0.2px;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Signature: pillar label · BPM range, indented under the name */
.gc-sig {
  display: flex;
  align-items: baseline;
  gap: var(--space-15);
  padding-left: var(--space-4);
  min-width: 0;
}
.sig-pillar {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th));
  white-space: nowrap;
  flex: none;
}
.sig-sep {
  color: var(--ink-3);
  opacity: 0.5;
}
.sig-bpm {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Stats: Tracks · Artistes · En bib (fer à droite) ── */
.gc-stats {
  display: flex;
  align-items: stretch;
  margin-top: auto;
  border-top: 1px solid var(--ct-line);
  padding-top: var(--space-25);
  gap: var(--space-4);
}
.gc-stat {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}
.gc-stat--lib {
  margin-left: auto;
  align-items: flex-end;
  text-align: right;
}
.gc-stat .k {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
}
.gc-stat .v {
  font: 500 var(--fs-title)/1 var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
}
.gc-stat .v-pos {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  color: var(--pos-ink);
}
.libdot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--pos);
  flex: none;
}
.v-empty {
  font: 500 var(--fs-title)/1 var(--font-mono);
  color: var(--ink-3);
}

/* ── Narrow card (G14) — container queries on the card itself ── */
@container (max-width: 243px) {
  .gc-art {
    aspect-ratio: 3 / 2;
  }
  .gc-play {
    width: 38px;
    height: 38px;
  }
  .gc-play-disc {
    width: 27px;
    height: 27px;
  }
  .gc-acts :deep(.ld-btn) {
    width: 27px;
    height: 27px;
  }
  .av {
    width: 22px;
    height: 22px;
  }
}
@container (max-width: 219px) {
  .gc-stat .v,
  .gc-stat .v-pos,
  .v-empty {
    font-size: var(--fs-sm);
  }
  .gc-avatars .av:nth-child(3) {
    display: none;
  }
  /* Stats on two lines: Tracks + Artistes, then « En bib » alone, fer à droite */
  .gc-stats {
    flex-wrap: wrap;
    row-gap: var(--space-2);
  }
  .gc-stat--lib {
    flex-basis: 100%;
    margin-left: 0;
    margin-top: var(--space-1);
    padding-top: var(--space-2);
    border-top: 1px solid var(--ct-line);
    flex-direction: row;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-2);
  }
}
</style>
