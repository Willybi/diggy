/**
 * ms -> "m:ss" or "H:MM:SS" if >= 1h
 */
export function fmtMs(ms) {
  if (!ms || ms <= 0) return '—'
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`
}

/**
 * BPM float -> rounded int or "--"
 */
export function fmtBpm(v) {
  return v ? Math.round(v) : '—'
}

/**
 * Date string -> DD/MM/YYYY (fr-FR) or "--"
 */
export function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

/**
 * seconds -> "m:ss" (player timeline). Handles negative for remaining time.
 */
export function fmtSec(sec) {
  if (sec == null || isNaN(sec)) return '0:00'
  const neg = sec < 0
  const abs = Math.floor(Math.abs(sec))
  const m = Math.floor(abs / 60)
  const s = abs % 60
  return `${neg ? '-' : ''}${m}:${String(s).padStart(2, '0')}`
}

/**
 * ms -> set timecode: "m:ss" under an hour, "h:mm:ss" from an hour up.
 * Only null is unknown ("—"); 0 is a valid cue (start of the set) -> "0:00".
 */
export function fmtCue(ms) {
  if (ms == null) return '—'
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`
}

/**
 * Number -> locale-formatted string (fr-FR, e.g. 1 248)
 */
export function fmtNum(n) {
  return n != null ? n.toLocaleString('fr-FR') : '—'
}

/**
 * Simple pluralize: pl(1, 'track', 'tracks') -> 'track'
 */
export function pl(n, one, many) {
  return n === 1 ? one : many
}

/**
 * "YYYY-MM-DD" -> "aujourd'hui / hier / il y a N j / N sem / N mois"
 * Release recency at day granularity (horizon <= 30 j). '' if unparseable.
 */
export function relativeAge(dateStr) {
  if (!dateStr) return ''
  const d = new Date(`${dateStr}T00:00:00`)
  if (Number.isNaN(d.getTime())) return ''
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return "aujourd'hui"
  if (days === 1) return 'hier'
  if (days < 7) return `il y a ${days} j`
  const weeks = Math.floor(days / 7)
  if (days < 30) return weeks === 1 ? 'il y a 1 sem' : `il y a ${weeks} sem`
  const months = Math.max(1, Math.floor(days / 30))
  return months === 1 ? 'il y a 1 mois' : `il y a ${months} mois`
}
