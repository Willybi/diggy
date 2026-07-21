import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RangeSlider from '../../../components/filters/RangeSlider.vue'

function mountSlider(props = {}) {
  return mount(RangeSlider, {
    props: { min: 60, max: 200, label: 'BPM', ...props },
  })
}

describe('RangeSlider', () => {
  it('renders the full range when modelValue is null (inactive criterion)', () => {
    const wrapper = mountSlider()
    const values = wrapper.findAll('.rs-val').map((v) => v.text())
    expect(values).toEqual(['60', '200'])
  })

  it('renders the current bounds on both sides', () => {
    const wrapper = mountSlider({ modelValue: [120, 133] })
    const values = wrapper.findAll('.rs-val').map((v) => v.text())
    expect(values).toEqual(['120', '133'])
  })

  it('emits [lo, hi] when a thumb moves', async () => {
    const wrapper = mountSlider({ modelValue: [120, 133] })
    await wrapper.findAll('input')[0].setValue('100')
    expect(wrapper.emitted('update:modelValue')).toEqual([[[100, 133]]])
  })

  it('clamps min onto max when the low thumb crosses (min never exceeds max)', async () => {
    const wrapper = mountSlider({ modelValue: [120, 133] })
    await wrapper.findAll('input')[0].setValue('180')
    expect(wrapper.emitted('update:modelValue')).toEqual([[[133, 133]]])
  })

  it('clamps max onto min when the high thumb crosses', async () => {
    const wrapper = mountSlider({ modelValue: [120, 133] })
    await wrapper.findAll('input')[1].setValue('80')
    expect(wrapper.emitted('update:modelValue')).toEqual([[[120, 120]]])
  })

  it('positions the accent fill segment between the thumbs (in %)', () => {
    const wrapper = mountSlider({ min: 0, max: 100, modelValue: [25, 75] })
    const style = wrapper.find('.rs-fill').attributes('style')
    expect(style).toContain('left: 25%')
    expect(style).toContain('right: 25%')
  })

  it('exposes accessible labels on both native inputs', () => {
    const wrapper = mountSlider()
    const inputs = wrapper.findAll('input')
    expect(inputs[0].attributes('aria-label')).toBe('BPM minimum')
    expect(inputs[1].attributes('aria-label')).toBe('BPM maximum')
  })

  it('disables both inputs when disabled', () => {
    const wrapper = mountSlider({ disabled: true })
    expect(wrapper.classes()).toContain('is-disabled')
    for (const input of wrapper.findAll('input')) {
      expect(input.attributes('disabled')).toBeDefined()
    }
  })
})
