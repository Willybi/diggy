/*
 * Shared criterion descriptor contract of the filter family.
 *
 * A page describes each filter criterion declaratively; FilterBar derives the
 * chips row and the badge count from it, useFilterState derives the URL sync.
 *
 * Criterion shape:
 *   {
 *     key: 'bpm',            // flat-state key (defaults to the query param name)
 *     type: 'range' | 'multi' | 'segment' | 'toggle' | 'text',
 *     label: 'BPM',          // chip label (rendered uppercase)
 *     // range:   min, max (full range = inactive criterion)
 *     // multi:   chipPerValue (true → one chip per value: styles, artistes),
 *     //          sort(a, b) (single-chip value ordering, e.g. compareCamelot),
 *     //          format(value) → display label (objects default to .name)
 *     // segment: options: [{ value, label }] — value null = « Tous » (inactive)
 *     // toggle:  valueLabel (chip value text, defaults to label)
 *     chip: false,           // opt-out: never a chip, never counted in the badge
 *                            // (e.g. the bar's own search input — the field IS
 *                            //  its own state display)
 *   }
 */

/** Default value per type — the "criterion absent" state (absent query param). */
export function defaultValue(criterion) {
  switch (criterion.type) {
    case 'range':
      return [criterion.min, criterion.max]
    case 'multi':
      return []
    case 'segment':
      return null
    case 'toggle':
      return false
    case 'text':
    default:
      return ''
  }
}

/** Whether a criterion is active (i.e. narrows the results). */
export function isActive(criterion, value) {
  switch (criterion.type) {
    case 'range':
      return Array.isArray(value) && (value[0] > criterion.min || value[1] < criterion.max)
    case 'multi':
      return Array.isArray(value) && value.length > 0
    case 'segment':
      return value != null && value !== ''
    case 'toggle':
      return value === true
    case 'text':
      return typeof value === 'string' && value.trim() !== ''
    default:
      return false
  }
}

/**
 * Badge count: a multi counts each of its values, every other active
 * criterion counts 1 (ranges, segments, toggles, texts).
 */
export function countActive(criteria, state) {
  let n = 0
  for (const c of criteria) {
    if (c.chip === false) continue
    const value = state[c.key]
    if (!isActive(c, value)) continue
    n += c.type === 'multi' ? value.length : 1
  }
  return n
}

function formatValue(criterion, value) {
  if (criterion.format) return criterion.format(value)
  if (value && typeof value === 'object') return String(value.name ?? value)
  return String(value)
}

function valueId(value) {
  return value && typeof value === 'object' ? value.id : value
}

/**
 * Canonical chips of the active state.
 * Mapping: range → 1 chip « BPM 120–133 » · multi → 1 chip (values sorted,
 * space-joined) or 1 chip PER value (chipPerValue: styles, artistes) ·
 * segment → the option label · toggle → the toggle label · text → the input.
 * Each chip carries { id, key, label, value } (+ rawValue for per-value chips).
 */
export function buildChips(criteria, state) {
  const chips = []
  for (const c of criteria) {
    if (c.chip === false) continue
    const value = state[c.key]
    if (!isActive(c, value)) continue
    switch (c.type) {
      case 'range':
        chips.push({
          id: c.key,
          key: c.key,
          label: c.label,
          value: `${formatValue(c, value[0])}–${formatValue(c, value[1])}`,
        })
        break
      case 'multi':
        if (c.chipPerValue) {
          for (const item of value) {
            chips.push({
              id: `${c.key}:${valueId(item)}`,
              key: c.key,
              label: c.label,
              value: formatValue(c, item),
              rawValue: item,
            })
          }
        } else {
          const sorted = c.sort ? [...value].sort(c.sort) : [...value]
          chips.push({
            id: c.key,
            key: c.key,
            label: c.label,
            value: sorted.map((v) => formatValue(c, v)).join(' '),
          })
        }
        break
      case 'segment': {
        const opt = (c.options || []).find((o) => o.value === value)
        chips.push({ id: c.key, key: c.key, label: c.label, value: opt ? opt.label : String(value) })
        break
      }
      case 'toggle':
        chips.push({ id: c.key, key: c.key, label: c.label, value: c.valueLabel ?? c.label })
        break
      case 'text':
        chips.push({ id: c.key, key: c.key, label: c.label, value: String(value).trim() })
        break
    }
  }
  return chips
}
