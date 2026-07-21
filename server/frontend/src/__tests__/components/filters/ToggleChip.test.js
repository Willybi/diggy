import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ToggleChip from '../../../components/filters/ToggleChip.vue'

describe('ToggleChip', () => {
  it('renders the label and aria-pressed=false when off (criterion absent)', () => {
    const wrapper = mount(ToggleChip, { props: { modelValue: false, label: 'Écoutable uniquement' } })
    expect(wrapper.text()).toContain('Écoutable uniquement')
    expect(wrapper.attributes('aria-pressed')).toBe('false')
    expect(wrapper.classes()).not.toContain('on')
  })

  it('reflects the on state through aria-pressed and the accent class', () => {
    const wrapper = mount(ToggleChip, { props: { modelValue: true, label: 'Écoutable uniquement' } })
    expect(wrapper.attributes('aria-pressed')).toBe('true')
    expect(wrapper.classes()).toContain('on')
  })

  it('toggles on click in both directions', async () => {
    const off = mount(ToggleChip, { props: { modelValue: false, label: 'Écoutable uniquement' } })
    await off.trigger('click')
    expect(off.emitted('update:modelValue')).toEqual([[true]])

    const on = mount(ToggleChip, { props: { modelValue: true, label: 'Écoutable uniquement' } })
    await on.trigger('click')
    expect(on.emitted('update:modelValue')).toEqual([[false]])
  })

  it('renders the optional icon slot', () => {
    const wrapper = mount(ToggleChip, {
      props: { modelValue: false, label: 'Écoutable uniquement' },
      slots: { icon: '<svg class="probe"></svg>' },
    })
    expect(wrapper.find('.tgl-ic .probe').exists()).toBe(true)
  })

  it('does not emit when disabled', async () => {
    const wrapper = mount(ToggleChip, {
      props: { modelValue: false, label: 'Écoutable uniquement', disabled: true },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
