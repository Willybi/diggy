import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ScoreRing from '../../components/ScoreRing.vue'

describe('ScoreRing', () => {
  it('displays the score rounded to an integer out of 10', () => {
    expect(
      mount(ScoreRing, { props: { score: 0.86 } })
        .find('.sr-note')
        .text(),
    ).toBe('9')
    expect(
      mount(ScoreRing, { props: { score: 0.44 } })
        .find('.sr-note')
        .text(),
    ).toBe('4')
  })

  it('handles the bounds 0 and 1', () => {
    expect(
      mount(ScoreRing, { props: { score: 0 } })
        .find('.sr-note')
        .text(),
    ).toBe('0')
    expect(
      mount(ScoreRing, { props: { score: 1 } })
        .find('.sr-note')
        .text(),
    ).toBe('10')
  })

  it('never renders a percent sign or "/10"', () => {
    const text = mount(ScoreRing, { props: { score: 0.7 } }).text()
    expect(text).toBe('7')
    expect(text).not.toContain('%')
    expect(text).not.toContain('/10')
  })

  it('exposes role=img and a default aria-label', () => {
    const wrapper = mount(ScoreRing, { props: { score: 0.86 } })
    const el = wrapper.find('.score-ring')
    expect(el.attributes('role')).toBe('img')
    expect(el.attributes('aria-label')).toBe('Score 9 /10')
  })

  it('uses the provided label instead of the default', () => {
    const wrapper = mount(ScoreRing, { props: { score: 0.86, label: 'Similarité 9 /10' } })
    expect(wrapper.find('.score-ring').attributes('aria-label')).toBe('Similarité 9 /10')
  })

  it('applies the size modifier class', () => {
    expect(
      mount(ScoreRing, { props: { score: 0.5 } })
        .find('.score-ring')
        .classes(),
    ).toContain('score-ring--sm')
    expect(
      mount(ScoreRing, { props: { score: 0.5, size: 'md' } })
        .find('.score-ring')
        .classes(),
    ).toContain('score-ring--md')
  })

  // --- mode="pct" ---

  const THIN_NBSP = String.fromCharCode(0x202f) // U+202F narrow no-break space

  it('keeps score mode as the default (bit-for-bit unchanged, no percent sign)', () => {
    const wrapper = mount(ScoreRing, { props: { score: 0.86 } })
    expect(wrapper.find('.sr-note').text()).toBe('9')
    expect(wrapper.find('.sr-note').classes()).not.toContain('sr-note--pct')
  })

  it('renders an integer percent with a fine no-break space in pct mode', () => {
    const wrapper = mount(ScoreRing, { props: { score: 0.69, mode: 'pct' } })
    expect(wrapper.find('.sr-note').text()).toBe(`69${THIN_NBSP}%`)
    expect(wrapper.find('.sr-note').classes()).toContain('sr-note--pct')
  })

  it('handles the 0% and 100% bounds in pct mode', () => {
    expect(
      mount(ScoreRing, { props: { score: 0, mode: 'pct' } })
        .find('.sr-note')
        .text(),
    ).toBe(`0${THIN_NBSP}%`)
    expect(
      mount(ScoreRing, { props: { score: 1, mode: 'pct' } })
        .find('.sr-note')
        .text(),
    ).toBe(`100${THIN_NBSP}%`)
  })

  it('rounds the proportion to an integer percent', () => {
    expect(
      mount(ScoreRing, { props: { score: 0.666, mode: 'pct' } })
        .find('.sr-note')
        .text(),
    ).toBe(`67${THIN_NBSP}%`)
  })

  it('defaults the aria-label to "N %" in pct mode', () => {
    const wrapper = mount(ScoreRing, { props: { score: 0.69, mode: 'pct' } })
    expect(wrapper.find('.score-ring').attributes('aria-label')).toBe(`69${THIN_NBSP}%`)
  })

  it('lets the provided label win over the pct default', () => {
    const wrapper = mount(ScoreRing, {
      props: { score: 0.69, mode: 'pct', label: '69 % de tracks identifiées' },
    })
    expect(wrapper.find('.score-ring').attributes('aria-label')).toBe('69 % de tracks identifiées')
  })
})
