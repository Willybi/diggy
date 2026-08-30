<template>
  <span
    class="spark"
    :style="{ width: width, height: height + 'px' }"
    role="img"
    :aria-label="ariaLabel"
  >
    <svg class="spark-svg" viewBox="0 0 120 30" preserveAspectRatio="none">
      <path
        v-if="showArea && vals.length > 1"
        class="spark-area"
        :d="areaPath"
        :style="{ fill: color }"
      />
      <path v-if="vals.length > 1" class="spark-line" :d="linePath" :style="{ stroke: color }" />
    </svg>
    <!-- Endpoint marker as an HTML dot (immune to the non-uniform viewBox scaling
         that would squash an in-SVG <circle> into an ellipse). lastX/lastY are
         expressed as a % of the wrapper box, so they map directly. -->
    <span
      v-if="vals.length"
      class="spark-dot"
      :style="{ left: lastX + '%', top: lastY + '%', background: color }"
    />
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // points: array of numbers, or of objects carrying a `v` (and optional `t`).
  points: { type: Array, default: () => [] },
  color: { type: String, default: 'var(--chart-neutral)' },
  width: { type: String, default: '100%' },
  height: { type: Number, default: 30 },
  showArea: { type: Boolean, default: true },
})

// Internal viewBox (archétype F: 120×30). preserveAspectRatio="none" stretches it
// to the wrapper box, so the aspect only sets the coordinate space, not the shape.
const VW = 120
const VH = 30

const vals = computed(() =>
  props.points
    .map((p) => (typeof p === 'number' ? p : Number(p && p.v)))
    .filter((v) => Number.isFinite(v)),
)

const bounds = computed(() => {
  const vs = vals.value
  if (!vs.length) return { min: 0, max: 1 }
  let min = Infinity
  let max = -Infinity
  for (const v of vs) {
    if (v < min) min = v
    if (v > max) max = v
  }
  if (min === max) {
    min -= 1
    max += 1
  }
  return { min, max }
})

function px(i) {
  const n = vals.value.length
  return n <= 1 ? VW / 2 : (i / (n - 1)) * VW
}
function py(v) {
  const { min, max } = bounds.value
  // Pad 8% top/bottom so the stroke isn't clipped at the extremes.
  const f = (v - min) / (max - min)
  return VH - (0.08 * VH + f * 0.84 * VH)
}

const linePath = computed(() =>
  vals.value.map((v, i) => `${i ? 'L' : 'M'}${px(i).toFixed(2)} ${py(v).toFixed(2)}`).join(' '),
)
const areaPath = computed(() => {
  const vs = vals.value
  if (vs.length < 2) return ''
  const body = vs.map((v, i) => `L${px(i).toFixed(2)} ${py(v).toFixed(2)}`).join(' ')
  return `M0 ${VH} ${body} L${VW} ${VH} Z`
})

const lastX = computed(() => (px(vals.value.length - 1) / VW) * 100)
const lastY = computed(() => (py(vals.value[vals.value.length - 1]) / VH) * 100)

const ariaLabel = computed(() => `Tendance (${vals.value.length} points)`)
</script>

<style scoped>
.spark {
  position: relative;
  display: inline-block;
  vertical-align: middle;
}
.spark-svg {
  width: 100%;
  height: 100%;
  display: block;
  overflow: visible;
}
.spark-line {
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}
.spark-area {
  opacity: 0.14;
  stroke: none;
}
.spark-dot {
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid var(--surface);
  pointer-events: none;
}
</style>
