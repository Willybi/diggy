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

      <div class="tsc-grid" :style="{ '--tsc-h': height + 'px' }">
        <div class="tsc-yaxis">
          <span
            v-for="t in yTicks"
            :key="t.f"
            class="tsc-ylabel"
            :style="{ top: (1 - t.f) * 100 + '%' }"
          >
            {{ yFormat(t.v) }}
          </span>
        </div>

        <div
          class="tsc-plot"
          role="img"
          :aria-label="ariaLabel"
          @mousemove="onMove"
          @mouseleave="onLeave"
        >
          <svg class="tsc-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
            <defs>
              <linearGradient
                v-for="(s, i) in norm"
                :id="`${uid}-g${i}`"
                :key="`${uid}-g${i}`"
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0" :style="{ stopColor: s.color }" stop-opacity="0.24" />
                <stop offset="1" :style="{ stopColor: s.color }" stop-opacity="0" />
              </linearGradient>
            </defs>

            <!-- horizontal gridlines + baseline + left axis -->
            <line
              v-for="t in yTicks"
              :key="`grid-${t.f}`"
              class="tsc-gridline"
              x1="0"
              :y1="(1 - t.f) * 100"
              x2="100"
              :y2="(1 - t.f) * 100"
            />
            <line class="tsc-axis" x1="0" y1="0" x2="0" y2="100" />

            <!-- optional area fills -->
            <template v-if="showArea">
              <path
                v-for="(s, i) in norm"
                :key="`area-${i}`"
                :d="areaPath(s.points)"
                :fill="`url(#${uid}-g${i})`"
              />
            </template>

            <!-- series lines -->
            <path
              v-for="(s, i) in norm"
              :key="`line-${i}`"
              class="tsc-line"
              :d="linePath(s.points)"
              :style="{ stroke: s.color }"
            />

            <!-- hover crosshair -->
            <line
              v-if="hover"
              class="tsc-crosshair"
              :x1="hover.f * 100"
              y1="0"
              :x2="hover.f * 100"
              y2="100"
            />
          </svg>

          <!-- last-point markers (HTML → always round, distortion-immune) -->
          <span
            v-for="(s, i) in norm"
            :key="`dot-${i}`"
            v-show="s.points.length"
            class="tsc-dot"
            :style="lastDotStyle(s)"
          />

          <!-- hover markers -->
          <template v-if="hover">
            <span
              v-for="(it, i) in hover.items"
              :key="`hd-${i}`"
              class="tsc-dot tsc-dot--hover"
              :style="dotStyle(hover.f, it.fy)"
            />
          </template>

          <div v-if="hover && hover.items.length" class="tsc-tooltip" :style="tipStyle()">
            <div class="tsc-tip-date">{{ fmtX(hover.ts) }}</div>
            <div v-for="(it, i) in hover.items" :key="`ti-${i}`" class="tsc-tip-row">
              <span class="tsc-swatch" :style="{ background: it.color }" />
              <span class="tsc-tip-label">{{ it.label }}</span>
              <span class="tsc-tip-val">{{ yFormat(it.v) }}</span>
            </div>
          </div>
        </div>

        <div class="tsc-xaxis">
          <span
            v-for="(t, i) in xTicks"
            :key="`x-${i}`"
            class="tsc-xlabel"
            :style="{ left: t.f * 100 + '%' }"
          >
            {{ fmtX(t.ts) }}
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

// Deterministic per-instance id namespace for the gradient <defs> (no Math.random,
// keeps SSR/tests stable).
let _seq = 0
_seq += 1
const uid = `tsc${_seq}`

const props = defineProps({
  // series: [{ label, color (a `var(--…)` string), points: [{ t, v }] }]
  series: { type: Array, default: () => [] },
  height: { type: Number, default: 200 },
  yFormat: { type: Function, default: (v) => String(Math.round(v)) },
  // Optional x-axis formatter; defaults to DD/MM from the parsed timestamp.
  xFormat: { type: Function, default: null },
  showArea: { type: Boolean, default: false },
})

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

function linePath(pts) {
  if (!pts.length) return ''
  return pts
    .map(
      (p, i) =>
        `${i ? 'L' : 'M'}${(fx(p.ts) * 100).toFixed(2)} ${((1 - fy(p.v)) * 100).toFixed(2)}`,
    )
    .join(' ')
}
function areaPath(pts) {
  if (!pts.length) return ''
  const body = pts
    .map((p) => `L${(fx(p.ts) * 100).toFixed(2)} ${((1 - fy(p.v)) * 100).toFixed(2)}`)
    .join(' ')
  const x0 = (fx(pts[0].ts) * 100).toFixed(2)
  const xN = (fx(pts[pts.length - 1].ts) * 100).toFixed(2)
  return `M${x0} 100 ${body} L${xN} 100 Z`
}

const yTicks = computed(() =>
  [0, 0.25, 0.5, 0.75, 1].map((f) => ({ f, v: niceMax.value * f })),
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

function lastDotStyle(s) {
  const p = s.points[s.points.length - 1]
  return { left: fx(p.ts) * 100 + '%', top: (1 - fy(p.v)) * 100 + '%', background: s.color }
}
function dotStyle(fxv, fyv) {
  return { left: fxv * 100 + '%', top: (1 - fyv) * 100 + '%' }
}

const hover = ref(null)
function onMove(e) {
  if (!allTs.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  if (!rect.width) return
  const rx = (e.clientX - rect.left) / rect.width
  let best = allTs.value[0]
  let bd = Infinity
  for (const t of allTs.value) {
    const d = Math.abs(fx(t) - rx)
    if (d < bd) {
      bd = d
      best = t
    }
  }
  const items = []
  for (const s of norm.value) {
    const p = s.points.find((pt) => pt.ts === best)
    if (p) items.push({ label: s.label, color: s.color, v: p.v, fy: fy(p.v) })
  }
  hover.value = { ts: best, f: fx(best), items }
}
function onLeave() {
  hover.value = null
}
function tipStyle() {
  if (!hover.value) return {}
  const f = hover.value.f
  return {
    left: f * 100 + '%',
    transform: f > 0.5 ? 'translateX(calc(-100% - 10px))' : 'translateX(10px)',
  }
}

const ariaLabel = computed(() => {
  const names = norm.value.filter((s) => s.points.length).map((s) => s.label)
  return names.length
    ? `Graphique temporel : ${names.join(', ')}`
    : 'Graphique temporel'
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
  font: 500 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-2);
}
.tsc-swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: none;
}
.tsc-grid {
  /* Y-axis gutter floor: its .tsc-ylabel children are all position:absolute, so
     they add nothing to the column's max-content (which would collapse to 0).
     minmax(floor, max-content) → the track takes the floor. 44px holds the worst
     realistic label: ~7 mono chars in --fs-nano ("127 000") or "100 %". */
  --tsc-yaxis-w: 44px;
  display: grid;
  grid-template-columns: minmax(var(--tsc-yaxis-w), max-content) 1fr;
  grid-template-rows: var(--tsc-h) max-content;
  column-gap: var(--space-2);
  row-gap: var(--space-1);
}
.tsc-yaxis {
  position: relative;
  grid-column: 1;
  grid-row: 1;
  width: 100%;
}
.tsc-ylabel {
  position: absolute;
  right: 0;
  transform: translateY(-50%);
  font: 400 var(--fs-nano)/1 var(--font-mono);
  color: var(--chart-axis);
  white-space: nowrap;
}
.tsc-plot {
  position: relative;
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
}
.tsc-svg {
  width: 100%;
  height: 100%;
  display: block;
  overflow: visible;
}
.tsc-gridline {
  stroke: var(--chart-grid);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.tsc-axis {
  stroke: var(--chart-axis);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
  opacity: 0.5;
}
.tsc-line {
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}
.tsc-crosshair {
  stroke: var(--chart-axis);
  stroke-width: 1;
  stroke-dasharray: 3 3;
  vector-effect: non-scaling-stroke;
}
.tsc-dot {
  position: absolute;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  border: 1.5px solid var(--surface);
  pointer-events: none;
}
.tsc-dot--hover {
  width: 9px;
  height: 9px;
  background: var(--surface);
  border-width: 2px;
  border-color: var(--ink-2);
}
.tsc-tooltip {
  position: absolute;
  top: 0;
  z-index: 2;
  min-width: 96px;
  padding: var(--space-15) var(--space-2);
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-xs);
  box-shadow: var(--shadow-md);
  pointer-events: none;
}
.tsc-tip-date {
  font: 500 var(--fs-nano)/1.2 var(--font-mono);
  color: var(--ink-3);
  margin-bottom: var(--space-1);
}
.tsc-tip-row {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font: 400 var(--fs-xs)/1.4 var(--font-ui);
  color: var(--ink);
}
.tsc-tip-label {
  color: var(--ink-2);
}
.tsc-tip-val {
  margin-left: auto;
  font-family: var(--font-mono);
  font-weight: 500;
}
.tsc-xaxis {
  position: relative;
  grid-column: 2;
  grid-row: 2;
  height: var(--space-4);
}
.tsc-xlabel {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  font: 400 var(--fs-nano)/1 var(--font-mono);
  color: var(--chart-axis);
  white-space: nowrap;
}
.tsc-xlabel:first-child {
  transform: translateX(0);
}
.tsc-xlabel:last-child {
  transform: translateX(-100%);
}
</style>
