import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FilterChip from '../../../components/filters/FilterChip.vue'

describe('FilterChip', () => {
  it('renders the criterion label and its value', () => {
    const wrapper = mount(FilterChip, { props: { label: 'BPM', value: '120–133' } })
    expect(wrapper.find('.fchip-label').text()).toBe('BPM')
    expect(wrapper.find('.fchip-value').text()).toBe('120–133')
  })

  it('emits remove when the × button is clicked', async () => {
    const wrapper = mount(FilterChip, { props: { label: 'Style', value: 'Techno' } })
    await wrapper.find('.fchip-x').trigger('click')
    expect(wrapper.emitted('remove')).toHaveLength(1)
  })

  it('labels the × button for assistive tech', () => {
    const wrapper = mount(FilterChip, { props: { label: 'Style', value: 'Techno' } })
    expect(wrapper.find('.fchip-x').attributes('aria-label')).toBe('Retirer Style')
  })

  it('default variant: only the × is a button, not the whole chip', () => {
    const wrapper = mount(FilterChip, { props: { label: 'Key', value: '5A' } })
    expect(wrapper.element.tagName).toBe('SPAN')
    expect(wrapper.findAll('button')).toHaveLength(1)
  })

  it('empty-state variant: the whole chip is one remove button', async () => {
    const wrapper = mount(FilterChip, { props: { label: 'Key', value: '5A', empty: true } })
    expect(wrapper.element.tagName).toBe('BUTTON')
    expect(wrapper.classes()).toContain('fchip--empty')
    await wrapper.trigger('click')
    expect(wrapper.emitted('remove')).toHaveLength(1)
  })
})
