import { describe, it, expect } from 'vitest'
import {
  SEPARATORS,
  detectSeparator,
  splitUnits,
  DROP_SET,
  isSeparatorUnit,
  tokenizeUnits,
  computeSegments,
  keptTokens,
  initSplitState,
  foldArtistName,
} from '../../utils/artistSplit.js'

// ── Legacy separator detection (still feeds the AdminArtists flag flow) ──────

describe('detectSeparator', () => {
  it('detects punctuation and word separators', () => {
    expect(detectSeparator('Adam Beyer & Ida Engberg')).toBe(' & ')
    expect(detectSeparator('A|B')).toBe('|')
    expect(detectSeparator('Foo, Bar')).toBe(', ')
    expect(detectSeparator('Foo feat. Bar')).toBe(' feat. ')
    expect(detectSeparator('Larry Heard presents Mr White')).toBe(' presents ')
    expect(detectSeparator('Foo pres. Bar')).toBe(' pres. ')
  })

  it('matches word separators case-insensitively (parity with backend IGNORECASE)', () => {
    expect(detectSeparator('Adam Beyer AND Ida')).toBe(' and ')
    expect(detectSeparator('Foo X Bar')).toBe(' x ')
    expect(detectSeparator('Foo Y Bar')).toBe(' y ')
    expect(detectSeparator('Foo E Bar')).toBe(' e ')
  })

  it('returns null when no separator is present', () => {
    expect(detectSeparator('Nina Kraviz')).toBeNull()
    expect(detectSeparator('')).toBeNull()
    expect(detectSeparator(null)).toBeNull()
  })

  it('exposes the parity separators', () => {
    for (const sep of [
      ' + ',
      ' and ',
      ' x ',
      ' y ',
      ' e ',
      ' presents ',
      ' présente ',
      ' pres. ',
      ' pres ',
    ]) {
      expect(SEPARATORS).toContain(sep)
    }
  })
})

describe('splitUnits', () => {
  it('splits on the separator, trimming and dropping empties', () => {
    expect(splitUnits('Adam Beyer & Ida Engberg', ' & ')).toEqual(['Adam Beyer', 'Ida Engberg'])
    expect(splitUnits('A & B & C', ' & ')).toEqual(['A', 'B', 'C'])
  })

  it('splits case-insensitively so a detected sep always cuts', () => {
    expect(splitUnits('Adam Beyer AND Ida', ' and ')).toEqual(['Adam Beyer', 'Ida'])
  })

  it('falls back to whitespace when no separator is given', () => {
    expect(splitUnits('Nina   Kraviz', null)).toEqual(['Nina', 'Kraviz'])
  })
})

// ── Unit model: tokenization ─────────────────────────────────────────────────

describe('tokenizeUnits', () => {
  it('spaces out hard punctuation so it becomes its own unit, even glued', () => {
    expect(tokenizeUnits('A|B')).toEqual(['A', '|', 'B'])
    expect(tokenizeUnits('A, B, C')).toEqual(['A', ',', 'B', ',', 'C'])
    expect(tokenizeUnits('Adam Beyer & Ida Engberg')).toEqual([
      'Adam',
      'Beyer',
      '&',
      'Ida',
      'Engberg',
    ])
  })

  it('keeps a glued "/" inside its unit but isolates a spaced one', () => {
    expect(tokenizeUnits('Felix KI/KI')).toEqual(['Felix', 'KI/KI'])
    expect(tokenizeUnits('KI/KI Marlon Hoffstadt')).toEqual(['KI/KI', 'Marlon', 'Hoffstadt'])
    expect(tokenizeUnits('A / B')).toEqual(['A', '/', 'B'])
  })

  it('keeps "." and "-" glued (feat., Mr., Jay-Z)', () => {
    expect(tokenizeUnits('Larry Heard presents Mr. White')).toEqual([
      'Larry',
      'Heard',
      'presents',
      'Mr.',
      'White',
    ])
    expect(tokenizeUnits('Jay-Z feat. Beyoncé')).toEqual(['Jay-Z', 'feat.', 'Beyoncé'])
  })

  it('returns [] for empty input', () => {
    expect(tokenizeUnits('')).toEqual([])
    expect(tokenizeUnits(null)).toEqual([])
  })
})

describe('isSeparatorUnit', () => {
  it('flags the punctuation bullets and multi-letter words, case-insensitively', () => {
    for (const u of [',', '&', '+', '|', ';', '/', 'and', 'AND', 'Feat.', 'presents', 'présente']) {
      expect(isSeparatorUnit(u)).toBe(true)
    }
  })

  it('does NOT flag single letters (too ambiguous: Malcolm X, Ben E King)', () => {
    for (const u of ['x', 'X', 'y', 'e']) {
      expect(isSeparatorUnit(u)).toBe(false)
    }
    expect(DROP_SET.has('x')).toBe(false)
  })

  it('does not flag a normal word or a glued slash', () => {
    expect(isSeparatorUnit('Adam')).toBe(false)
    expect(isSeparatorUnit('KI/KI')).toBe(false)
  })
})

// ── Unit model: segments + tokens ────────────────────────────────────────────

describe('computeSegments', () => {
  it('makes each unit its own segment when every boundary is cut', () => {
    const segs = computeSegments(['A', 'B', 'C'], [true, true], [true, true, true])
    expect(segs.map((s) => s.text)).toEqual(['A', 'B', 'C'])
    expect(segs.map((s) => s.kept)).toEqual([true, true, true])
  })

  it('merges adjacent units across a non-cut boundary', () => {
    const segs = computeSegments(['A', 'B', 'C'], [false, true], [true, true, true])
    expect(segs.map((s) => s.text)).toEqual(['A B', 'C'])
    expect(segs[0].unitIndices).toEqual([0, 1])
  })

  it('hides a dropped separator unit inside a merged segment', () => {
    const segs = computeSegments(['A', '&', 'B'], [false, false], [true, false, true])
    expect(segs).toHaveLength(1)
    expect(segs[0].text).toBe('A B')
    expect(segs[0].kept).toBe(true)
  })

  it('falls back to the raw units for a fully-dropped segment (readable chip)', () => {
    const segs = computeSegments(['A', '&', 'B'], [true, true], [true, false, true])
    expect(segs.map((s) => s.text)).toEqual(['A', '&', 'B'])
    expect(segs.map((s) => s.kept)).toEqual([true, false, true])
  })

  it('returns a single segment for a single unit', () => {
    const segs = computeSegments(['Solo'], [], [true])
    expect(segs.map((s) => s.text)).toEqual(['Solo'])
  })
})

describe('keptTokens', () => {
  it('emits one token per kept segment', () => {
    const units = ['Adam Beyer', 'Ida Engberg', '(Original Mix)']
    expect(keptTokens(units, [true, true], [true, true, true])).toEqual(units)
  })

  it('excludes deleted segments from the tokens', () => {
    const units = ['Adam Beyer', 'Ida Engberg', '(Original Mix)']
    expect(keptTokens(units, [true, true], [true, true, false])).toEqual([
      'Adam Beyer',
      'Ida Engberg',
    ])
    expect(keptTokens(units, [true, true], [true, false, false])).toEqual(['Adam Beyer'])
  })

  it('returns an empty list when nothing is kept (guard drives the disabled confirm)', () => {
    expect(keptTokens(['A', 'B'], [true], [false, false])).toEqual([])
  })

  it('keeps a merged segment as one space-joined token', () => {
    expect(keptTokens(['A', 'B'], [false], [true, true])).toEqual(['A B'])
  })

  it('emits a restored separator segment as a real token (admin decision)', () => {
    expect(keptTokens(['A', '&', 'B'], [true, true], [true, true, true])).toEqual(['A', '&', 'B'])
  })
})

// ── Default-state contract (initSplitState) ──────────────────────────────────

// Behaviour contract from the Lot 1 brief: default state WITHOUT manual edits,
// then after the documented edit.
describe('initSplitState', () => {
  const tokensOf = (s) => keptTokens(s.units, s.cuts, s.keep)

  it('"Felix KI/KI" → one default segment, space cut isolates KI/KI whole', () => {
    const s = initSplitState('Felix KI/KI')
    expect(s.units).toEqual(['Felix', 'KI/KI'])
    expect(s.cuts).toEqual([false])
    expect(tokensOf(s)).toEqual(['Felix KI/KI'])
    s.cuts[0] = true
    expect(tokensOf(s)).toEqual(['Felix', 'KI/KI'])
  })

  it('"KI/KI Marlon Hoffstadt" → cut after KI/KI gives the two real artists', () => {
    const s = initSplitState('KI/KI Marlon Hoffstadt')
    expect(s.units).toEqual(['KI/KI', 'Marlon', 'Hoffstadt'])
    expect(tokensOf(s)).toEqual(['KI/KI Marlon Hoffstadt'])
    s.cuts[0] = true
    expect(tokensOf(s)).toEqual(['KI/KI', 'Marlon Hoffstadt'])
  })

  it('"Adam Beyer & Ida Engberg" → "&" dropped with a cut on each side', () => {
    const s = initSplitState('Adam Beyer & Ida Engberg')
    expect(s.units).toEqual(['Adam', 'Beyer', '&', 'Ida', 'Engberg'])
    expect(s.cuts).toEqual([false, true, true, false])
    expect(s.keep).toEqual([true, true, false, true, true])
    expect(tokensOf(s)).toEqual(['Adam Beyer', 'Ida Engberg'])
  })

  it('splits glued and spaced punctuation by default', () => {
    expect(tokensOf(initSplitState('A|B'))).toEqual(['A', 'B'])
    expect(tokensOf(initSplitState('A, B, C'))).toEqual(['A', 'B', 'C'])
    expect(tokensOf(initSplitState('A / B'))).toEqual(['A', 'B'])
  })

  it('drops word separators ("presents") while "." stays glued', () => {
    expect(tokensOf(initSplitState('Larry Heard presents Mr. White'))).toEqual([
      'Larry Heard',
      'Mr. White',
    ])
  })

  it('keeps a single letter as a normal unit ("Malcolm X" stays whole)', () => {
    const s = initSplitState('Malcolm X')
    expect(s.cuts).toEqual([false])
    expect(tokensOf(s)).toEqual(['Malcolm X'])
  })

  it('deleting segments excludes them; nothing kept → []', () => {
    const s = initSplitState('Adam Beyer & Ida Engberg')
    s.keep[3] = false
    s.keep[4] = false
    expect(tokensOf(s)).toEqual(['Adam Beyer'])
    s.keep[0] = false
    s.keep[1] = false
    expect(tokensOf(s)).toEqual([])
  })

  it('handles an empty raw string', () => {
    const s = initSplitState('')
    expect(s.units).toEqual([])
    expect(s.cuts).toEqual([])
    expect(tokensOf(s)).toEqual([])
  })
})

// ── Deezer signal fold ───────────────────────────────────────────────────────

describe('foldArtistName', () => {
  it('folds case and accents to compare Deezer hits to segments', () => {
    expect(foldArtistName('Nick León')).toBe('nick leon')
    expect(foldArtistName('ZOË')).toBe('zoe')
    expect(foldArtistName('Beyoncé')).toBe(foldArtistName('BEYONCE'))
  })

  it('collapses whitespace and trims', () => {
    expect(foldArtistName('  Adam   Beyer ')).toBe('adam beyer')
  })

  it('is safe on empty input', () => {
    expect(foldArtistName('')).toBe('')
    expect(foldArtistName(null)).toBe('')
  })
})
