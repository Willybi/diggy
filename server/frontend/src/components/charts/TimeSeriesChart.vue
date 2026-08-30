<template>
  <div class="tsc" :class="{ 'tsc--empty': !hasData }">
    <div v-if="!hasData" class="state">Aucune donnée sur la période.</div>

    <template v-else>
      <div v-if="series.length >= 2" class="tsc-legend">
        <span v-for="s in norm" :key="s.label" class="tsc-leg">
          <span class="tsc-swatch" :style="{ background: s.color }" />
          {{ s.label }}
        </span>
      </div>

      <!-- Plot wrapper owns the responsive height var; .tsc-chart carries the CSS
           axis gutter (padding-left 52px), the SVG holds ONLY the plot area, and
           the axis labels are HTML positioned in that gutter (never <text> — a
           preserveAspectRatio="none" SVG stretches text and interpolated SVG
           <text> is created in the wrong namespace and never renders). -->
      <div class="tsc-plotwrap" :style="{ '--tsc-h-desktop': height + 'px' }">
        <div class="tsc-chart">
          <svg
            class="tsc-svg"
            viewBox="0 0 1000 300"
            preserveAspectRatio="none"
            role="img"
            :aria-label="ariaLabel"
          >
            <!-- 5 horizontal gridlines, full plot width -->
            <line
              v-for="t in yTicks"
              :key="`grid-${t.f}`"
              class="tsc-gridline"
              x1="0"
              :y1="t.y"
              x2="1000"
              :y2="t.y"
            />
            <!-- area under the « total » (soft) curve only (D22) -->
            <path
              v-for="(s, i) in areaSeries"
              :key="`area-${i}`"
              class="tsc-area"
              :d="areaPath(s.points)"
              :style="{ fill: s.color }"
            />
            <!-- series lines -->
            <path
              v-for="(s, i) in norm"
              :key="`line-${i}`"
              class="tsc-line"
              :d="linePath(s.points)"
              :style="{ stroke: s.color }"
            />
          </svg>

          <span
            v-for="t in yTicks"
            :key="`y-${t.f}`"
            class="tsc-ylabel"
            :style="{ top: `calc(var(--tsc-h) * ${t.k})` }"
          >
            {{ yFormat(t.v) }}
          </span>
        </div>

        <div class="tsc-xaxis">
          <span v-for="(t, i) in xTicks" :key="`x-${i}`" class="tsc-xlabel">{{ fmtX(t.ts) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // series: [{ label, color (a `var(--…)` string), points: [{ t, v }] }]
  series: { type: Array, default: () => [] },
  height: { type: Number, default: 260 },
  yFormat: { type: Function, default: (v) => String(Math.round(v)) },
  // Optional x-axis formatter; defaults to DD/MM from the parsed timestamp.
  xFormat: { type: Function, default: null },
  showArea: { type: Boolean, default: false },
})

// ── Plot geometry ── viewBox is the plot area ONLY (1000×300), with tiny inner
// top/bottom margins so the stroke isn't clipped at the extremes. The axis gutter
// lives in CSS (padding-left on .tsc-chart), never inside the viewBox.
const VW = 1000
const VH = 300
const TOP_PAD = 8
const BOT_PAD = 6
const USABLE = VH - TOP_PAD - BOT_PAD
const BASE_Y = VH - BOT_PAD

function toTs(t) {
  if (t == null) return NaN
  if (typeof t === 'number') return t
  return new Date(t).getTime()
}

// Normalise: numeric ts + v, drop invalids, sort by time.
const norm = computed(() =>
  props.series.map((s) => ({
    label: s.label,
    color: s.color || 'var(--chart-neutral)',
    points: (s.points || [])
      .map((p) => ({ ts: toTs(p.t), v: Number(p.v) }))
      .filter((p) => Number.isFinite(p.ts) && Number.isFinite(p.v))
      .sort((a, b) => a.ts - b.ts),
  })),
)

const hasData = computed(() => norm.value.some((s) => s.points.length > 0))

// Area fill (when show-area) goes ONLY under the « total » curve — identified by
// its `-soft` colour token (D22: soft variant = total/parked). Filling under the
// « à traiter » line too would muddy the 2-tone band.
const areaSeries = computed(() =>
  props.showArea ? norm.value.filter((s) => /-soft/.test(s.color) && s.points.length) : [],
)

const allTs = computed(() => {
  const set = new Set()
  for (const s of norm.value) for (const p of s.points) set.add(p.ts)
  return [...set].sort((a, b) => a - b)
})
const tMin = computed(() => (allTs.value.length ? allTs.value[0] : 0))
const tMax = computed(() => (allTs.value.length ? allTs.value[allTs.value.length - 1] : 1))

const vMax = computed(() => {
  let m = 0
  for (const s of norm.value) for (const p of s.points) if (p.v > m) m = p.v
  return m
})

function niceCeil(v) {
  if (!(v > 0)) return 1
  const pow = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / pow
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10
  return step * pow
}
const niceMax = computed(() => niceCeil(vMax.value))

function fx(ts) {
  if (tMax.value === tMin.value) return 0.5
  return (ts - tMin.value) / (tMax.value - tMin.value)
}
function fy(v) {
  return niceMax.value ? Math.min(1, Math.max(0, v / niceMax.value)) : 0
}
function X(ts) {
  return fx(ts) * VW
}
function Y(v) {
  return TOP_PAD + (1 - fy(v)) * USABLE
}

function linePath(pts) {
  if (!pts.length) return ''
  return pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.ts).toFixed(2)} ${Y(p.v).toFixed(2)}`).join(' ')
}
function areaPath(pts) {
  if (!pts.length) return ''
  const body = pts.map((p) => `L${X(p.ts).toFixed(2)} ${Y(p.v).toFixed(2)}`).join(' ')
  const x0 = X(pts[0].ts).toFixed(2)
  const xN = X(pts[pts.length - 1].ts).toFixed(2)
  return `M${x0} ${BASE_Y} ${body} L${xN} ${BASE_Y} Z`
}

// yTicks carry both the SVG y (0–300) for the gridline and `k` (fraction of the
// plot height) for the HTML label's `top: calc(var(--tsc-h) * k)`.
const yTicks = computed(() =>
  [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const y = TOP_PAD + (1 - f) * USABLE
    return { f, v: niceMax.value * f, y, k: y / VH }
  }),
)

const xTicks = computed(() => {
  const ts = allTs.value
  if (!ts.length) return []
  if (tMax.value === tMin.value) return [{ ts: ts[0], f: 0.5 }]
  const N = 4
  const out = []
  for (let i = 0; i <= N; i++) {
    out.push({ ts: tMin.value + ((tMax.value - tMin.value) * i) / N, f: i / N })
  }
  return out
})

function defaultXFormat(ts) {
  const d = new Date(ts)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}`
}
function fmtX(ts) {
  return props.xFormat ? props.xFormat(ts) : defaultXFormat(ts)
}

const ariaLabel = computed(() => {
  const names = norm.value.filter((s) => s.points.length).map((s) => s.label)
  return names.length ? `Graphique temporel : ${names.join(', ')}` : 'Graphique temporel'
})
</script>

<style scoped>
.tsc {
  width: 100%;
}
.tsc--empty {
  min-height: 60px;
}
.tsc .state {
  /* diverges from canonical .state: chart-local, compact, left-aligned */
  padding: var(--space-4) 0;
  font-size: var(--fs-sm);
}
.tsc-legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.tsc-leg {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-2);
}
.tsc-swatch {
  width: 9px;
  height: 9px;
  border-radius: var(--r-xs);
  flex: none;
}

/* Responsive plot height carried by a stylesheet var (NOT inline) so the 859px
   container query can override it and keep the SVG and the HTML labels in sync. */
.tsc-plotwrap {
  --tsc-h: var(--tsc-h-desktop, 260px);
}
.tsc-chart {
  position: relative;
  height: var(--tsc-h);
  padding-left: 52px;
  padding-right: 12px;
}
.tsc-svg {
  display: block;
  width: 100%;
  height: var(--tsc-h);
  overflow: visible;
}
.tsc-gridline {
  stroke: var(--chart-grid);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.tsc-area {
  opacity: 0.14;
  stroke: none;
}
.tsc-line {
  fill: none;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}
/* Y labels: HTML, absolute in the 52px CSS gutter, aligned to the gridlines. */
.tsc-ylabel {
  position: absolute;
  left: 0;
  width: 46px;
  text-align: right;
  transform: translateY(-50%);
  font: 400 9px/1 var(--font-mono);
  color: var(--chart-axis);
  white-space: nowrap;
  pointer-events: none;
}
/* X labels: HTML row under the plot, same left/right bounds as the plot area. */
.tsc-xaxis {
  display: flex;
  justify-content: space-between;
  padding: var(--space-1) 12px 0 52px;
  font: 400 9px/1 var(--font-mono);
  color: var(--chart-axis);
}
.tsc-xlabel {
  white-space: nowrap;
}

@container (max-width: 859px) {
  .tsc-plotwrap {
    --tsc-h: 200px;
  }
}
</style>
