import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FilterDrawer from '../../../components/filters/FilterDrawer.vue'

describe('FilterDrawer', () => {
  it('renders nothing while closed', () => {
    const wrapper = mount(FilterDrawer, { props: { open: false } })
    expect(wrapper.find('.fdrawer').exists()).toBe(false)
  })

  it('renders the sheet, header and slot content when open', () => {
    const wrapper = mount(FilterDrawer, {
      props: { open: true },
      slots: { default: '<div class="probe">contrôles</div>' },
    })
    expect(wrapper.find('.fdrawer-title').text()).toBe('Filtres')
    expect(wrapper.find('.fdrawer-body .probe').exists()).toBe(true)
    expect(wrapper.find('.fdrawer-sheet').attributes('role')).toBe('dialog')
  })

  it('CTA shows the live count and closes the drawer', async () => {
    const wrapper = mount(FilterDrawer, { props: { open: true, resultCount: 42 } })
    const cta = wrapper.find('.fdrawer-cta')
    expect(cta.text()).toBe('Afficher 42 résultats')

    await cta.trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('CTA uses the singular for one result and a neutral label while loading', () => {
    const one = mount(FilterDrawer, { props: { open: true, resultCount: 1 } })
    expect(one.find('.fdrawer-cta').text()).toBe('Afficher 1 résultat')

    const loading = mount(FilterDrawer, { props: { open: true, resultCount: 42, loading: true } })
    expect(loading.find('.fdrawer-cta').text()).toBe('Afficher les résultats')
  })

  it('closes on overlay tap', async () => {
    const wrapper = mount(FilterDrawer, { props: { open: true } })
    await wrapper.find('.fdrawer-overlay').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('closes on Escape (document-level) only while open', async () => {
    const closed = mount(FilterDrawer, { props: { open: false } })
    document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    expect(closed.emitted('update:open')).toBeUndefined()

    const wrapper = mount(FilterDrawer, { props: { open: true } })
    document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    wrapper.unmount()
  })

  it('emits reset from the header button without closing', async () => {
    const wrapper = mount(FilterDrawer, { props: { open: true } })
    await wrapper.find('.fdrawer-reset').trigger('click')
    expect(wrapper.emitted('reset')).toHaveLength(1)
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('stops listening for Escape after unmount', () => {
    const wrapper = mount(FilterDrawer, { props: { open: true } })
    wrapper.unmount()
    // Must not throw nor emit — listener removed with the component.
    document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})
