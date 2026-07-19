import { describe, it, expect } from 'vitest'
import { fmtCue } from '../../utils/format'

describe('fmtCue', () => {
  it('returns an em dash only for a null timecode', () => {
    expect(fmtCue(null)).toBe('—')
    expect(fmtCue(undefined)).toBe('—')
  })

  it('formats 0 as "0:00" (start of the set is a valid cue)', () => {
    expect(fmtCue(0)).toBe('0:00')
  })

  it('uses "m:ss" under an hour', () => {
    expect(fmtCue(1294000)).toBe('21:34') // 21m34s — the Track Detail cue format
    expect(fmtCue(3599000)).toBe('59:59') // just under an hour
  })

  it('uses "h:mm:ss" from an hour up', () => {
    expect(fmtCue(3600000)).toBe('1:00:00')
    expect(fmtCue(3661000)).toBe('1:01:01')
  })
})
