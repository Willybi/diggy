import { watch } from 'vue'

/**
 * Two-way mirror between a set of plain refs and the URL query string.
 *
 * For listing views that keep their filters as local refs (the card grids:
 * sort / family / search / opinion mode) rather than the FilterBar criteria
 * model that `useFilterState` serves — reusing that would mean rebinding every
 * control to its `state`. This keeps the existing refs untouched and just
 * mirrors them: a filter change writes the URL, and a back/forward return (or a
 * pasted link) re-applies the URL into the refs, so the list comes back with the
 * exact same filters. Foreign query params are preserved; a value equal to its
 * default is omitted (clean URLs); text-ish fields debounce the write.
 *
 * @param {Array<{ ref: import('vue').Ref, param: string, default: any, debounce?: boolean }>} fields
 * @param {object} deps
 * @param {{ replace: Function }} deps.router  the view's router
 * @param {{ query: object }} deps.route       the view's reactive route
 * @param {number} [deps.debounceMs=300]
 */
export function useUrlSync(fields, { router, route, debounceMs = 300 }) {
  function coerce(field, raw) {
    const value = Array.isArray(raw) ? raw[0] : raw
    if (typeof field.default === 'number') return Number(value)
    if (typeof field.default === 'boolean') return value === 'true' || value === '1'
    return String(value)
  }

  function isDefault(field) {
    const v = field.ref.value
    return v == null || String(v).trim() === '' || String(v) === String(field.default)
  }

  // Hydrate refs from the URL once, BEFORE the view registers its own filter
  // watchers, so this initial write is silent (no spurious refetch on mount).
  for (const field of fields) {
    const raw = route.query?.[field.param]
    if (raw != null) field.ref.value = coerce(field, raw)
  }

  let timer = null
  function write() {
    timer = null
    const query = { ...(route.query || {}) }
    for (const field of fields) {
      if (isDefault(field)) delete query[field.param]
      else query[field.param] = String(field.ref.value).trim()
    }
    if (sameQuery(query, route.query || {})) return
    router.replace({ query })
  }

  function schedule(debounce) {
    clearTimeout(timer)
    if (debounce) timer = setTimeout(write, debounceMs)
    else write()
  }

  for (const field of fields) {
    watch(field.ref, () => schedule(!!field.debounce))
  }

  // Back/forward (or external) navigation → re-apply the URL into the refs.
  watch(
    () => route.query,
    (q) => {
      for (const field of fields) {
        const raw = (q || {})[field.param]
        const next = raw == null ? field.default : coerce(field, raw)
        if (String(field.ref.value) !== String(next)) field.ref.value = next
      }
    },
  )
}

function sameQuery(a, b) {
  const ka = Object.keys(a)
  const kb = Object.keys(b)
  if (ka.length !== kb.length) return false
  return ka.every((k) => String(a[k]) === String(b[k]))
}
