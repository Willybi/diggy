import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchInput from '../../../components/filters/SearchInput.vue'

describe('SearchInput', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces the update:modelValue emission by 250ms', async () => {
    const wrapper = mount(SearchInput, { props: { modelValue: '' } })
    await wrapper.find('input').setValue('kas')

    vi.advanceTimersByTime(249)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    vi.advanceTimersByTime(1)
    expect(wrapper.emitted('update:modelValue')).toEqual([['kas']])
  })

  it('resets the debounce timer on every keystroke (single emission)', async () => {
    const wrapper = mount(SearchInput, { props: { modelValue: '' } })
    await wrapper.find('input').setValue('k')
    vi.advanceTimersByTime(200)
    await wrapper.find('input').setValue('ka')
    vi.advanceTimersByTime(200)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    vi.advanceTimersByTime(50)
    expect(wrapper.emitted('update:modelValue')).toEqual([['ka']])
  })

  it('follows an external modelValue change (URL restore)', async () => {
    const wrapper = mount(SearchInput, { props: { modelValue: '' } })
    await wrapper.setProps({ modelValue: 'drumcode' })
    expect(wrapper.find('input').element.value).toBe('drumcode')
  })

  it('shows the magnifier by default and hides it for the Label variant', () => {
    const withIcon = mount(SearchInput, { props: { modelValue: '' } })
    expect(withIcon.find('.si-loupe').exists()).toBe(true)

    const noIcon = mount(SearchInput, { props: { modelValue: '', icon: false } })
    expect(noIcon.find('.si-loupe').exists()).toBe(false)
  })

  it('renders the placeholder and disables the input when disabled', () => {
    const wrapper = mount(SearchInput, {
      props: { modelValue: '', placeholder: 'Defected, Drumcode…', disabled: true },
    })
    const input = wrapper.find('input')
    expect(input.attributes('placeholder')).toBe('Defected, Drumcode…')
    expect(input.attributes('disabled')).toBeDefined()
    expect(wrapper.classes()).toContain('is-disabled')
  })
})
