// Pure segmentation logic for the manual artist-split tool (Lot 2).
//
// The manual splitter turns a malformed artist string ("Adam Beyer & Ida
// Engberg", "Foo Bar (Original Mix)") into N artist tokens. It works on three
// layers, all pure and testable here (no Vue, no DOM):
//   1. UNITS    — the raw string cut on the detected separator (or on spaces
//                 when none is found). Atomic, immutable.
//   2. CUTS     — a boolean per unit-boundary: a cut ON keeps the two units in
//                 separate segments, OFF merges them back. Toggling cuts is what
//                 makes the split N-ary.
//   3. KEEP     — a boolean per unit: a segment marked "à supprimer" (an artefact
//                 like "(Original Mix)") drops out of the emitted tokens.
// The component reads `computeSegments` for display and `keptTokens` for output.

// Separator list kept in PARITY with the backend auto-split detection
// (workers/tasks/artists.py: FEAT_RE + PRESENTS_RE + X/AND/Y/E_RE + " & "/" + "/
// "|"), with the more specific variants FIRST so detectSeparator picks the
// longest match. This list drives DETECTION ONLY (which "·" boundaries to show +
// the default segmentation of the component) — the real split decision stays
// backend-side, so a front-side false positive on a stylized name is harmless.
//
// Word separators (feat/ft/vs/presents/pres/x/and/y/e) are matched
// case-insensitively (the backend uses re.IGNORECASE); punctuation separators
// (/ | ; , & +) are case-agnostic anyway. '/' and ';' are FRONT-ONLY review
// hints (never a backend auto-split): '/' ("AC/DC"), ';' ("A; B").
export const SEPARATORS = [
  '/',
  ' & ',
  ' + ',
  '|',
  ';',
  ', ',
  ' featuring ',
  ' feat. ',
  ' feat ',
  ' ft. ',
  ' ft ',
  ' vs. ',
  ' vs ',
  ' presents ',
  ' présente ',
  ' pres. ',
  ' pres ',
  ' and ',
  ' x ',
  ' y ',
  ' e ',
]

// First matching separator (SEPARATORS order = priority). Matched against a
// lower-cased copy so the word separators are case-insensitive, in parity with
// the backend's IGNORECASE detection.
export function detectSeparator(name) {
  const lower = (name || '').toLowerCase()
  return SEPARATORS.find((sep) => lower.includes(sep)) || null
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Split a name into atomic UNITS: on `sep` (case-insensitively, to match
// detectSeparator) when given, else on whitespace. Units are trimmed and empties
// dropped.
export function splitUnits(name, sep) {
  const raw = name || ''
  const parts = sep ? raw.split(new RegExp(escapeRegExp(sep), 'i')) : raw.split(/\s+/)
  return parts.map((p) => p.trim()).filter(Boolean)
}

// Group units into SEGMENTS by the cut boundaries. `cuts[i]` is the boundary
// between unit i and unit i+1; a cut ON closes the current segment. Each segment
// rejoins its units with `sep` (or a single space for the space-fallback).
// Returns [{ text, unitIndices }].
export function computeSegments(units, cuts, sep) {
  const join = sep || ' '
  const segments = []
  let start = 0
  for (let i = 0; i < units.length; i++) {
    const boundary = i === units.length - 1 || cuts[i]
    if (!boundary) continue
    const unitIndices = []
    for (let j = start; j <= i; j++) unitIndices.push(j)
    segments.push({
      text: unitIndices
        .map((j) => units[j])
        .join(join)
        .trim(),
      unitIndices,
    })
    start = i + 1
  }
  return segments
}

// Emitted tokens = the text of every KEPT segment (a segment is kept when at
// least one of its units is kept), trimmed and non-empty. This is the value the
// component sends to the backend as `tokens`.
export function keptTokens(units, cuts, keep, sep) {
  return computeSegments(units, cuts, sep)
    .filter((seg) => seg.unitIndices.some((j) => keep[j]))
    .map((seg) => seg.text.trim())
    .filter(Boolean)
}

// Build the initial splitter state for a raw string.
//   - initialTokens given (Flags tab): each token is a pre-made unit, all cut
//     apart and kept — the admin then merges/deletes as needed.
//   - a separator is detected: split on it, every boundary cut ON (each part its
//     own segment) → the N-ary default.
//   - no separator (malformed name): split on spaces, every boundary cut OFF
//     (the whole string is one segment) → the admin adds cuts where needed.
// `sep` is the join delimiter used to rebuild merged segments.
export function initSplitState(raw, initialTokens) {
  const detected = detectSeparator(raw)
  let units
  let defaultCut
  if (initialTokens && initialTokens.length) {
    units = initialTokens.map((t) => (t || '').trim()).filter(Boolean)
    defaultCut = true
  } else if (detected) {
    units = splitUnits(raw, detected)
    defaultCut = true
  } else {
    units = splitUnits(raw, null)
    defaultCut = false
  }
  return {
    sep: detected || ' ',
    units,
    cuts: units.slice(0, -1).map(() => defaultCut),
    keep: units.map(() => true),
  }
}
