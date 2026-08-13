<template>
  <!-- Shared virtualised, sortable track table for Explorer & Radar. It owns the
       thead, the windowed body (spacers + visible slice), the loading skeleton,
       the empty/error states and ALL of the table CSS (incl. the container-query
       column drops). The consuming view keeps the data/fetch/windowing plumbing
       and hands the already-computed state down via props, receiving intents back
       as events. Divergences between the two pages are injected, never hardcoded:
         - the Durée column is opt-in (`show-duration`), Explorer only ;
         - the Radar score columns (Tendance / Pour toi) are injected through the
           `head-extra` / `row-extra` slots — they render in the VIEW's scope
           (ScoreRing + velocity + active-column band stay in RadarView) ;
         - the responsive palier layout is variant-scoped (`tt-table--<variant>`)
           because a shared column drops at a DIFFERENT container width per view
           (e.g. BPM never drops in Explorer but drops at 699px in Radar), which
           is not expressible as a single parametric set of breakpoints. -->
  <section class="tt-table" :class="`tt-table--${variant}`" aria-label="Résultats">
    <div v-if="!isEmpty && !isError" class="tt-thead">
      <span class="tt-th"></span>
      <button
        v-if="trackSortable"
        class="tt-th tt-th--btn"
        :class="{ 'is-sorted': sort === 'title' }"
        type="button"
        @click="emit('header-sort', 'title')"
      >
        Track<span v-if="sort === 'title'" class="tt-arr">{{ arrow }}</span>
      </button>
      <span v-else class="tt-th">Track</span>
      <span class="tt-th col-style">Style</span>
      <button
        class="tt-th tt-th--btn tt-th--right col-bpm"
        :class="{ 'is-sorted': sort === 'bpm' }"
        type="button"
        @click="emit('header-sort', 'bpm')"
      >
        BPM<span v-if="sort === 'bpm'" class="tt-arr">{{ arrow }}</span>
      </button>
      <button
        v-if="keySortable"
        class="tt-th tt-th--btn col-key"
        :class="{ 'is-sorted': sort === 'key' }"
        type="button"
        @click="emit('header-sort', 'key')"
      >
        Key<span v-if="sort === 'key'" class="tt-arr">{{ arrow }}</span>
      </button>
      <span v-else class="tt-th col-key">Key</span>
      <button
        v-if="showDuration"
        class="tt-th tt-th--btn tt-th--right col-dur"
        :class="{ 'is-sorted': sort === 'duration_ms' }"
        type="button"
        @click="emit('header-sort', 'duration_ms')"
      >
        Durée<span v-if="sort === 'duration_ms'" class="tt-arr">{{ arrow }}</span>
      </button>
      <slot name="head-extra" />
      <span class="tt-th tt-th--avis">Avis</span>
    </div>

    <!-- Loading skeleton : 8 ghost rows in the exact grid -->
    <div v-if="initialLoading" class="tt-body" aria-hidden="true">
      <div v-for="i in 8" :key="i" class="tt-row tt-row--skel" :style="{ '--i': i - 1 }">
        <span class="tt-cell"><span class="sk sk-play"></span></span>
        <span class="tt-cell tt-cell--track">
          <span class="sk sk-art"></span>
          <span class="tt-tx">
            <span class="sk sk-line sk-line--title"></span>
            <span class="sk sk-line sk-line--sub"></span>
          </span>
        </span>
        <span class="tt-cell col-style"><span class="sk sk-line sk-line--tag"></span></span>
        <span class="tt-cell tt-cell--right col-bpm"
          ><span class="sk sk-line sk-line--num"></span
        ></span>
        <span class="tt-cell col-key"><span class="sk sk-line sk-line--num"></span></span>
        <span v-if="showDuration" class="tt-cell tt-cell--right col-dur"
          ><span class="sk sk-line sk-line--num"></span
        ></span>
        <span
          v-for="(shape, s) in extraSkeleton"
          :key="`x${s}`"
          class="tt-cell tt-cell--extra-skel"
        >
          <span class="sk" :class="shape === 'disc' ? 'sk-disc' : 'sk-line sk-line--num'"></span>
        </span>
        <span class="tt-cell tt-cell--avis"
          ><span class="sk sk-round"></span><span class="sk sk-round"></span
        ></span>
      </div>
    </div>

    <!-- Error state : a fetch failure is not an empty result (offer a retry) -->
    <div v-else-if="isError" class="tt-empty">
      <svg
        class="tt-empty-ic"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5" />
        <path d="M12 16h.01" />
      </svg>
      <p class="tt-empty-title">Erreur de chargement</p>
      <p class="tt-empty-sub">Impossible de récupérer les résultats. Réessaie dans un instant.</p>
      <button class="btn" type="button" @click="emit('retry')">Réessayer</button>
    </div>

    <!-- Empty state : removable chips repair the search -->
    <div v-else-if="isEmpty" class="tt-empty">
      <svg
        class="tt-empty-ic"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.2-3.2" />
        <path d="M4 4l14 14" />
      </svg>
      <p class="tt-empty-title">Aucun résultat avec ces filtres</p>
      <p class="tt-empty-sub">Retire un critère ci-dessous ou réinitialise la recherche.</p>
      <div v-if="activeChips.length" class="tt-empty-chips">
        <FilterChip
          v-for="chip in activeChips"
          :key="chip.id"
          :label="chip.label"
          :value="chip.value"
          empty
          @remove="emit('remove-chip', chip)"
        />
      </div>
      <button class="btn" type="button" @click="emit('reset')">
        Réinitialiser tous les filtres
      </button>
    </div>

    <!-- Windowed rows : only the visible slice is rendered between spacers -->
    <template v-else>
      <div ref="bodyEl" class="tt-body">
        <div :style="{ height: padTop + 'px' }" aria-hidden="true"></div>
        <div
          v-for="e in windowItems"
          :key="e.id"
          class="tt-row"
          :class="{
            playing: isCurrent(e.id),
            liked: e.avis === 'liked',
            disliked: e.avis === 'disliked',
          }"
          @click="emit('row-click', e)"
        >
          <span class="tt-cell tt-cell--play">
            <button
              v-if="e.has_preview"
              class="tt-pbtn"
              :class="{ 'tt-pbtn--playing': isCurrent(e.id) }"
              type="button"
              :aria-label="`Écouter ${e.title}`"
              @click.stop="emit('play', e)"
            >
              <svg
                v-if="!(isCurrent(e.id) && playing)"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M8 5.5v13l11-6.5z" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <rect x="7" y="5" width="3.4" height="14" rx="1" />
                <rect x="13.6" y="5" width="3.4" height="14" rx="1" />
              </svg>
            </button>
          </span>
          <span class="tt-cell tt-cell--track">
            <Artwork size="row" :src="artSrc(e)" :alt="e.title" :in-lib="e.in_lib" />
            <span class="tt-tx">
              <span class="tt-title-row">
                <span class="tt-title">{{ e.title }}</span>
                <span v-if="e.trend_rank && e.trend_rank <= 50" class="tt-rank"
                  >#{{ e.trend_rank }}</span
                >
              </span>
              <span class="tt-artists" @click.stop>
                <ArtistLinks :artists="e.artists" :fallback="e.artist" />
              </span>
            </span>
          </span>
          <span class="tt-cell col-style">
            <template v-if="e.genres?.length">
              <RouterLink
                class="tt-style-link"
                :to="`/style/${encodeURIComponent(e.genres[0].name)}`"
                @click.stop
              >
                <StyleTag
                  :name="e.genres[0].name"
                  :family="e.genres[0].pillar"
                  :depth="e.genres[0].depth"
                />
              </RouterLink>
              <span v-if="e.genres.length > 1" class="tt-more">+{{ e.genres.length - 1 }}</span>
            </template>
            <StyleTag v-else-if="e.style" :name="e.style" />
            <span v-else class="tt-null">—</span>
          </span>
          <span class="tt-cell tt-cell--right col-bpm">
            <span :class="e.bpm != null ? 'tt-bpm' : 'tt-null'"
              ><span
                v-if="e.bpm != null && e.bpm_source === 'analysis'"
                class="tt-bpm-est"
                title="BPM estimé (analyse audio)"
                aria-label="BPM estimé"
                >~</span
              >{{ e.bpm != null ? Math.round(e.bpm) : '—' }}</span
            >
          </span>
          <span class="tt-cell col-key">
            <span :class="e.key ? 'tt-key' : 'tt-null'">{{ e.key || '—' }}</span>
          </span>
          <span v-if="showDuration" class="tt-cell tt-cell--right col-dur">
            <span :class="e.duration_ms > 0 ? 'tt-dur' : 'tt-null'">{{
              e.duration_ms > 0 ? fmtMs(e.duration_ms) : '—'
            }}</span>
          </span>
          <slot name="row-extra" :row="e" />
          <span class="tt-cell tt-cell--avis" @click.stop>
            <LikeDislike :model-value="e.avis" @update:model-value="(v) => emit('avis', e, v)" />
          </span>
        </div>
        <div :style="{ height: padBottom + 'px' }" aria-hidden="true"></div>
      </div>
      <div v-if="items.length" class="tt-end">{{ hasMore ? '…' : 'Fin des résultats' }}</div>
    </template>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { fmtMs } from '../utils/format'
import FilterChip from './filters/FilterChip.vue'
import Artwork from './Artwork.vue'
import StyleTag from './StyleTag.vue'
import ArtistLinks from './ArtistLinks.vue'
import LikeDislike from './LikeDislike.vue'

defineProps({
  // Layout family: 'explorer' | 'radar'. Selects the variant-scoped responsive
  // palier CSS (grid template + column drops) — see the template comment.
  variant: { type: String, required: true },
  // Windowing state, computed by the view (useWindowedList + useVirtualWindow).
  windowItems: { type: Array, default: () => [] }, // the visible slice
  items: { type: Array, default: () => [] }, // full loaded list (end sentinel)
  padTop: { type: Number, default: 0 },
  padBottom: { type: Number, default: 0 },
  hasMore: { type: Boolean, default: false },
  // Mutually-exclusive render states, resolved by the view.
  initialLoading: { type: Boolean, default: false },
  isError: { type: Boolean, default: false },
  isEmpty: { type: Boolean, default: false },
  activeChips: { type: Array, default: () => [] }, // empty-state repair chips
  // Current effective sort field + arrow glyph, for the built-in sortable
  // headers (the field names are the API sort keys: title/bpm/key/duration_ms).
  sort: { type: String, default: null },
  arrow: { type: String, default: '' },
  // Built-in column toggles (Explorer sorts Track/Key + has Durée; Radar neither).
  trackSortable: { type: Boolean, default: false },
  keySortable: { type: Boolean, default: false },
  showDuration: { type: Boolean, default: false },
  // Ghost shapes for the skeleton cells of the injected extra columns (Radar's
  // two score discs). The REAL header/body cells come from the slots.
  extraSkeleton: { type: Array, default: () => [] },
  // Player read-state (presentational): whether a row id is the current track,
  // and whether it is actively playing (drives the row highlight + play icon).
  isCurrent: { type: Function, default: () => false },
  playing: { type: Boolean, default: false },
})

const emit = defineEmits([
  'header-sort',
  'row-click',
  'play',
  'avis',
  'retry',
  'reset',
  'remove-chip',
])

// The windowed body element, exposed so the view can wire useVirtualWindow to it
// (the view owns the windowing composables; it needs this element as `listRef`).
// A computed on the view side reads it: `computed(() => ttRef.value?.bodyEl)`.
const bodyEl = ref(null)
defineExpose({ bodyEl })

function artSrc(e) {
  return e.has_artwork ? `/storage/catalog-artworks/${e.id}.jpg` : undefined
}
</script>

<style scoped>
/* ============ TABLE — shared grid header/rows ============ */
.tt-table {
  --tt-gap: var(--space-2);
  padding-bottom: var(--space-8);
}
.tt-thead,
.tt-row {
  display: grid;
  grid-template-columns: var(--tt-grid);
  gap: var(--tt-gap);
  align-items: center;
  padding-inline: var(--page-px);
}
.tt-thead {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 36px;
  background: var(--bg);
  border-bottom: 1px solid var(--line-2);
}
.tt-th {
  font: 600 var(--fs-label) / 1 var(--font-mono);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-3);
  white-space: nowrap;
  text-align: left;
  user-select: none;
}
.tt-th--btn {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  transition: color 0.12s;
}
.tt-th--btn:hover {
  color: var(--ink-2);
}
.tt-th--btn.is-sorted {
  color: var(--accent-ink);
}
.tt-th--btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.tt-th--right {
  text-align: right;
}
.tt-th--avis {
  text-align: center;
}
.tt-arr {
  margin-left: var(--space-05);
  color: var(--accent-ink);
}

/* ============ ROWS ============ */
.tt-row {
  height: var(--row-h);
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  transition: background 0.12s;
}
.tt-row:hover {
  background: var(--surface-2);
}
.tt-row.playing,
.tt-row.playing:hover {
  background: var(--accent-wash);
}
.tt-row.liked {
  background: var(--pos-wash);
}
.tt-row.liked:hover {
  background: var(--pos-wash-2);
}
[data-theme='dark'] .tt-row.liked {
  background: var(--pos-wash-2);
}
.tt-row.disliked > .tt-cell:not(.tt-cell--avis) {
  opacity: 0.45;
  transition: opacity 0.16s;
}
.tt-row.disliked:hover > .tt-cell:not(.tt-cell--avis) {
  opacity: 0.7;
}

.tt-cell {
  min-width: 0;
}
.tt-cell--right {
  text-align: right;
}

/* ============ PLAY ============ */
.tt-pbtn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.12s,
    background 0.12s;
}
.tt-row:hover .tt-pbtn {
  opacity: 1;
}
.tt-pbtn svg {
  width: 11px;
  height: 11px;
}
.tt-pbtn--playing {
  opacity: 1;
  background: var(--accent);
  border-color: transparent;
  color: var(--on-accent);
}

/* ============ TRACK CELL ============ */
.tt-cell--track {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
/* Local sizing of the shared Artwork (brief: 38px row cover). */
.tt-cell--track :deep(.artwork--row) {
  width: 38px;
}
.tt-tx {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.tt-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.tt-title {
  font: 600 var(--fs-table) / 1.25 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tt-row.playing .tt-title {
  color: var(--accent-ink);
}
.tt-rank {
  display: inline-flex;
  align-items: center;
  padding: var(--space-05) var(--space-15);
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-nano) / 1 var(--font-mono);
  flex: none;
}
.tt-artists {
  font: 400 var(--fs-table-sm) / 1.25 var(--font-ui);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

/* ============ STYLE CELL (1 tag + « +N ») ============ */
.col-style {
  display: flex;
  align-items: center;
  gap: var(--space-15);
}
.tt-style-link {
  text-decoration: none;
  min-width: 0;
  display: inline-flex;
}
.tt-more {
  font: 500 var(--fs-nano) / 1 var(--font-mono);
  color: var(--ink-3);
  flex: none;
}

/* ============ DATA CELLS ============ */
.tt-bpm,
.tt-dur {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-2);
}
.tt-key {
  font: 600 var(--fs-table) var(--font-mono);
  color: var(--accent-ink);
}
.tt-null {
  font: 500 var(--fs-table) var(--font-mono);
  color: var(--ink-3);
}
/* "estimé" tilde prefix — BPM derived from audio analysis, not a trusted source.
   Dimmed, tooltip-carried, doesn't widen the cell (reads "~128"). */
.tt-bpm-est {
  color: var(--ink-3);
  cursor: help;
}

/* ============ AVIS (shared LikeDislike, local deltas only) ============ */
.tt-cell--avis {
  display: flex;
  justify-content: center;
}
/* Avis buttons stay visible at rest (neutral --ink-3 from LikeDislike); only
   Play is hover-revealed on desktop. Liked/disliked colored states below. */
.tt-cell--avis :deep(.ld-btn) {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border-color: transparent;
  background: transparent;
}
.tt-cell--avis :deep(.ld-btn:hover) {
  background: var(--surface-3);
}
.tt-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like),
.tt-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  opacity: 1;
}
.tt-cell--avis :deep(.ld[data-state='liked'] .ld-btn.like) {
  background: var(--pos-soft);
}
.tt-cell--avis :deep(.ld[data-state='disliked'] .ld-btn.dislike) {
  background: var(--neg-soft);
}

/* ============ END SENTINEL ============ */
.tt-end {
  font: 500 var(--fs-xs) / 1 var(--font-mono);
  color: var(--ink-3);
  text-align: center;
  padding: var(--space-4) var(--page-px) 0;
}

/* ============ SKELETON ============ */
.tt-row--skel {
  cursor: default;
}
.sk {
  display: inline-block;
  background: var(--surface-2);
  border-radius: var(--r-xs);
  animation: tt-pulse 1.4s ease-in-out infinite;
  animation-delay: calc(var(--i, 0) * 0.12s);
}
.sk-play {
  width: 30px;
  height: 30px;
  border-radius: 50%;
}
.sk-art {
  width: 38px;
  height: 38px;
  flex: none;
  background: var(--surface-3);
}
.sk-line {
  height: 10px;
}
.sk-line--title {
  width: 62%;
  background: var(--surface-3);
}
.sk-line--sub {
  width: 40%;
}
.sk-line--tag {
  width: 90px;
  height: 18px;
  border-radius: var(--r-pill);
}
.sk-line--num {
  width: 34px;
}
.sk-disc {
  width: 30px;
  height: 30px;
  border-radius: 50%;
}
.sk-round {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  margin: 0 var(--space-05);
}
/* Injected extra columns (score discs) center their ghost like the real cell. */
.tt-cell--extra-skel {
  display: flex;
  align-items: center;
  justify-content: center;
}
@keyframes tt-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

/* ============ EMPTY / ERROR STATE ============ */
.tt-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-15x) var(--page-px);
  text-align: center;
}
.tt-empty-ic {
  width: 34px;
  height: 34px;
  color: var(--ink-3);
}
.tt-empty-title {
  margin: 0;
  font: 600 var(--fs-md) / 1.3 var(--font-ui);
  color: var(--ink);
}
.tt-empty-sub {
  margin: 0;
  font: 400 var(--fs-sm) / 1.4 var(--font-ui);
  color: var(--ink-2);
}
.tt-empty-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-15);
  margin-top: var(--space-1);
}
.tt-empty .btn {
  margin-top: var(--space-2);
}

/* ============ EXPLORER LAYOUT (grid + 4-tier column drop) ============ */
/* Drop order: Durée → Style → Key → (mobile compaction). */
.tt-table--explorer {
  --tt-grid: 44px minmax(0, 1fr) 176px 56px 48px 60px 84px;
}
@container (max-width: 999px) {
  .tt-table--explorer {
    --tt-grid: 44px minmax(0, 1fr) 176px 56px 48px 84px;
  }
  .tt-table--explorer .col-dur {
    display: none;
  }
}
@container (max-width: 859px) {
  .tt-table--explorer {
    --tt-grid: 44px minmax(0, 1fr) 56px 48px 84px;
  }
  .tt-table--explorer .col-style {
    display: none;
  }
}
@container (max-width: 699px) {
  .tt-table--explorer {
    --tt-grid: 44px minmax(0, 1fr) 56px 84px;
  }
  .tt-table--explorer .col-key {
    display: none;
  }
}
@container (max-width: 639px) {
  .tt-table--explorer {
    --tt-grid: 40px minmax(0, 1fr) 46px 76px;
    --tt-gap: var(--space-1);
  }
}

/* ============ RADAR LAYOUT (grid + column drop preserving the 2 scores) ======= */
/* Score columns (Tendance/Pour toi), Play, Track and Avis survive to 375px.
   Drop order: Style → Key → BPM. */
.tt-table--radar {
  --tt-grid: 44px minmax(0, 1fr) 176px 56px 48px 64px 64px 84px;
}
@container (max-width: 999px) {
  .tt-table--radar {
    --tt-grid: 44px minmax(0, 1fr) 56px 48px 64px 64px 84px;
  }
  .tt-table--radar .col-style {
    display: none;
  }
}
@container (max-width: 859px) {
  .tt-table--radar {
    --tt-grid: 44px minmax(0, 1fr) 56px 64px 64px 84px;
  }
  .tt-table--radar .col-key {
    display: none;
  }
}
@container (max-width: 699px) {
  .tt-table--radar {
    --tt-grid: 44px minmax(0, 1fr) 64px 64px 84px;
  }
  .tt-table--radar .col-bpm {
    display: none;
  }
}
@container (max-width: 639px) {
  .tt-table--radar {
    --tt-grid: 40px minmax(0, 1fr) 52px 52px 76px;
    --tt-gap: var(--space-1);
  }
}

/* ============ RESPONSIVE — shared mobile table rules ============ */
@container (max-width: 639px) {
  .tt-thead,
  .tt-row {
    padding-inline: var(--page-px-mobile);
  }
  .tt-end {
    padding-inline: var(--page-px-mobile);
  }
  .tt-empty {
    padding-inline: var(--page-px-mobile);
  }
  /* Touch: play always visible (avis is already visible at rest). */
  .tt-pbtn {
    opacity: 1;
  }
}
</style>
