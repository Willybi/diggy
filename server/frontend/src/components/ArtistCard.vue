<template>
  <div
    class="artist-card"
    :class="{ liked: opinion === 'liked', disliked: opinion === 'disliked', playing: isPlaying }"
    :data-fam="tone.pillar"
    role="link"
    tabindex="0"
    :aria-label="artist.name"
    @click="goToArtist"
    @keydown.enter="goToArtist"
  >
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

      <!-- Follow toggle (top-left) -->
      <button
        class="ac-follow"
        :class="{ 'ac-follow--on': following }"
        :aria-pressed="following"
        :aria-label="following ? `Ne plus suivre ${artist.name}` : `Suivre ${artist.name}`"
        :title="following ? `Ne plus suivre ${artist.name}` : `Suivre ${artist.name}`"
        @click.stop.prevent="toggleFollow"
      >
        <span class="ac-follow-disc">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5S10.5 3.17 10.5 4v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"
            />
          </svg>
        </span>
      </button>

      <!-- Play button (hover reveal) -->
      <button
        class="ac-play"
        :class="{ 'ac-play--playing': isPlaying }"
        aria-label="Lecture"
        @click.stop="onPlay"
      >
        <span class="ac-play-disc">
          <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 5h4v14H6zm8 0h4v14h-4z" />
          </svg>
        </span>
      </button>
    </div>

    <div class="ac-body">
      <div class="ac-name">{{ artist.name }}</div>
      <div class="ac-genres">
        <RouterLink
          v-for="g in displayGenres"
          :key="g.name"
          class="ac-genre-link"
          :to="`/style/${encodeURIComponent(g.name)}`"
          @click.stop
        >
          <StyleTag :name="g.name" :family="g.pillar" :depth="g.depth" />
        </RouterLink>
      </div>
      <div class="ac-stats">
        <div class="ac-stat">
          <span class="k">Catalog</span>
          <span class="v">{{ artist.nb_catalog }}</span>
        </div>
        <div class="ac-stat">
          <span class="k">In Lib</span>
          <span v-if="artist.nb_lib" class="v v-pos">{{ artist.nb_lib }}</span>
          <span v-else class="v-empty">&mdash;</span>
        </div>
        <div class="ac-avis">
          <LikeDislike
            :model-value="opinions.get('artist', artist.id)"
            @update:model-value="(v) => opinions.set('artist', artist.id, v)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { styleTone } from '../composables/useStyleMap.js'

import api from '../utils/api.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { useOpinionsStore } from '../stores/opinions.js'
import StyleTag from './StyleTag.vue'
import LikeDislike from './LikeDislike.vue'

const props = defineProps({
  artist: { type: Object, required: true },
})

const router = useRouter()
const player = useAudioPlayer()
const opinions = useOpinionsStore()
const isPlaying = computed(() => player.artistPlaying === props.artist.id)
const opinion = computed(() => opinions.get('artist', props.artist.id))

function goToArtist(e) {
  // Keyboard: only navigate when the card itself is focused. Without this guard,
  // an Enter pressed on an inner control (follow/play/genre link) bubbles
  // its keydown up to the card and navigates on top of the control's own action
  // (the controls .stop their click, but not their keydown).
  if (e.type === 'keydown' && e.target !== e.currentTarget) return
  router.push(`/artist/${props.artist.id}`)
}

function onPlay() {
  if (isPlaying.value) {
    player.close()
  } else {
    player.playRandomArtist(props.artist.id)
  }
}

// -- Follow (optimistic, internal to the card) --
const following = ref(!!props.artist.following)
watch(
  () => props.artist.following,
  (v) => {
    following.value = !!v
  },
)

async function toggleFollow() {
  const prev = following.value
  following.value = !prev
  try {
    if (prev) {
      await api.delete(`/api/artists/${props.artist.id}/follow`)
    } else {
      await api.post(`/api/artists/${props.artist.id}/follow`)
    }
  } catch {
    following.value = prev
  }
}

const imgBroken = ref(false)

const tone = computed(() => {
  const g = props.artist.genres?.[0]
  if (!g) return styleTone({ pillar: 'autres' })
  return styleTone({ pillar: g.pillar, depth: g.depth })
})

const initials = computed(() => {
  const words = props.artist.name
    .trim()
    .split(/[\s\-_./]+/)
    .filter((w) => /[a-zA-Z0-9]/.test(w))
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
.artist-card[data-fam='house'] {
  --th: var(--hue-house);
}
.artist-card[data-fam='techno'] {
  --th: var(--hue-techno);
}
.artist-card[data-fam='trance'] {
  --th: var(--hue-trance);
}
.artist-card[data-fam='dnb'] {
  --th: var(--hue-dnb);
}
.artist-card[data-fam='hardcore'] {
  --th: var(--hue-hardcore);
}
.artist-card[data-fam='harddance'] {
  --th: var(--hue-harddance);
}
.artist-card[data-fam='autres'] {
  --th: 0;
  --ct-c: 0;
  --fb-c1: 0;
  --fb-c2: 0;
}

.artist-card {
  container-type: inline-size;
  background: var(--surface);
  border: 1px solid var(--ct-line);
  border-radius: var(--r-md);
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  color: inherit;
  box-shadow: var(--shadow-sm);
  transition:
    box-shadow 0.12s ease,
    border-color 0.12s ease;
}
.artist-card:hover {
  box-shadow: var(--shadow-md);
}
.artist-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* ---- art zone ---- */
.ac-art {
  position: relative;
  aspect-ratio: 1 / 1;
  overflow: hidden;
}

/* Mosaic (4 covers grid, like GenreCard) */
.ac-mosaic {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
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

/* Scrim: soft central radial (detaches the avatar) + lightened vertical
   gradient toward the family hue at the bottom. */
.ac-scrim {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background:
    radial-gradient(
      66% 58% at 50% 44%,
      oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.5) 0%,
      transparent 70%
    ),
    linear-gradient(
      to bottom,
      oklch(var(--ct-l) calc(var(--ct-c) * 4.2) var(--th) / 0.1) 0%,
      oklch(var(--ct-l) calc(var(--ct-c) * 4.2) var(--th) / 0.4) 52%,
      oklch(var(--ct-l) calc(var(--ct-c) * 4.2) var(--th) / 0.78) 100%
    );
}
.artist-card[data-fam='autres'] .ac-scrim {
  background:
    radial-gradient(
      66% 58% at 50% 44%,
      oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.5) 0%,
      transparent 70%
    ),
    linear-gradient(
      to bottom,
      oklch(var(--ct-l) 0 70 / 0.1) 0%,
      oklch(var(--ct-l) 0 70 / 0.4) 52%,
      oklch(var(--ct-l) 0 70 / 0.78) 100%
    );
}

/* Fallback: solid family gradient (no covers) */
.ac-art.fallback {
  background: linear-gradient(
    155deg,
    oklch(var(--fb-l1) var(--fb-c1) var(--th)) 0%,
    oklch(var(--fb-l2) var(--fb-c2) var(--th)) 100%
  );
}
.ac-art.fallback::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    135deg,
    transparent 0 9px,
    oklch(0 0 0 / 0.038) 9px 10px
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
  width: 44%;
  aspect-ratio: 1 / 1;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  box-shadow:
    0 0 0 3px var(--genre-tile-ink),
    var(--shadow-md);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
[data-theme='dark'] .ac-avatar {
  box-shadow:
    0 0 0 3px var(--genre-tile-border-dark),
    var(--shadow-md);
}
.ac-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.ac-avatar.init {
  background: oklch(var(--tag-bg-l) calc(var(--tag-bg-c) * 0.9) var(--th));
  color: oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th));
  font: 700 var(--fs-lg)/1 var(--font-ui);
}
.artist-card[data-fam='autres'] .ac-avatar.init {
  background: var(--surface-3);
  color: var(--ink-2);
}

/* ---- follow toggle (top-left) ---- */
.ac-follow {
  position: absolute;
  top: 2px;
  left: 2px;
  z-index: 4;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  display: grid;
  place-items: center;
  cursor: pointer;
}
.ac-follow-disc {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  opacity: 0.5;
  transition:
    opacity 0.12s ease,
    background 0.12s ease,
    color 0.12s ease;
}
.ac-follow svg {
  width: 16px;
  height: 16px;
  display: block;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.artist-card:hover .ac-follow-disc,
.ac-follow:hover .ac-follow-disc {
  opacity: 1;
}
.ac-follow--on .ac-follow-disc {
  background: var(--accent);
  color: var(--on-accent);
  box-shadow: var(--shadow-sm);
  opacity: 1;
}
.ac-follow--on:hover .ac-follow-disc {
  background: var(--accent-hover);
}
.ac-follow--on svg {
  fill: currentColor;
  stroke: none;
}
.ac-follow:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -6px;
}

/* ---- play button ---- */
.ac-play {
  position: absolute;
  right: 2px;
  bottom: 2px;
  z-index: 4;
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
.ac-play-disc {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--overlay-soft);
  color: var(--overlay-text);
  transition:
    background 0.12s ease,
    color 0.12s ease;
}
.ac-play svg {
  width: 15px;
  height: 15px;
  display: block;
  margin-left: var(--space-05);
}
.artist-card:hover .ac-play,
.ac-play:focus-visible {
  opacity: 1;
}
.ac-play--playing {
  opacity: 1;
}
.ac-play--playing .ac-play-disc {
  background: var(--accent);
  color: var(--on-accent);
}
.ac-play--playing svg {
  margin-left: 0;
}
.ac-play:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -6px;
}

/* ---- body (tinted) ---- */
.ac-body {
  padding: var(--pad);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex: 1;
  background: oklch(var(--ct-l) var(--ct-c) var(--th));
}
.ac-name {
  font: 600 var(--fs-title)/1.15 var(--font-ui);
  letter-spacing: -0.2px;
  color: var(--ink);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ac-genres {
  display: flex;
  flex-wrap: nowrap;
  gap: var(--space-1);
  justify-content: center;
  min-height: 22px;
  overflow: hidden;
}
.ac-genre-link {
  min-width: 0;
  max-width: 50%;
  flex: 0 1 auto;
  text-decoration: none;
  display: inline-flex;
}
.ac-genre-link :deep(.style-tag) {
  min-width: 0;
  max-width: 100%;
}

/* ---- stats ---- */
.ac-stats {
  display: flex;
  align-items: stretch;
  margin-top: auto;
  border-top: 1px solid var(--ct-line);
  padding-top: var(--space-25);
}
.ac-stat {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
  flex: 1;
  align-items: center;
}
.ac-stat + .ac-stat {
  border-left: 1px solid var(--ct-line);
}
.ac-stat .k {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.ac-stat .v {
  font: 500 var(--fs-title)/1 var(--font-mono);
  color: var(--ink-2);
}
.ac-stat .v-pos {
  color: var(--pos-ink);
}
.v-empty {
  font: 500 var(--fs-title)/1 var(--font-mono);
  color: var(--ink-3);
}

/* ---- avis separator + buttons ---- */
.ac-avis {
  border-left: 1px solid var(--ct-line);
  display: flex;
  align-items: center;
  padding-left: var(--space-3);
  margin-left: auto;
}

/* ---- card liked / disliked states ---- */
.artist-card.liked {
  border-color: var(--pos);
  box-shadow:
    0 0 0 1px var(--pos-soft),
    var(--shadow-sm);
}
.artist-card.liked:hover {
  box-shadow:
    0 0 0 1px var(--pos-soft),
    var(--shadow-md);
}
.artist-card.disliked {
  opacity: 0.45;
}
.artist-card.disliked:hover {
  opacity: 0.8;
}

/* ---- playing state (border wins over liked) ---- */
.artist-card.playing {
  border-color: var(--accent);
}

/* ---- narrow card (A13): stack stats, drop 2nd tag ---- */
@container (max-width: 190px) {
  .ac-stats {
    flex-direction: column;
    gap: var(--space-2);
    align-items: center;
  }
  .ac-stat + .ac-stat {
    border-left: 0;
  }
  .ac-avis {
    border-left: 0;
    padding-left: 0;
    margin-left: 0;
    justify-content: center;
  }
  .ac-genre-link:nth-child(2) {
    display: none;
  }
}
</style>
