import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SortSelect from '../../../components/filters/SortSelect.vue'

const options = [
  { value: 'recent', label: 'Récemment ajoutés' },
  { value: 'title', label: 'Titre A–Z' },
  { value: 'bpm', label: 'BPM' },
]

describe('SortSelect', () => {
  it('renders the page-provided options in a native select', () => {
    const wrapper = mount(SortSelect, { props: { modelValue: 'recent', options } })
    const opts = wrapper.findAll('option')
    expect(opts.map((o) => o.text())).toEqual(['Récemment ajoutés', 'Titre A–Z', 'BPM'])
    expect(wrapper.find('select').element.value).toBe('recent')
  })

  it('emits update:modelValue on change', async () => {
    const wrapper = mount(SortSelect, { props: { modelValue: 'recent', options } })
    await wrapper.find('select').setValue('bpm')
    expect(wrapper.emitted('update:modelValue')).toEqual([['bpm']])
  })

  it('is labelled « Trier » for assistive tech', () => {
    const wrapper = mount(SortSelect, { props: { modelValue: 'recent', options } })
    expect(wrapper.find('select').attributes('aria-label')).toBe('Trier')
  })

  it('never renders a filter chip (sorting is not a filter)', () => {
    const wrapper = mount(SortSelect, { props: { modelValue: 'recent', options } })
    expect(wrapper.find('.fchip').exists()).toBe(false)
    expect(wrapper.find('.fbar-badge').exists()).toBe(false)
  })

  it('is dimmed and inert when disabled', () => {
    const wrapper = mount(SortSelect, { props: { modelValue: 'recent', options, disabled: true } })
    expect(wrapper.classes()).toContain('is-disabled')
    expect(wrapper.find('select').attributes('disabled')).toBeDefined()
  })
})
