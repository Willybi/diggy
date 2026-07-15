import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FamilyChips from '../../components/FamilyChips.vue'

function famKeys(wrapper) {
  // The "Tous" chip has fam=null → Vue omits data-fam, so map it back to 'all'.
  return wrapper.findAll('.fam-chip').map((c) => c.attributes('data-fam') || 'all')
}

describe('FamilyChips', () => {
  it('always shows "Tous" with the summed count', () => {
    const wrapper = mount(FamilyChips, {
      props: { modelValue: 'all', counts: { house: 5, techno: 3 } },
    })
    const first = wrapper.findAll('.fam-chip')[0]
    expect(first.text()).toContain('Tous')
    expect(first.text()).toContain('8') // 5 + 3
  })

  it('hides families whose count is zero or absent', () => {
    const wrapper = mount(FamilyChips, {
      props: { modelValue: 'all', counts: { house: 5, techno: 0, trance: 2 } },
    })
    const keys = famKeys(wrapper)
    expect(keys).toEqual(['all', 'house', 'trance'])
    const text = wrapper.text()
    expect(text).not.toContain('Techno') // count 0
    expect(text).not.toContain('Hardcore') // absent
  })

  it('keeps the active family visible even when its count is zero/absent', () => {
    const wrapper = mount(FamilyChips, {
      props: { modelValue: 'techno', counts: { house: 5 } },
    })
    const keys = famKeys(wrapper)
    expect(keys[0]).toBe('all') // "Tous" always first
    expect(keys).toContain('techno') // active, count 0 → still shown
    expect(keys).toContain('house')
  })

  it('emits update:modelValue when a chip is clicked', async () => {
    const wrapper = mount(FamilyChips, {
      props: { modelValue: 'all', counts: { house: 5 } },
    })
    const house = wrapper.findAll('.fam-chip').find((c) => c.text().includes('House'))
    await house.trigger('click')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['house'])
  })
})
