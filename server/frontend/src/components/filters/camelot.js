/* Camelot wheel — the 24 static keys stored in base (1A…12A minors, 1B…12B majors). */

const NUMBERS = Array.from({ length: 12 }, (_, i) => i + 1)

/** Row A (minors) first, then row B (majors) — the CamelotSelect grid reading order. */
export const CAMELOT_KEYS = [
  ...NUMBERS.map((n) => `${n}A`),
  ...NUMBERS.map((n) => `${n}B`),
]

/**
 * Harmonic sort for chip display: letter first (A minors before B majors),
 * then wheel number — « 5A 6A 7A 6B », the grid reading order.
 */
export function compareCamelot(a, b) {
  const la = a.slice(-1)
  const lb = b.slice(-1)
  if (la !== lb) return la < lb ? -1 : 1
  return parseInt(a, 10) - parseInt(b, 10)
}
