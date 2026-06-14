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
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

/**
 * ms -> "H:MM:SS" timecode for sets
 */
export function fmtCue(ms) {
  if (ms == null) return '—'
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}
