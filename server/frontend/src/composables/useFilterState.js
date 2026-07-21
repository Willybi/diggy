import { reactive, watch } from 'vue'
import { defaultValue } from '../components/filters/criteria.js'

/*
 * Flat filter state ↔ URL query params, 1:1 (filter-family principle 1).
 *
 * The page declares its criteria (same descriptors as FilterBar — see
 * components/filters/criteria.js) and passes ITS router/route (arguments, not
 * global imports → testable without a router mock). Default value = absent
 * param. Built-in (de)serializers per type, overridable per criterion via
 * `serialize(value) → string|undefined` / `deserialize(raw) → value` (e.g.
 * artists: ids in the URL, objects in the state).
 *
 * Built-ins:
 *   range   'bpm=120-133'   (full range → absent)
 *   multi   'keys=5A,6A'    (scalar values, comma-joined; empty → absent)
 *   segment 'inlib=mine'    (String(option.value); null → absent)
 *   toggle  'preview=1'     (false → absent)
 *   text    'label=drumcode' (trimmed; empty → absent)
 *
 * Text and range mutations debounce the URL write (250 ms); the other types
 * write immediately. Foreign query params are preserved.
 */

const DEBOUNCED_TYPES = new Set(['text', 'range'])

function paramOf(criterion) {
  return criterion.param ?? criterion.key
}

export function serializeValue(criterion, value) {
  if (criterion.serialize) return criterion.serialize(value)
  switch (criterion.type) {
    case 'range': {
      if (!Array.isArray(value)) return undefined
      const [lo, hi] = value
      if (lo <= criterion.min && hi >= criterion.max) return undefined
      return `${lo}-${hi}`
    }
    case 'multi':
      return Array.isArray(value) && value.length ? value.join(',') : undefined
    case 'segment':
      return value == null || value === '' ? undefined : String(value)
    case 'toggle':
      return value === true ? '1' : undefined
    case 'text': {
      const t = (value ?? '').trim()
      return t || undefined
    }
    default:
      return undefined
  }
}

export function deserializeValue(criterion, raw) {
  if (criterion.deserialize) return criterion.deserialize(raw)
  if (raw == null) return defaultValue(criterion)
  const s = String(Array.isArray(raw) ? raw[0] : raw)
  switch (criterion.type) {
    case 'range': {
      const m = s.match(/^(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)$/)
      if (!m) return defaultValue(criterion)
      const lo = Math.max(criterion.min, Number(m[1]))
      const hi = Math.min(criterion.max, Number(m[2]))
      if (Number.isNaN(lo) || Number.isNaN(hi) || lo > hi) return defaultValue(criterion)
      return [lo, hi]
    }
    case 'multi':
      return s ? s.split(',').filter(Boolean) : []
    case 'segment': {
      if (criterion.options) {
        const hit = criterion.options.find((o) => o.value != null && String(o.value) === s)
        return hit ? hit.value : null
      }
      return s
    }
    case 'toggle':
      return s === '1' || s === 'true'
    case 'text':
      return s
    default:
      return defaultValue(criterion)
  }
}

/**
 * @param {Array} criteria  criterion descriptors (see criteria.js)
 * @param {object} deps
 * @param {{ replace: Function }} deps.router  the page's router
 * @param {{ query: object }} deps.route       the page's current route (reactive)
 * @param {number} [deps.debounceMs=250]       text/range URL-write debounce
 * @returns {{ state: object, reset: () => void }}
 */
export function useFilterState(criteria, { router, route, debounceMs = 250 }) {
  const state = reactive({})
  for (const c of criteria) {
    state[c.key] = deserializeValue(c, (route.query || {})[paramOf(c)])
  }

  const owned = new Set(criteria.map(paramOf))

  function buildQuery() {
    const query = {}
    for (const [k, v] of Object.entries(route.query || {})) {
      if (!owned.has(k)) query[k] = v
    }
    for (const c of criteria) {
      const s = serializeValue(c, state[c.key])
      if (s !== undefined) query[paramOf(c)] = s
    }
    return query
  }

  function sameQuery(a, b) {
    const ka = Object.keys(a)
    const kb = Object.keys(b)
    if (ka.length !== kb.length) return false
    return ka.every((k) => String(a[k]) === String(b[k]))
  }

  let timer = null

  function push() {
    timer = null
    const query = buildQuery()
    // Route → state echoes serialize back to the current query: skip the write.
    if (sameQuery(query, route.query || {})) return
    router.replace({ query })
  }

  function schedulePush(immediate) {
    clearTimeout(timer)
    if (immediate) push()
    else timer = setTimeout(push, debounceMs)
  }

  for (const c of criteria) {
    watch(
      () => state[c.key],
      () => schedulePush(!DEBOUNCED_TYPES.has(c.type)),
      { deep: true },
    )
  }

  // Back/forward (or external) navigation → re-apply the URL into the state.
  watch(
    () => route.query,
    (q) => {
      for (const c of criteria) {
        const next = deserializeValue(c, (q || {})[paramOf(c)])
        if (JSON.stringify(state[c.key]) !== JSON.stringify(next)) state[c.key] = next
      }
    },
  )

  function reset() {
    for (const c of criteria) state[c.key] = defaultValue(c)
  }

  return { state, reset }
}
