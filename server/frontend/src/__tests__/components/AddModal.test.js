import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AddModal from '../../components/AddModal.vue'

describe('AddModal', () => {
  it('renders the head (title + aria-label) and the slotted body when open', () => {
    const wrapper = mount(AddModal, {
      props: { open: true, title: 'Ajouter un set' },
      slots: { default: '<p class="body-marker">corps</p>' },
    })
    expect(wrapper.find('.add-overlay').exists()).toBe(true)
    expect(wrapper.find('.add-modal-title').text()).toBe('Ajouter un set')
    // The dialog aria-label mirrors the title.
    expect(wrapper.find('[role="dialog"]').attributes('aria-label')).toBe('Ajouter un set')
    // The body comes from the default slot.
    expect(wrapper.find('.body-marker').text()).toBe('corps')
  })

  it('renders nothing when closed', () => {
    const wrapper = mount(AddModal, {
      props: { open: false, title: 'X' },
      slots: { default: '<p class="body-marker">corps</p>' },
    })
    expect(wrapper.find('.add-overlay').exists()).toBe(false)
    expect(wrapper.find('.body-marker').exists()).toBe(false)
  })

  it('emits update:open=false when the close button is clicked', async () => {
    const wrapper = mount(AddModal, { props: { open: true, title: 'X' } })
    await wrapper.find('.add-modal-x').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('closes on a backdrop click but not on a click inside the card (@click.self)', async () => {
    const wrapper = mount(AddModal, { props: { open: true, title: 'X' } })
    // A click that bubbles up from the card is not a backdrop click → no close.
    await wrapper.find('.add-modal').trigger('click')
    expect(wrapper.emitted('update:open')).toBeFalsy()
    // A click on the overlay itself closes.
    await wrapper.find('.add-overlay').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('applies the bottom-sheet modifier only when opted in', () => {
    const plain = mount(AddModal, { props: { open: true, title: 'X' } })
    expect(plain.find('.add-overlay').classes()).not.toContain('add-overlay--sheet')
    const sheet = mount(AddModal, { props: { open: true, title: 'X', bottomSheet: true } })
    expect(sheet.find('.add-overlay').classes()).toContain('add-overlay--sheet')
  })

  it('closes on Escape while open', async () => {
    const wrapper = mount(AddModal, { props: { open: true, title: 'X' } })
    window.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    wrapper.unmount()
  })
})
