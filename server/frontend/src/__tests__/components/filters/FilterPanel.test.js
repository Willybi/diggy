import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FilterPanel from '../../../components/filters/FilterPanel.vue'

describe('FilterPanel', () => {
  it('renders the consumer field blocks in its grid slot', () => {
    const wrapper = mount(FilterPanel, {
      slots: { default: '<div class="flt-field probe">bloc</div>' },
    })
    expect(wrapper.find('.fpanel-grid .probe').exists()).toBe(true)
  })

  it('shows the live count in the footer (French plural)', () => {
    const many = mount(FilterPanel, { props: { resultCount: 42 } })
    expect(many.find('.fpanel-count').text()).toBe('42 résultats')

    const one = mount(FilterPanel, { props: { resultCount: 1 } })
    expect(one.find('.fpanel-count').text()).toBe('1 résultat')

    const zero = mount(FilterPanel, { props: { resultCount: 0 } })
    expect(zero.find('.fpanel-count').text()).toBe('0 résultat')
  })

  it('shows … while loading and nothing without a count', () => {
    const loading = mount(FilterPanel, { props: { resultCount: 42, loading: true } })
    expect(loading.find('.fpanel-count').text()).toBe('…')

    const none = mount(FilterPanel)
    expect(none.find('.fpanel-count').text()).toBe('')
  })

  it('emits reset and close from the footer buttons', async () => {
    const wrapper = mount(FilterPanel, { props: { resultCount: 3 } })
    const buttons = wrapper.findAll('.fpanel-foot button')
    expect(buttons.map((b) => b.text())).toEqual(['Réinitialiser', 'Fermer'])

    await buttons[0].trigger('click')
    expect(wrapper.emitted('reset')).toHaveLength(1)
    await buttons[1].trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
