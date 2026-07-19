<template>
  <div
    class="track-card"
    :class="{
      playing,
      'has-end': !!$slots.end,
      'has-duration': showDuration,
      'has-position': position != null,
      'has-timecode': !!timecode,
      'state-id': isId,
      'state-unresolved': isUnresolved,
    }"
  >
    <span v-if="position != null" class="tk-pos">{{ position }}</span>

    <div class="tk-art">
      <Artwork size="row" :src="coverSrc" :alt="track.title" :in-lib="artInLib" />
      <button
        v-if="showPlay"
        class="tk-play"
        :class="{ playing }"
        :aria-label="playing ? 'Pause' : `Écouter ${track.title}`"
        @click.stop="emitPlay"
      >
        <svg v-if="playing" class="tk-play-icon" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="5" width="4" height="14" />
          <rect x="14" y="5" width="4" height="14" />
        </svg>
        <svg v-else class="tk-play-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      </button>
    </div>

    <div class="tk-tx">
      <span class="tk-title" :class="{ 'tk-title--id': isId }">{{ titleText }}</span>
      <span v-if="showArtist" class="tk-artist">
        <template v-if="isId">non identifié</template>
        <template v-else-if="isUnresolved">{{ track.artist }}</template>
        <template v-else-if="track.artists && track.artists.length">
          <template v-for="(a, i) in track.artists" :key="a.id">
            <span v-if="i > 0" class="tk-artist-sep">, </span>
            <RouterLink :to="`/artist/${a.id}`" class="tk-artist-link" @click.stop>
              {{ a.name }}
            </RouterLink>
          </template>
        </template>
        <template v-else>{{ track.artist }}</template>
      </span>
    </div>

    <span class="tk-bpm" :class="{ 'tk-bpm--empty': bpmEmpty }">{{ bpmText }}</span>
    <span class="tk-key" :class="{ 'tk-key--empty': keyEmpty }">{{ keyText }}</span>
    <span v-if="showDuration" class="tk-dur" :class="{ 'tk-dur--empty': durEmpty }">{{
      durText
    }}</span>

    <template v-if="timecode">
      <a
        v-if="timecode.href"
        class="tk-tc tk-tc--link"
        :href="timecode.href"
        target="_blank"
        rel="noopener"
        @click.stop
        >{{ fmtCue(timecode.ms) }}</a
      >
      <span v-else class="tk-tc">{{ fmtCue(timecode.ms) }}</span>
    </template>

    <span v-if="$slots.end" class="tk-end"><slot name="end"></slot></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Artwork from './Artwork.vue'
import { fmtBpm, fmtMs, fmtCue } from '../utils/format'

const props = defineProps({
  // { id, title, artist?, artists?: [{ id, name }], bpm, key, duration_ms?, has_artwork, has_preview, in_lib }
  track: { type: Object, required: true },
  showArtist: { type: Boolean, default: false },
  // Opt-in duration column (m:ss / h:mm:ss) inserted between Key and the end slot.
  showDuration: { type: Boolean, default: false },
  playing: { type: Boolean, default: false },
  // --- Set-row extension (all optional; absent = current behavior, bit-for-bit) ---
  // Order index (# column at the head of the grid). Pure ordering, never a link.
  position: { type: Number, default: undefined },
  // Timecode column between duration and the end slot. `href` → external link,
  // otherwise plain text; `ms` null → em dash. The page builds the href.
  timecode: { type: Object, default: undefined }, // { ms: number|null, href?: string }
  // 'id' = unidentified row (title "ID", muted, non-interactive);
  // 'unresolved' = read in the source but absent from the catalog (raw text, no link).
  state: {
    type: String,
    default: undefined,
    validator: (v) => v === undefined || v === 'id' || v === 'unresolved',
  },
})
const emit = defineEmits(['play'])

const isId = computed(() => props.state === 'id')
const isUnresolved = computed(() => props.state === 'unresolved')

// Same cover convention as the existing views. No artwork (or a special state,
// which is always a placeholder) → Artwork placeholder.
const coverSrc = computed(() =>
  !props.state && props.track.has_artwork
    ? `/storage/catalog-artworks/${props.track.id}.jpg`
    : undefined,
)
// No in-lib indicator on set rows (id/unresolved): pass undefined to hide it.
const artInLib = computed(() => (props.state ? undefined : !!props.track.in_lib))
// Never a play affordance on id/unresolved rows.
const showPlay = computed(() => props.track.has_preview && !props.state)

const titleText = computed(() => (isId.value ? 'ID' : props.track.title))
// id → empty cells (the track itself is unknown, no dashes);
// unresolved → em dash (data unknown); otherwise the real value.
const bpmText = computed(() => {
  if (isId.value) return ''
  if (isUnresolved.value) return '—'
  return fmtBpm(props.track.bpm)
})
const keyText = computed(() => {
  if (isId.value) return ''
  if (isUnresolved.value) return '—'
  // Missing key on a normal row → em dash (unified "missing data" language),
  // dimmed via .tk-key--empty rather than the key accent.
  return props.track.key || '—'
})
const durText = computed(() => {
  if (isId.value) return ''
  if (isUnresolved.value) return '—'
  return fmtMs(props.track.duration_ms)
})
// Dimmed dash only for a genuinely-missing normal cell (states color their own cells).
const bpmEmpty = computed(() => !props.state && !props.track.bpm)
const keyEmpty = computed(() => !props.state && !props.track.key)
const durEmpty = computed(() => !props.state && !props.track.duration_ms)

function emitPlay() {
  emit('play')
}
</script>

<style scoped>
.track-card {
  /* Composable columns: an empty custom prop drops out of the template, a set one
     adds its track. Order: position · art · title · bpm · key · duration · timecode · end.
     Default (no extension props) resolves to `36px 1fr 42px 30px` — unchanged. */
  --col-pos: ;
  --col-bpm: 42px;
  --col-dur: ;
  --col-tc: ;
  --col-end: ;
  display: grid;
  grid-template-columns:
    var(--col-pos) 36px minmax(0, 1fr) var(--col-bpm) 30px var(--col-dur) var(--col-tc)
    var(--col-end);
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition:
    background 0.12s,
    border-color 0.12s;
}
.track-card.has-position {
  --col-pos: 28px;
}
/* Duration column (44px) inserted between Key and the timecode/end slots. */
.track-card.has-duration {
  --col-dur: 44px;
}
/* Timecode column (58px, fits 1:57:32) between duration and the end slot. */
.track-card.has-timecode {
  --col-tc: 58px;
}
.track-card.has-end {
  --col-end: auto;
}
.track-card:hover {
  background: var(--surface-2);
  border-color: var(--line-2);
}
.track-card.playing,
.track-card.playing:hover {
  background: var(--accent-wash);
}

/* Set-row states — visually withdrawn, non-interactive (hover stays neutral). */
.track-card.state-id {
  background: var(--bg);
  cursor: default;
}
.track-card.state-id:hover {
  background: var(--bg);
  border-color: var(--line);
}
.track-card.state-id .tk-art {
  opacity: 0.55;
}
.track-card.state-unresolved {
  cursor: default;
}
.track-card.state-unresolved:hover {
  background: var(--surface);
  border-color: var(--line);
}
.track-card.state-unresolved .tk-bpm,
.track-card.state-unresolved .tk-key,
.track-card.state-unresolved .tk-dur {
  color: var(--ink-3);
}

/* Position — pure order index, mono, right-aligned, no zero-padding. */
.tk-pos {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
  text-align: right;
}

.tk-art {
  position: relative;
  width: 36px;
  height: 36px;
  flex: none;
}
.tk-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: var(--r-xs);
  background: var(--overlay-soft);
  color: var(--overlay-text);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s;
}
.track-card:hover .tk-play,
.tk-play.playing {
  opacity: 1;
}
.tk-play-icon {
  width: 16px;
  height: 16px;
}

.tk-tx {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.tk-title {
  font: 600 var(--fs-sm)/1.2 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* "ID" placeholder title on an unidentified row — mono, withdrawn. */
.tk-title--id {
  font-family: var(--font-mono);
  color: var(--ink-3);
}
.tk-artist {
  font: 400 var(--fs-xs)/1.2 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* Clickable artists — same voice as the plain string, underline on hover only. */
.tk-artist-link {
  color: inherit;
  text-decoration: none;
  transition: color 0.12s;
}
.tk-artist-link:hover {
  color: var(--ink);
  text-decoration: underline;
}
.tk-artist-sep {
  color: var(--ink-3);
}

.tk-bpm {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
  text-align: right;
}
.tk-key {
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--accent-ink);
}
/* Missing BPM/Key on a normal row → dimmed dash (grid alignment preserved,
   same "missing data" language as .tk-dur--empty). */
.tk-bpm--empty,
.tk-key--empty {
  color: var(--ink-3);
}
/* Duration — same voice as BPM (mono, --ink-2, right-aligned); the Key keeps the accent. */
.tk-dur {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
  text-align: right;
}
/* Missing duration → dimmer dash (grid alignment preserved). */
.tk-dur--empty {
  color: var(--ink-3);
}

/* Timecode — mono, right-aligned. Plain text is --ink-3; a link is --ink-2 →
   --ink on hover (the voice distinguishes clickable from static, no icon). */
.tk-tc {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
  text-align: right;
  text-decoration: none;
}
.tk-tc--link {
  color: var(--ink-2);
  transition: color 0.12s;
}
.tk-tc--link:hover {
  color: var(--ink);
  text-decoration: underline;
}

.tk-end {
  display: inline-flex;
  align-items: center;
}

/* No hover on touch → play stays visible on narrow containers (page container query). */
@container (max-width: 640px) {
  .tk-play {
    opacity: 1;
  }
  /* Duration is secondary — drop it (and its column); BPM/Key stay by default.
     Same specificity as the base setter but later in source order → it wins. */
  .track-card.has-duration {
    --col-dur: ;
  }
  .tk-dur {
    display: none;
  }
  /* Set rows (timecode present): the timecode is the axis of the set, so BPM also
     drops (S9) — the room goes to the title and the timecode. Grid becomes
     `28px 36px 1fr 30px 58px`. Without a timecode, BPM stays (zero regression). */
  .track-card.has-timecode {
    --col-bpm: ;
  }
  .track-card.has-timecode .tk-bpm {
    display: none;
  }
}
</style>
