import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CamelotSelect from '../../../components/filters/CamelotSelect.vue'
import { CAMELOT_KEYS, compareCamelot } from '../../../components/filters/camelot.js'

describe('CamelotSelect', () => {
  it('renders the 24 static Camelot cells, minors (A) before majors (B)', () => {
    const wrapper = mount(CamelotSelect)
    const cells = wrapper.findAll('.cam-cell')
    expect(cells).toHaveLength(24)
    expect(cells[0].text()).toBe('1A')
    expect(cells[11].text()).toBe('12A')
    expect(cells[12].text()).toBe('1B')
    expect(cells[23].text()).toBe('12B')
  })

  it('reflects the selection through aria-pressed', () => {
    const wrapper = mount(CamelotSelect, { props: { modelValue: ['5A', '6B'] } })
    const pressed = wrapper
      .findAll('.cam-cell')
      .filter((c) => c.attributes('aria-pressed') === 'true')
      .map((c) => c.text())
    expect(pressed).toEqual(['5A', '6B'])
    const rest = wrapper.findAll('.cam-cell').filter((c) => c.attributes('aria-pressed') === 'false')
    expect(rest).toHaveLength(22)
  })

  it('adds a key on click', async () => {
    const wrapper = mount(CamelotSelect, { props: { modelValue: ['5A'] } })
    const cell6A = wrapper.findAll('.cam-cell').find((c) => c.text() === '6A')
    await cell6A.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['5A', '6A']]])
  })

  it('removes an already-selected key on click', async () => {
    const wrapper = mount(CamelotSelect, { props: { modelValue: ['5A', '6A'] } })
    const cell5A = wrapper.findAll('.cam-cell').find((c) => c.text() === '5A')
    await cell5A.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['6A']]])
  })

  it('renders the harmonic legend', () => {
    const wrapper = mount(CamelotSelect)
    expect(wrapper.find('.cam-legend').text()).toBe('A mineures · B majeures')
  })

  it('switches to the 6-column drawer variant via the variant prop', () => {
    const wrapper = mount(CamelotSelect, { props: { variant: 'drawer' } })
    expect(wrapper.classes()).toContain('cam--drawer')
    expect(wrapper.findAll('.cam-cell')).toHaveLength(24)
  })

  it('compareCamelot sorts letter first (A before B) then wheel number', () => {
    expect(['6B', '7A', '5A', '6A'].sort(compareCamelot)).toEqual(['5A', '6A', '7A', '6B'])
    expect(['12A', '2A', '1B', '1A'].sort(compareCamelot)).toEqual(['1A', '2A', '12A', '1B'])
  })

  it('CAMELOT_KEYS holds exactly the 24 base values', () => {
    expect(CAMELOT_KEYS).toHaveLength(24)
    expect(new Set(CAMELOT_KEYS).size).toBe(24)
    expect(CAMELOT_KEYS).toContain('1A')
    expect(CAMELOT_KEYS).toContain('12B')
  })
})
