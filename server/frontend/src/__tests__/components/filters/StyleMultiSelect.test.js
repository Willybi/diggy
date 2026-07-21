import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StyleMultiSelect from '../../../components/filters/StyleMultiSelect.vue'

const options = [
  { name: 'Ambient', count: 240, pillar: 'autres', depth: 0 },
  { name: 'Techno', count: 3860, pillar: 'techno', depth: 0 },
  { name: 'Tech House', count: 1284, pillar: 'house', depth: 1 },
  { name: 'House', count: 4120, pillar: 'house', depth: 0 },
]

describe('StyleMultiSelect', () => {
  it('groups by pillar in the fixed order, empty pillars omitted', () => {
    const wrapper = mount(StyleMultiSelect, { props: { options } })
    const labels = wrapper.findAll('.sms-pillar').map((p) => p.text())
    // House before Techno before Autres; Trance/DnB/Hardcore/Hard Dance absent.
    expect(labels).toEqual(['House', 'Techno', 'Autres'])
  })

  it('keeps chips under their pillar row with the pillar hue attributes', () => {
    const wrapper = mount(StyleMultiSelect, { props: { options } })
    const rows = wrapper.findAll('.sms-row')
    const houseChips = rows[0].findAll('.sms-chip')
    expect(houseChips.map((c) => c.find('.sms-name').text())).toEqual(['Tech House', 'House'])
    expect(houseChips[0].attributes('data-fam')).toBe('house')
    // Depth drives the chroma attenuation custom prop.
    expect(houseChips[0].attributes('style')).toContain('--d: 1')
  })

  it('routes an unknown pillar to Autres', () => {
    const wrapper = mount(StyleMultiSelect, {
      props: { options: [{ name: 'Mystery', count: 1, pillar: 'zzz', depth: 0 }] },
    })
    expect(wrapper.findAll('.sms-pillar').map((p) => p.text())).toEqual(['Autres'])
    expect(wrapper.find('.sms-chip').attributes('data-fam')).toBe('autres')
  })

  it('shows the count on each chip', () => {
    const wrapper = mount(StyleMultiSelect, { props: { options } })
    const techno = wrapper.findAll('.sms-chip').find((c) => c.find('.sms-name').text() === 'Techno')
    expect(techno.find('.sms-count').text()).toBe('3860')
  })

  it('marks selected chips with aria-pressed', () => {
    const wrapper = mount(StyleMultiSelect, { props: { options, modelValue: ['Techno'] } })
    const techno = wrapper.findAll('.sms-chip').find((c) => c.find('.sms-name').text() === 'Techno')
    expect(techno.attributes('aria-pressed')).toBe('true')
    expect(techno.classes()).toContain('on')
    const house = wrapper.findAll('.sms-chip').find((c) => c.find('.sms-name').text() === 'House')
    expect(house.attributes('aria-pressed')).toBe('false')
  })

  it('adds a style on click and removes it on re-click', async () => {
    const wrapper = mount(StyleMultiSelect, { props: { options, modelValue: ['Techno'] } })
    const house = wrapper.findAll('.sms-chip').find((c) => c.find('.sms-name').text() === 'House')
    await house.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['Techno', 'House']]])

    const techno = wrapper.findAll('.sms-chip').find((c) => c.find('.sms-name').text() === 'Techno')
    await techno.trigger('click')
    expect(wrapper.emitted('update:modelValue')[1]).toEqual([[]])
  })

  it('renders nothing with an empty options list', () => {
    const wrapper = mount(StyleMultiSelect, { props: { options: [] } })
    expect(wrapper.findAll('.sms-row')).toHaveLength(0)
  })
})
