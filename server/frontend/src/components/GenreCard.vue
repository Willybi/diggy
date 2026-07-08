<template>
  <RouterLink
    :to="`/style/${encodeURIComponent(genre.name)}`"
    class="genre-card"
    :class="{ liked: opinion === 'liked', disliked: opinion === 'disliked' }"
    :data-fam="tone.pillar"
  >
    <!-- Artwork zone: always 4 slots — image or tinted placeholder -->
    <div class="gc-art">
      <div v-for="(slot, i) in fourSlots" :key="i" class="gc-tile">
        <img v-if="slot" class="gc-cover" :src="slot" alt="" loading="lazy" @error="onCoverError" />
      </div>
      <div class="gc-scrim"></div>

      <!-- Badge in-lib -->
      <span v-if="genre.inLibCount > 0" class="gc-lib">
        <span class="libdot"></span>{{ fmtNum(genre.inLibCount) }} en bib
      </span>

      <!-- Avatars artistes -->
      <div v-if="genre.artists?.length" class="gc-avatars">
        <img
          v-for="a in genre.artists.slice(0, 3)"
          :key="a.id"
          class="av"
          :src="a.image"
          :alt="a.name"
          loading="lazy"
          @error="onAvatarError"
        />
        <span v-if="genre.artistCount > 3" class="more">+{{ fmtNum(genre.artistCount - 3) }}</span>
      </div>

      <!-- Like/Dislike overlay (top-right of art zone) -->
      <div class="gc-acts" @click.prevent.stop>
        <LikeDislike
          :model-value="opinion"
          @update:model-value="(v) => opinions.set('genre', genre.name, v)"
        />
      </div>

      <!-- Play button (hover reveal) -->
      <button
        class="gc-play"
        :class="{ 'gc-play--playing': isPlaying }"
        aria-label="Lecture"
        @click.prevent.stop="onPlay"
      >
        <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 5h4v14H6zm8 0h4v14h-4z" />
        </svg>
      </button>
    </div>

    <!-- Body -->
    <div class="gc-body">
      <div class="gc-titlerow">
        <span class="gc-dot"></span>
        <span class="gc-title">{{ genre.name }}</span>
        <span class="gc-fam">{{ pillarLabel }}</span>
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
        <div class="gc-stat bpm">
          <span class="k">BPM</span>
          <span v-if="!genre.bpmLo && !genre.bpmHi" class="v-empty">–</span>
          <span v-else-if="genre.bpmLo === genre.bpmHi" class="v">{{ genre.bpmLo }}</span>
          <span v-else class="v">{{ genre.bpmLo }}–{{ genre.bpmHi }}</span>
        </div>
      </div>
    </div>
  </RouterLink>
</template>

<script setup>
import { computed } from 'vue'
import { fmtNum } from '../utils/format'
import { styleTone, PILLAR_LABELS } from '../composables/useStyleMap.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { useOpinionsStore } from '../stores/opinions.js'
import LikeDislike from './LikeDislike.vue'

const props = defineProps({
  genre: { type: Object, required: true },
})

const player = useAudioPlayer()
const opinions = useOpinionsStore()
const isPlaying = computed(() => player.genrePlaying === props.genre.name)
const opinion = computed(() => opinions.get('genre', props.genre.name))

function onPlay() {
  if (isPlaying.value) {
    player.close()
  } else {
    player.playRandom(props.genre.name)
  }
}

const tone = computed(() => styleTone({ pillar: props.genre.pillar, depth: props.genre.depth }))
const pillarLabel = computed(() => PILLAR_LABELS[tone.value.pillar] || PILLAR_LABELS.autres)

// 4 slots: use available covers, null = tinted placeholder (no repeating)
const fourSlots = computed(() => {
  const aw = props.genre.artworks || []
  return [aw[0] || null, aw[1] || null, aw[2] || null, aw[3] || null]
})

function onCoverError(e) {
  e.target.remove()
}

function onAvatarError(e) {
  e.target.style.display = 'none'
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
}
.genre-card[data-fam='autres'] .gc-tile {
  --mc: 0;
}
.genre-card[data-fam='autres'] .gc-dot {
  background: var(--ink-3);
  box-shadow: none;
}
.genre-card[data-fam='autres'] .gc-title {
  color: var(--ink-2);
}

.genre-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition:
    box-shadow 0.18s ease,
    transform 0.18s ease,
    border-color 0.18s ease;
  text-decoration: none;
  color: inherit;
}
.genre-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: var(--line-2);
}

/* ── Artwork zone — 2×2 mosaic, hue from [data-fam] on parent ── */
.gc-art {
  position: relative;
  height: 130px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: var(--space-05);
}

.gc-tile {
  position: relative;
  overflow: hidden;
  min-height: 0;
  background: oklch(var(--ml) var(--mc, 0.15) var(--th));
}
.gc-tile:nth-child(1) {
  --ml: 0.66;
  --mc: 0.155;
}
.gc-tile:nth-child(2) {
  --ml: 0.75;
  --mc: 0.115;
}
.gc-tile:nth-child(3) {
  --ml: 0.56;
  --mc: 0.165;
}
.gc-tile:nth-child(4) {
  --ml: 0.7;
  --mc: 0.095;
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

.gc-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, var(--genre-tile-scrim) 0%, transparent 46%);
  pointer-events: none;
}

/* Badge in-lib */
.gc-lib {
  position: absolute;
  top: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font: 600 var(--fs-label)/1 var(--font-mono);
  color: var(--pos-ink);
  background: var(--surface);
  padding: var(--space-1) var(--space-2) var(--space-1) var(--space-15);
  border-radius: var(--r-pill);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--line);
}
.libdot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--pos);
  flex: none;
}

/* Avatars */
.gc-avatars {
  position: absolute;
  left: 12px;
  bottom: 11px;
  display: flex;
  align-items: center;
}
.av {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  flex: none;
  margin-left: -9px;
  border: 2px solid var(--genre-tile-ink);
  object-fit: cover;
  box-shadow: var(--shadow-sm);
  background-color: oklch(var(--art-l) calc(var(--art-c) + 0.02) var(--th));
}
.av:first-child {
  margin-left: 0;
}
[data-theme='dark'] .av {
  border-color: var(--genre-tile-border-dark);
}
.more {
  margin-left: var(--space-15);
  font: 600 var(--fs-xs)/1 var(--font-mono);
  color: var(--genre-tile-ink);
  text-shadow: 0 1px 3px var(--genre-tile-shadow);
}

/* Play button */
.gc-play {
  position: absolute;
  right: 11px;
  bottom: 11px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  transform: translateY(6px);
  transition:
    opacity 0.18s ease,
    transform 0.18s ease,
    background 0.15s;
  box-shadow: var(--shadow-md);
}
.gc-play svg {
  width: 17px;
  height: 17px;
  margin-left: var(--space-05);
}
.genre-card:hover .gc-play {
  opacity: 1;
  transform: none;
}
.gc-play--playing {
  opacity: 1;
  transform: none;
}
.gc-play:hover {
  background: var(--accent-hover);
}

/* Like/Dislike overlay in art zone — hover reveal */
.gc-acts {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 4;
  display: flex;
  align-items: center;
  opacity: 0;
  transition: opacity 0.18s ease;
}
.genre-card:hover .gc-acts {
  opacity: 1;
}
.gc-acts :deep(.ld-btn) {
  box-shadow: var(--shadow-sm);
}

/* Card liked / disliked states */
.genre-card.liked {
  border-color: var(--pos);
  box-shadow: 0 0 0 2px var(--pos-soft);
}
.genre-card.disliked {
  opacity: 0.55;
}
.genre-card.disliked:hover {
  opacity: 0.8;
}

/* ── Body ── */
.gc-body {
  padding: var(--pad);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  flex: 1;
  background: oklch(var(--ct-l) var(--ct-c) var(--th));
}
.gc-titlerow {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  min-width: 0;
}
.gc-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  align-self: center;
  background: oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th));
  box-shadow: 0 0 0 1px oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th) / 0.28);
}
.gc-title {
  font: 600 var(--fs-md) var(--font-ui);
  letter-spacing: -0.2px;
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gc-fam {
  font: 500 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  flex: none;
}

/* ── Stats ── */
.gc-stats {
  display: flex;
  margin-top: auto;
  border-top: 1px solid var(--ct-line);
  padding-top: var(--space-25);
}
.gc-stat {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding-right: var(--space-3);
}
.gc-stat + .gc-stat {
  padding-left: var(--space-3);
  border-left: 1px solid var(--ct-line);
}
.gc-stat .k {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
}
.gc-stat .v {
  font: 600 var(--fs-base)/1 var(--font-mono);
  color: var(--ink);
  white-space: nowrap;
}
.gc-stat.bpm .v {
  color: var(--ink-2);
  font-size: var(--fs-sm);
}
.gc-stat .v-empty {
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
}
</style>
