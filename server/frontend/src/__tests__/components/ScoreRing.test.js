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
})
