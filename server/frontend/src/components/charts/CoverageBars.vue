<template>
  <div class="cb">
    <!-- ── Complétude globale : buckets dérivés de l'histogramme completeness,
         barre 100 % segmentée + légende (labels + % + counts). ── -->
    <div v-if="bucketSegs.length" class="cb-global">
      <div class="cb-global-head">
        <span class="cb-global-label">Complétude globale</span>
        <span class="cb-global-total">{{ fmtInt(total) }} titres</span>
      </div>
      <div
        class="cb-track"
        role="img"
        :aria-label="`Complétude globale sur ${fmtInt(total)} titres`"
      >
        <span
          v-for="seg in bucketSegs"
          :key="seg.key"
          class="cb-seg"
          :style="{ width: seg.pct + '%', background: seg.color }"
          :title="`${seg.label} · ${fmtInt(seg.count)} (${fmtPct(seg.pct)})`"
        />
      </div>
      <div class="cb-legend">
        <span v-for="seg in bucketSegs" :key="seg.key" class="cb-leg">
          <span class="cb-swatch" :style="{ background: seg.color }" />
          {{ seg.label }} · {{ fmtPct(seg.pct) }} ({{ fmtInt(seg.count) }})
        </span>
      </div>
    </div>

    <!-- ── Barres par dimension : part couverte (ventilée par source pour
         BPM/Key, segment « abandonnés » pour Deezer/Beatport) sur piste
         neutre = part manquante. ── -->
    <div v-if="dimRows.length" class="cb-dims">
      <div v-for="row in dimRows" :key="row.key" class="cb-row">
        <span class="cb-row-label">{{ row.label }}</span>
        <div class="cb-track" :title="`${row.label} · manquant : ${fmtInt(row.missing)}`">
          <span
            v-for="seg in row.segments"
            :key="seg.key"
            class="cb-seg"
            :style="{ width: seg.pct + '%', background: seg.color }"
            :title="`${row.label} · ${seg.label} : ${fmtInt(seg.count)} (${fmtPct(seg.pct)})`"
          />
        </div>
        <span
          class="cb-row-val"
          :title="`${fmtInt(row.covered)} couverts / ${fmtInt(total)} · ${row.detail}`"
        >
          {{ fmtPct(row.pct) }} · {{ fmtInt(row.covered) }}
        </span>
      </div>
    </div>

    <!-- ── Top combinaisons manquantes : 8 chips ✓/✗ + barre proportionnelle
         au count. ── -->
    <div v-if="combos.length" class="cb-combos">
      <div class="cb-combos-title">Combinaisons incomplètes les plus fréquentes</div>
      <div v-for="(c, i) in combos" :key="i" class="cb-combo">
        <div class="cb-chips">
          <span
            v-for="chip in c.chips"
            :key="chip.key"
            class="cb-chip"
            :class="chip.ok ? 'cb-chip--ok' : 'cb-chip--miss'"
            :title="`${chip.full} · ${chip.ok ? 'présent' : 'manquant'}`"
          >
            {{ chip.ok ? '✓' : '✗' }} {{ chip.short }}
          </span>
        </div>
        <div class="cb-combo-bar">
          <span class="cb-combo-fill" :style="{ width: c.pct + '%' }" />
        </div>
        <span class="cb-combo-count">{{ fmtInt(c.count) }}</span>
      </div>
    </div>

    <div v-if="!bucketSegs.length && !dimRows.length && !combos.length" class="cb-empty">
      Aucune donnée de couverture.
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// Presentational only (charts family): props in, zero fetch. `coverage` is the
// latest_snapshot.payload.coverage block written by snapshot_backlogs (L1) —
// older snapshots don't carry it, so EVERYTHING here is defensive (absent keys
// → sub-block hidden, never a crash).
const props = defineProps({
  coverage: { type: Object, default: null },
})

// ── Dimension display order + labels (UI en français) ──
const DIM_ORDER = [
  'deezer',
  'beatport',
  'bpm',
  'key',
  'genres',
  'artwork',
  'embedding',
  'artist_link',
  'preview',
  'album',
]
const DIM_LABELS = {
  deezer: 'Deezer',
  beatport: 'Beatport',
  bpm: 'BPM',
  key: 'Key',
  genres: 'Genres',
  artwork: 'Pochettes',
  embedding: 'Embeddings',
  artist_link: 'Artiste lié',
  preview: 'Preview',
  album: 'Album',
}
// Base tint per single-segment dimension (compose with the existing --chart-*
// palette, no new token).
const DIM_COLORS = {
  genres: 'var(--chart-sets)',
  artwork: 'var(--chart-albums)',
  embedding: 'var(--chart-embeddings)',
  artist_link: 'var(--chart-neutral)',
  preview: 'var(--chart-deezer-soft)',
  album: 'var(--chart-albums)',
}
// Provenance tints for the BPM/Key by-source ventilation. Unknown extra sources
// fall back on the neutral rotation below.
const SOURCE_COLORS = {
  beatport: 'var(--chart-beatport)',
  rekordbox: 'var(--chart-bpm)',
  deezer: 'var(--chart-deezer)',
  analysis: 'var(--chart-embeddings)',
  unknown: 'var(--chart-neutral)',
}
const SOURCE_FALLBACKS = ['var(--chart-sets)', 'var(--chart-albums)', 'var(--chart-neutral)']

// 8 core completeness dimensions (the top_combos flag order).
const CORE_DIMS = [
  'deezer',
  'beatport',
  'bpm',
  'key',
  'genres',
  'artwork',
  'embedding',
  'artist_link',
]
const CORE_SHORT = {
  deezer: 'DZ',
  beatport: 'BP',
  bpm: 'BPM',
  key: 'KEY',
  genres: 'GEN',
  artwork: 'COV',
  embedding: 'EMB',
  artist_link: 'ART',
}

const cov = computed(() => props.coverage || {})
const total = computed(() => {
  const t = Number(cov.value.total)
  return Number.isFinite(t) && t > 0 ? t : 0
})

function pctOf(n) {
  return total.value ? (n / total.value) * 100 : 0
}

// ── Complétude globale : histogramme {"0":n…"8":n} replié en 4 buckets. ──
const BUCKETS = [
  { key: 'full', label: '8/8 complet', color: 'var(--pos)', keys: ['8'] },
  { key: 'seven', label: '7/8', color: 'var(--accent)', keys: ['7'] },
  { key: 'mid', label: '5-6/8', color: 'var(--warn)', keys: ['5', '6'] },
  { key: 'low', label: '≤4/8', color: 'var(--neg)', keys: ['0', '1', '2', '3', '4'] },
]
const bucketSegs = computed(() => {
  const hist = cov.value.completeness
  if (!hist || typeof hist !== 'object' || !total.value) return []
  const segs = []
  for (const b of BUCKETS) {
    let count = 0
    for (const k of b.keys) {
      const n = Number(hist[k])
      if (Number.isFinite(n)) count += n
    }
    if (count > 0) segs.push({ ...b, count, pct: pctOf(count) })
  }
  return segs
})

// ── Une ligne par dimension : segments couverts (la piste --surface-3 dessous
// figure la part manquante). ──
function platformRow(key) {
  const d = cov.value[key]
  if (!d || typeof d !== 'object') return null
  const linked = Number.isFinite(Number(d.linked)) ? Number(d.linked) : 0
  const abandoned = Number.isFinite(Number(d.abandoned)) ? Number(d.abandoned) : 0
  const segments = [
    {
      key: 'linked',
      label: 'liés',
      count: linked,
      pct: pctOf(linked),
      color: `var(--chart-${key})`,
    },
  ]
  if (abandoned > 0) {
    segments.push({
      key: 'abandoned',
      label: 'abandonnés',
      count: abandoned,
      pct: pctOf(abandoned),
      color: `var(--chart-${key}-soft)`,
    })
  }
  return { covered: linked, segments, detail: `${fmtInt(abandoned)} abandonnés` }
}

function bySourceRow(key) {
  const d = cov.value[key]
  if (!d || typeof d !== 'object') return null
  const entries = Object.entries(d)
    .map(([src, n]) => [src, Number(n)])
    .filter(([, n]) => Number.isFinite(n) && n > 0)
    .sort((a, b) => b[1] - a[1])
  let fallback = 0
  const segments = entries.map(([src, n]) => ({
    key: src,
    label: src,
    count: n,
    pct: pctOf(n),
    color: SOURCE_COLORS[src] || SOURCE_FALLBACKS[fallback++ % SOURCE_FALLBACKS.length],
  }))
  const covered = entries.reduce((s, [, n]) => s + n, 0)
  return {
    covered,
    segments,
    detail: entries.map(([src, n]) => `${src} ${fmtInt(n)}`).join(' · ') || 'aucune source',
  }
}

function coveredRow(key) {
  const d = cov.value[key]
  const covered = d && Number.isFinite(Number(d.covered)) ? Number(d.covered) : null
  if (covered == null) return null
  return {
    covered,
    segments: [
      {
        key: 'covered',
        label: 'couverts',
        count: covered,
        pct: pctOf(covered),
        color: DIM_COLORS[key] || 'var(--chart-neutral)',
      },
    ],
    detail: `${fmtInt(covered)} couverts`,
  }
}

const dimRows = computed(() => {
  if (!total.value) return []
  const rows = []
  for (const key of DIM_ORDER) {
    let row
    if (key === 'deezer' || key === 'beatport') row = platformRow(key)
    else if (key === 'bpm' || key === 'key') row = bySourceRow(key)
    else row = coveredRow(key)
    if (!row) continue
    rows.push({
      key,
      label: DIM_LABELS[key],
      pct: pctOf(row.covered),
      missing: Math.max(0, total.value - row.covered),
      ...row,
    })
  }
  return rows
})

// ── Top combinaisons manquantes : chips ✓/✗ dans l'ordre des 8 dimensions
// cœur, barre proportionnelle au count max. ──
const combos = computed(() => {
  const list = Array.isArray(cov.value.top_combos) ? cov.value.top_combos : []
  const valid = list.filter((c) => c && c.dims && Number.isFinite(Number(c.count)))
  if (!valid.length) return []
  const max = Math.max(...valid.map((c) => Number(c.count)))
  return valid.map((c) => ({
    count: Number(c.count),
    pct: max ? (Number(c.count) / max) * 100 : 0,
    chips: CORE_DIMS.filter((k) => k in c.dims).map((k) => ({
      key: k,
      short: CORE_SHORT[k],
      full: DIM_LABELS[k],
      ok: !!c.dims[k],
    })),
  }))
})

// ── formatters ──
function fmtInt(n) {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  return Number(n).toLocaleString('fr-FR')
}
function fmtPct(p) {
  if (!Number.isFinite(p)) return '—'
  if (p > 0 && p < 1) return '<1 %'
  return `${Math.round(p)} %`
}
</script>

<style scoped>
.cb {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ── Piste commune : fond --surface-3 = part manquante, segments posés à
   gauche. ── */
.cb-track {
  display: flex;
  height: 14px;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  overflow: hidden;
}
.cb-seg {
  display: block;
  height: 100%;
  min-width: 0;
}
.cb-seg + .cb-seg {
  box-shadow: inset 1px 0 0 var(--surface);
}

/* ── Complétude globale ── */
.cb-global {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.cb-global-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}
.cb-global-label {
  font: 500 var(--fs-nano)/1.2 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.cb-global-total {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.cb-legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
}
.cb-leg {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-2);
}
.cb-swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: none;
}

/* ── Lignes par dimension ── */
.cb-dims {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.cb-row {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
}
.cb-row-label {
  font: 400 var(--fs-sm)/1.2 var(--font-ui);
  color: var(--ink-2);
}
.cb-row-val {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
  text-align: right;
  min-width: 9ch;
}

/* ── Top combinaisons ── */
.cb-combos {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.cb-combos-title {
  font: 500 var(--fs-nano)/1.2 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.cb-combo {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px auto;
  align-items: center;
  gap: var(--space-3);
}
.cb-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.cb-chip {
  font: 500 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.03em;
  padding: 3px var(--space-2);
  border-radius: var(--r-pill);
  white-space: nowrap;
}
.cb-chip--ok {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.cb-chip--miss {
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.cb-combo-bar {
  height: 8px;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  overflow: hidden;
}
.cb-combo-fill {
  display: block;
  height: 100%;
  border-radius: var(--r-pill);
  background: var(--chart-neutral);
}
.cb-combo-count {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-2);
  text-align: right;
  min-width: 7ch;
}

.cb-empty {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-3);
}

/* ── Palier étroit : label au-dessus de la barre, combos empilées ── */
@container (max-width: 620px) {
  .cb-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .cb-row-label {
    grid-column: 1;
  }
  .cb-row-val {
    grid-column: 2;
  }
  .cb-row .cb-track {
    grid-column: 1 / -1;
  }
  .cb-combo {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .cb-combo-bar {
    grid-column: 1;
  }
  .cb-combo-count {
    grid-column: 2;
  }
  .cb-chips {
    grid-column: 1 / -1;
  }
}
</style>
