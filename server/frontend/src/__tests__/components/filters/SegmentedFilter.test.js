import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SegmentedFilter from '../../../components/filters/SegmentedFilter.vue'

const triState = [
  { value: null, label: 'Tous' },
  { value: 'in', label: 'Dans ma bib' },
  { value: 'out', label: 'Pas dans RB' },
]

const presets = [
  { value: 'lt3', label: '< 3 min' },
  { value: '3-5', label: '3–5 min' },
  { value: '5-8', label: '5–8 min' },
  { value: 'gt8', label: '> 8 min' },
]

describe('SegmentedFilter', () => {
  it('tri-state: « Tous » is the active pill when the value is null', () => {
    const wrapper = mount(SegmentedFilter, { props: { modelValue: null, options: triState } })
    const active = wrapper.findAll('.seg-pill').filter((p) => p.attributes('aria-pressed') === 'true')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toBe('Tous')
  })

  it('tri-state: exactly one pill active for a set value', () => {
    const wrapper = mount(SegmentedFilter, { props: { modelValue: 'in', options: triState } })
    const active = wrapper.findAll('.seg-pill').filter((p) => p.attributes('aria-pressed') === 'true')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toBe('Dans ma bib')
  })

  it('tri-state: picking an option emits its value, « Tous » emits null', async () => {
    const wrapper = mount(SegmentedFilter, { props: { modelValue: null, options: triState } })
    const pills = wrapper.findAll('.seg-pill')
    await pills[1].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['in']])

    const back = mount(SegmentedFilter, { props: { modelValue: 'in', options: triState } })
    await back.findAll('.seg-pill')[0].trigger('click')
    expect(back.emitted('update:modelValue')).toEqual([[null]])
  })

  it('tri-state: re-clicking the active option does NOT deselect (« Tous » covers that)', async () => {
    const wrapper = mount(SegmentedFilter, { props: { modelValue: 'in', options: triState } })
    await wrapper.findAll('.seg-pill')[1].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('presets without « Tous »: re-clicking the active option deselects (emits null)', async () => {
    const wrapper = mount(SegmentedFilter, { props: { modelValue: '3-5', options: presets } })
    await wrapper.findAll('.seg-pill')[1].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[null]])
  })

  it('presets: nothing active when the value is null', () => {
    const wrapper = mount(SegmentedFilter, { props: { modelValue: null, options: presets } })
    const active = wrapper.findAll('.seg-pill').filter((p) => p.attributes('aria-pressed') === 'true')
    expect(active).toHaveLength(0)
  })

  it('applies mono and drawer variants and disables all pills when disabled', () => {
    const wrapper = mount(SegmentedFilter, {
      props: { modelValue: null, options: presets, mono: true, variant: 'drawer', disabled: true },
    })
    expect(wrapper.classes()).toContain('seg--drawer')
    for (const pill of wrapper.findAll('.seg-pill')) {
      expect(pill.classes()).toContain('mono')
      expect(pill.attributes('disabled')).toBeDefined()
    }
  })
})
