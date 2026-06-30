<template>
  <RouterLink :to="`/artist/${artist.id}`" class="artist-card" :class="{ liked: opinion === 'liked', disliked: opinion === 'disliked' }" :data-fam="tone.pillar">
    <div class="ac-art" :class="{ fallback: !hasMosaic }">
      <!-- Mosaic covers (like GenreCard) -->
      <template v-if="hasMosaic">
        <div class="ac-mosaic">
          <div v-for="(slot, i) in fourSlots" :key="i" class="ac-tile">
            <img
              v-if="slot"
              class="ac-cover"
              :src="slot"
              alt=""
              loading="lazy"
              @error="onCoverError"
            />
          </div>
        </div>
        <div class="ac-scrim"></div>
      </template>

      <!-- Avatar (always visible, centered) -->
      <div class="ac-avatar" :class="{ init: !artist.has_artwork || imgBroken }">
        <img
          v-if="artist.has_artwork && !imgBroken"
          :src="`/storage/artist-artworks/${artist.id}.jpg`"
          :alt="artist.name"
          loading="lazy"
          @error="imgBroken = true"
        />
        <template v-else>{{ initials }}</template>
      </div>

      <!-- Rating badge -->
      <span v-if="artist.avg_rating != null" class="ac-rating">
        <svg viewBox="0 0 24 24"><path d="M12 2.5l2.9 6.2 6.6.7-4.9 4.5 1.4 6.6L12 18.6 6 21l1.4-6.6L2.5 9.4l6.6-.7z"/></svg>
        {{ artist.avg_rating.toFixed(1) }}
      </span>

      <!-- In-lib badge -->
      <span v-if="artist.nb_lib > 0" class="ac-lib">
        <span class="libdot"></span>{{ artist.nb_lib }} en bib
      </span>

      <!-- Play button (hover reveal) -->
      <button class="ac-play" :class="{ 'ac-play--playing': isPlaying }" aria-label="Lecture" @click.prevent.stop="onPlay">
        <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>
      </button>
    </div>

    <div class="ac-body">
      <div class="ac-name">{{ artist.name }}</div>
      <div v-if="displayGenres.length" class="ac-genres">
        <StyleTag v-for="g in displayGenres" :key="g.name" :name="g.name" :family="g.pillar" :depth="g.depth" />
      </div>
      <div class="ac-stats">
        <div class="ac-stat">
          <span class="k">Catalog</span>
          <span class="v">{{ artist.nb_catalog }}</span>
        </div>
        <div class="ac-stat">
          <span class="k">In Lib</span>
          <span v-if="artist.nb_lib" class="v">{{ artist.nb_lib }}</span>
          <span v-else class="v-empty">&mdash;</span>
        </div>
        <div class="ac-avis">
          <LikeDislike
            :model-value="opinions.get('artist', artist.id)"
            @update:model-value="v => opinions.set('artist', artist.id, v)"
          />
        </div>
      </div>
    </div>
  </RouterLink>
</template>

<script setup>
import { computed, ref } from 'vue'
import { styleTone } from '../composables/useStyleMap.js'

import { useAudioPlayer } from '../stores/audioPlayer'
import { useOpinionsStore } from '../stores/opinions.js'
import StyleTag from './StyleTag.vue'
import LikeDislike from './LikeDislike.vue'

const props = defineProps({
  artist: { type: Object, required: true },
})

const player = useAudioPlayer()
const opinions = useOpinionsStore()
const isPlaying = computed(() => player.artistPlaying === props.artist.id)
const opinion = computed(() => opinions.get('artist', props.artist.id))

function onPlay() {
  if (isPlaying.value) {
    player.close()
  } else {
    player.playRandomArtist(props.artist.id)
  }
}

const imgBroken = ref(false)

const tone = computed(() => {
  const g = props.artist.genres?.[0]
  if (!g) return styleTone({ pillar: 'autres' })
  return styleTone({ pillar: g.pillar, depth: g.depth })
})

const initials = computed(() => {
  const words = props.artist.name.trim().split(/[\s\-_./]+/).filter(w => /[a-zA-Z0-9]/.test(w))
  if (!words.length) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
})

const displayGenres = computed(() => {
  const genres = props.artist.genres || []
  return genres.slice(0, 2)
})

const hasMosaic = computed(() => (props.artist.tracks_with_artwork || 0) >= 1)

const fourSlots = computed(() => {
  const aw = props.artist.top_track_artworks || []
  return [aw[0] || null, aw[1] || null, aw[2] || null, aw[3] || null]
})

function onCoverError(e) {
  e.target.remove()
}
</script>

<style scoped>
/* ── Pillar hue mapping ── */
.artist-card[data-fam="house"]     { --th: var(--hue-house); }
.artist-card[data-fam="techno"]    { --th: var(--hue-techno); }
.artist-card[data-fam="trance"]    { --th: var(--hue-trance); }
.artist-card[data-fam="dnb"]       { --th: var(--hue-dnb); }
.artist-card[data-fam="hardcore"]  { --th: var(--hue-hardcore); }
.artist-card[data-fam="harddance"] { --th: var(--hue-harddance); }
.artist-card[data-fam="autres"]    { --th: 0; --ct-c: 0; --fb-c1: 0; --fb-c2: 0; }

.artist-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  text-decoration: none;
  color: inherit;
  transition: box-shadow .18s ease, transform .18s ease, border-color .18s ease;
}
.artist-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: var(--line-2);
}

/* ---- art zone ---- */
.ac-art {
  position: relative;
  height: 186px;
  overflow: hidden;
}

/* Mosaic (4 covers grid, like GenreCard) */
.ac-mosaic {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 2px;
}
.ac-tile {
  position: relative;
  overflow: hidden;
  min-height: 0;
  background: var(--surface-2);
}
.ac-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
}

/* Scrim: radial dark top + linear gradient towards family hue at bottom */
.ac-scrim {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background:
    radial-gradient(120% 92% at 50% 22%, transparent 0%, oklch(0.12 0.02 262 / .34) 100%),
    linear-gradient(to bottom, transparent 30%, oklch(var(--ct-l) calc(var(--ct-c) * 4.2) var(--th) / .96) 100%);
}
.artist-card[data-fam="autres"] .ac-scrim {
  background:
    radial-gradient(120% 92% at 50% 22%, transparent 0%, oklch(0.12 0.02 262 / .34) 100%),
    linear-gradient(to bottom, transparent 30%, oklch(var(--ct-l) 0 70 / .96) 100%);
}

/* Fallback: solid family gradient (no covers) */
.ac-art.fallback {
  background: linear-gradient(155deg,
    oklch(var(--fb-l1) var(--fb-c1) var(--th)) 0%,
    oklch(var(--fb-l2) var(--fb-c2) var(--th)) 100%);
}
.ac-art.fallback::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    135deg,
    transparent 0 9px,
    oklch(0 0 0 / .038) 9px 10px
  );
  pointer-events: none;
}

/* ---- avatar (centered in art zone) ---- */
.ac-avatar {
  position: absolute;
  z-index: 3;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -56%);
  width: 92px;
  height: 92px;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  box-shadow: 0 0 0 4px var(--surface), var(--shadow-md);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform .18s ease;
}
.ac-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.ac-avatar.init {
  background: oklch(var(--tag-bg-l) calc(var(--tag-bg-c) * .9) var(--th));
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th));
  font: 600 30px/1 var(--font-ui);
}
.artist-card[data-fam="autres"] .ac-avatar.init {
  background: var(--surface-3);
  color: var(--ink-2);
}
.artist-card:hover .ac-avatar {
  transform: translate(-50%, -56%) scale(1.07);
}

/* ---- rating badge ---- */
.ac-rating {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 4;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 23px;
  padding: 0 9px;
  border-radius: 999px;
  background: oklch(0.20 0.02 262 / .72);
  backdrop-filter: blur(6px);
  color: oklch(0.96 0.01 92);
  font: 600 11px/1 var(--font-mono);
  pointer-events: none;
}
.ac-rating svg {
  width: 12px;
  height: 12px;
  fill: var(--accent);
  flex: none;
}

/* ---- in-lib badge ---- */
.ac-lib {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  background: oklch(0.20 0.02 262 / .72);
  backdrop-filter: blur(6px);
  color: oklch(0.96 0.01 92);
  font: 600 10px/1 var(--font-mono);
  pointer-events: none;
}
.libdot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--pos);
  flex: none;
}

/* ---- play button ---- */
.ac-play {
  position: absolute;
  right: 10px;
  bottom: 10px;
  z-index: 4;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  cursor: pointer;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity .18s ease, transform .18s ease, background .14s;
  box-shadow: var(--shadow-md);
}
.ac-play svg { width: 14px; height: 14px; margin-left: 2px; }
.artist-card:hover .ac-play { opacity: 1; transform: none; }
.ac-play--playing { opacity: 1; transform: none; }
.ac-play:hover { background: var(--accent-hover); }

/* ---- body (tinted) ---- */
.ac-body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  flex: 1;
  background: oklch(var(--ct-l) var(--ct-c) var(--th));
}
.ac-name {
  font: 600 16px/1.15 var(--font-ui);
  letter-spacing: -.2px;
  color: var(--ink);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ac-genres {
  display: flex;
  flex-wrap: nowrap;
  gap: 5px;
  justify-content: center;
  min-height: 22px;
  overflow: hidden;
}
.ac-genres :deep(.style-tag) {
  min-width: 0;
  max-width: 50%;
  flex: 0 1 auto;
}

/* ---- stats ---- */
.ac-stats {
  display: flex;
  margin-top: auto;
  border-top: 1px solid var(--ct-line);
  padding-top: 10px;
}
.ac-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  align-items: center;
}
.ac-stat + .ac-stat { border-left: 1px solid var(--ct-line); }
.ac-stat .k {
  font: 600 8.5px/1 var(--font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.ac-stat .v {
  font: 600 14px/1 var(--font-mono);
  color: var(--ink);
}
.v-empty {
  font: 500 13px/1 var(--font-mono);
  color: var(--ink-3);
}

/* ---- avis separator + buttons ---- */
.ac-avis {
  border-left: 1px solid var(--ct-line);
  display: flex;
  align-items: center;
  padding-left: 12px;
  margin-left: auto;
}

/* ---- card liked / disliked states ---- */
.artist-card.liked {
  border-color: var(--pos);
  box-shadow: 0 0 0 2px var(--pos-soft);
}
.artist-card.disliked {
  opacity: 0.55;
}
.artist-card.disliked:hover {
  opacity: 0.8;
}
</style>
