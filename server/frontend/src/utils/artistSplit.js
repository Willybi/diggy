// Pure segmentation logic for the manual artist-split tool.
//
// The manual splitter turns a malformed artist string ("Adam Beyer & Ida
// Engberg", "Felix KI/KI") into N artist tokens. It works on three layers, all
// pure and testable here (no Vue, no DOM):
//   1. UNITS    — the raw string tokenized into atomic "words": the hard
//                 punctuation separators [, & + | ;] are spaced out first, then
//                 the string is cut on whitespace. '/' is deliberately NOT
//                 spaced out — a glued slash stays inside its unit ("KI/KI" is
//                 ONE artist) while an isolated " / " becomes its own unit —
//                 and '.'/'-' stay glued ("feat.", "Mr.", "Jay-Z"). Atomic,
//                 immutable.
//   2. CUTS     — a boolean per unit-boundary: a cut ON keeps the two units in
//                 separate segments, OFF merges them back. A separator unit
//                 (DROP_SET) starts with a cut on BOTH sides; every other
//                 boundary starts uncut (words grouped). Toggling cuts is what
//                 makes the split N-ary.
//   3. KEEP     — a boolean per unit: a separator unit starts dropped so it
//                 vanishes from the emitted tokens; a segment marked "à
//                 supprimer" (an artefact like "(Original Mix)") drops all its
//                 units, restoring it restores all of them (a restored "&"
//                 chip becomes a real token — the admin decides).
// The component reads `computeSegments` for display and `keptTokens` for output.

// ── Legacy separator detection (flag flow) ───────────────────────────────────
// Separator list kept in PARITY with the backend auto-split detection
// (workers/tasks/artists.py: FEAT_RE + PRESENTS_RE + X/AND/Y/E_RE + " & "/
// " + "/"|"), with the more specific variants FIRST so detectSeparator picks
// the longest match. Since the unit model above took over the splitter
// component, this list only gates the "Flagguer"/"Splitter" row buttons and the
// blind flagArtist tokenisation in AdminArtists — the real split decision stays
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
  // "with" collaborations, incl. the parenthesised "w"/"w." shorthand
  // ("Freddie McGregor (w The Sound Dimension)"). Mirrors the backend panel's
  // _name_is_splittable so these route to the split lane instead of being treated
  // as one linkable artist. More specific "(w." before "(w ".
  ' with ',
  '(w. ',
  '(w ',
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

// Split a name into parts on `sep` (case-insensitively, to match
// detectSeparator) when given, else on whitespace. Parts are trimmed and
// empties dropped. Legacy: only feeds the blind flagArtist tokenisation.
export function splitUnits(name, sep) {
  const raw = name || ''
  const parts = sep ? raw.split(new RegExp(escapeRegExp(sep), 'i')) : raw.split(/\s+/)
  return parts.map((p) => p.trim()).filter(Boolean)
}

// ── Unit model (tokenization) ────────────────────────────────────────────────

// Hard punctuation separators spaced out during tokenization so each always
// becomes its own unit, even glued ("A|B"). '/' is absent on purpose: glued vs
// isolated is meaningful there (see the UNITS layer above).
const HARD_PUNCT_RE = /([,&+|;])/g

// Units DROPPED by default, with a default cut on each side: the punctuation
// bullets + the multi-letter separator words (case-insensitive). The single
// letters x / y / e are deliberately NOT here — too ambiguous ("Malcolm X",
// "Ben E King") — they stay normal kept units and the admin decides.
export const DROP_SET = new Set([
  ',',
  '&',
  '+',
  '|',
  ';',
  '/',
  'and',
  'vs',
  'vs.',
  'feat',
  'feat.',
  'ft',
  'ft.',
  'featuring',
  'presents',
  'présente',
  'pres',
  'pres.',
])

// True when a unit is a separator: dropped by default + cut on each side.
export function isSeparatorUnit(unit) {
  return DROP_SET.has((unit || '').toLowerCase())
}

// Tokenize a raw artist string into atomic UNITS (words).
export function tokenizeUnits(raw) {
  return (raw || '').replace(HARD_PUNCT_RE, ' $1 ').split(/\s+/).filter(Boolean)
}

// Group units into SEGMENTS by the cut boundaries. `cuts[i]` is the boundary
// between unit i and unit i+1; a cut ON closes the current segment. A segment's
// text = its KEPT units joined by a single space (a dropped separator unit
// inside a merged segment does not appear); a fully-dropped segment falls back
// to its raw units so the struck-through chip stays readable and restorable.
// Returns [{ text, kept, unitIndices }].
export function computeSegments(units, cuts, keep) {
  const segments = []
  let start = 0
  for (let i = 0; i < units.length; i++) {
    const boundary = i === units.length - 1 || cuts[i]
    if (!boundary) continue
    const unitIndices = []
    for (let j = start; j <= i; j++) unitIndices.push(j)
    const keptText = unitIndices
      .filter((j) => keep[j])
      .map((j) => units[j])
      .join(' ')
      .trim()
    segments.push({
      text:
        keptText ||
        unitIndices
          .map((j) => units[j])
          .join(' ')
          .trim(),
      kept: keptText.length > 0,
      unitIndices,
    })
    start = i + 1
  }
  return segments
}

// Emitted tokens = the text of every KEPT segment (at least one unit kept),
// trimmed and non-empty. This is the value the component sends to the backend
// as `tokens`.
export function keptTokens(units, cuts, keep) {
  return computeSegments(units, cuts, keep)
    .filter((seg) => seg.kept)
    .map((seg) => seg.text)
    .filter(Boolean)
}

// Build the initial splitter state for a raw string: units from the tokenizer,
// separator units dropped with a cut on each side, every other boundary uncut
// (words grouped). The admin then toggles cuts / restores segments as needed.
export function initSplitState(raw) {
  const units = tokenizeUnits(raw)
  const seps = units.map(isSeparatorUnit)
  return {
    units,
    cuts: units.slice(0, -1).map((_, i) => seps[i] || seps[i + 1]),
    keep: seps.map((s) => !s),
  }
}

// ── Display helper ───────────────────────────────────────────────────────────

// Drop a trailing Discogs "(N)" disambiguator for DISPLAY only: "The Blue Men (2)"
// → "The Blue Men", "Taxi (22)" → "Taxi". Anchored at the end, pure digits only —
// "Moon (DE)", "Front 242" and "Free Bitch (Sinjin Hawke Remix)" pass through
// unchanged. The number stays in the DB (it marks a DISTINCT homonym); this is
// purely cosmetic (mirrors workers.artist_names.strip_disambiguation_number).
const DISAMBIG_NUMBER_RE = /\s*\(\s*\d+\s*\)\s*$/
export function stripDisambiguationNumber(name) {
  if (!name) return name
  const stripped = name.replace(DISAMBIG_NUMBER_RE, '').trim()
  return stripped || name
}

// ── Deezer signal helper ─────────────────────────────────────────────────────

// Case- and accent-insensitive fold for the live Deezer signal: a hit "counts"
// only when its name equals the segment after folding (Deezer returns fuzzy
// hits for anything, so a non-empty hit list alone proves nothing). NFKD +
// combining-marks strip ("Zoë" → "zoe"); whitespace collapsed so join
// artifacts never break equality.
export function foldArtistName(name) {
  return (name || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}
