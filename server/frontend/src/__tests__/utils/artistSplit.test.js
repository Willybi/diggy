import { describe, it, expect } from 'vitest'
import {
  SEPARATORS,
  detectSeparator,
  splitUnits,
  computeSegments,
  keptTokens,
  initSplitState,
} from '../../utils/artistSplit.js'

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

  it('exposes the new parity separators', () => {
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

describe('computeSegments', () => {
  it('makes each unit its own segment when every boundary is cut', () => {
    const segs = computeSegments(['A', 'B', 'C'], [true, true], ' & ')
    expect(segs.map((s) => s.text)).toEqual(['A', 'B', 'C'])
  })

  it('merges adjacent units across a non-cut boundary', () => {
    const segs = computeSegments(['A', 'B', 'C'], [false, true], ' & ')
    expect(segs.map((s) => s.text)).toEqual(['A & B', 'C'])
    expect(segs[0].unitIndices).toEqual([0, 1])
  })

  it('returns a single segment for a single unit', () => {
    const segs = computeSegments(['Solo'], [], ' ')
    expect(segs.map((s) => s.text)).toEqual(['Solo'])
  })
})

describe('keptTokens', () => {
  const units = ['Adam Beyer', 'Ida Engberg', '(Original Mix)']
  const cuts = [true, true]

  it('splits into N tokens when all kept', () => {
    const keep = [true, true, true]
    expect(keptTokens(units, cuts, keep, ' & ')).toEqual([
      'Adam Beyer',
      'Ida Engberg',
      '(Original Mix)',
    ])
  })

  it('excludes a deleted segment from the tokens', () => {
    const keep = [true, true, false]
    expect(keptTokens(units, cuts, keep, ' & ')).toEqual(['Adam Beyer', 'Ida Engberg'])
  })

  it('excludes several deleted segments', () => {
    const keep = [true, false, false]
    expect(keptTokens(units, cuts, keep, ' & ')).toEqual(['Adam Beyer'])
  })

  it('returns an empty list when nothing is kept (guard drives the disabled confirm)', () => {
    const keep = [false, false, false]
    expect(keptTokens(units, cuts, keep, ' & ')).toEqual([])
  })

  it('keeps a merged segment as one token', () => {
    const keep = [true, true]
    expect(keptTokens(['A', 'B'], [false], keep, ' & ')).toEqual(['A & B'])
  })
})

describe('initSplitState', () => {
  it('splits on a detected separator with every boundary cut (N-ary default)', () => {
    const s = initSplitState('A & B & C', null)
    expect(s.units).toEqual(['A', 'B', 'C'])
    expect(s.cuts).toEqual([true, true])
    expect(s.keep).toEqual([true, true, true])
    expect(s.sep).toBe(' & ')
    expect(keptTokens(s.units, s.cuts, s.keep, s.sep)).toEqual(['A', 'B', 'C'])
  })

  it('keeps a separator-less name as one uncut segment', () => {
    const s = initSplitState('Nina Kraviz', null)
    expect(s.units).toEqual(['Nina', 'Kraviz'])
    expect(s.cuts).toEqual([false])
    expect(keptTokens(s.units, s.cuts, s.keep, s.sep)).toEqual(['Nina Kraviz'])
  })

  it('uses initialTokens as pre-cut units (Flags tab)', () => {
    const s = initSplitState('Adam Beyer & Ida Engberg', ['Adam Beyer', 'Ida Engberg'])
    expect(s.units).toEqual(['Adam Beyer', 'Ida Engberg'])
    expect(s.cuts).toEqual([true])
    expect(s.sep).toBe(' & ')
    expect(keptTokens(s.units, s.cuts, s.keep, s.sep)).toEqual(['Adam Beyer', 'Ida Engberg'])
  })
})
