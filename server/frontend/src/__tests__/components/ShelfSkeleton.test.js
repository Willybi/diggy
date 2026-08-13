import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ShelfSkeleton from '../../components/hub/ShelfSkeleton.vue'

// Lightweight loading fallback for the lazy Hub sections. Deliberately imports no
// heavy shelf component, so it can stay in the main bundle.
describe('ShelfSkeleton', () => {
  it('renders an inert, aria-hidden ghost grid of the default 9 cards', () => {
    const wrapper = mount(ShelfSkeleton)
    expect(wrapper.attributes('aria-hidden')).toBe('true')
    expect(wrapper.attributes('aria-busy')).toBe('true')
    expect(wrapper.findAll('.sk-card')).toHaveLength(9)
  })

  it('honours a custom card count', () => {
    const wrapper = mount(ShelfSkeleton, { props: { count: 4 } })
    expect(wrapper.findAll('.sk-card')).toHaveLength(4)
  })
})
