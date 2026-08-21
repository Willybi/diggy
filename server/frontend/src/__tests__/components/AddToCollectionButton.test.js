import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))

vi.mock('../../utils/api.js', () => ({
  default: { get: apiGet, post: apiPost },
}))

async function mountButton(props, collections = []) {
  apiGet.mockResolvedValue({ data: collections })
  const { default: AddToCollectionButton } =
    await import('../../components/AddToCollectionButton.vue')
  return mount(AddToCollectionButton, { props })
}

describe('AddToCollectionButton', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    apiPost.mockResolvedValue({ data: {} })
  })

  it('renders the button with the default label and no dropdown until opened', async () => {
    const wrapper = await mountButton({ itemType: 'track', itemId: 1 })
    expect(wrapper.find('.btn-coll').text()).toContain('Collection')
    expect(wrapper.find('.coll-dropdown').exists()).toBe(false)
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('accepts a custom label', async () => {
    const wrapper = await mountButton({ itemType: 'set', itemId: 3, label: 'Ajouter' })
    expect(wrapper.find('.btn-coll').text()).toContain('Ajouter')
  })

  it('fetches the collections on the first open only', async () => {
    const wrapper = await mountButton({ itemType: 'track', itemId: 1 }, [
      { id: 10, name: 'Peak Time' },
      { id: 11, name: 'Warmup' },
    ])
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()

    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/api/collections/')
    expect(wrapper.findAll('.coll-dd-item')).toHaveLength(2)

    // Close then re-open — the list is already loaded, no second fetch.
    await wrapper.find('.btn-coll').trigger('click')
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('posts the polymorphic payload for a track (item_id, null item_name)', async () => {
    const wrapper = await mountButton({ itemType: 'track', itemId: 42 }, [{ id: 10, name: 'Peak' }])
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()

    await wrapper.find('.coll-dd-item').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/api/collections/10/items', {
      item_type: 'track',
      item_id: 42,
      item_name: null,
    })
    // The added collection is marked with a ✓ and disabled.
    expect(wrapper.find('.coll-dd-check').exists()).toBe(true)
    expect(wrapper.find('.coll-dd-item').attributes('disabled')).toBeDefined()
  })

  it('posts the polymorphic payload for a genre (item_name, null item_id)', async () => {
    const wrapper = await mountButton({ itemType: 'genre', itemName: 'Techno' }, [
      { id: 10, name: 'Peak' },
    ])
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()

    await wrapper.find('.coll-dd-item').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/api/collections/10/items', {
      item_type: 'genre',
      item_id: null,
      item_name: 'Techno',
    })
  })

  it('treats a 409 (already in collection) as an added state', async () => {
    apiPost.mockRejectedValue({ response: { status: 409 } })
    const wrapper = await mountButton({ itemType: 'artist', itemId: 5 }, [{ id: 10, name: 'Peak' }])
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()

    await wrapper.find('.coll-dd-item').trigger('click')
    await flushPromises()

    expect(wrapper.find('.coll-dd-check').exists()).toBe(true)
  })

  it('creates a new collection then adds the item to it', async () => {
    apiPost.mockImplementation((url) => {
      if (url === '/api/collections/') {
        return Promise.resolve({ data: { id: 77, name: 'Fresh', type: 'playlist', item_count: 0 } })
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = await mountButton({ itemType: 'playlist', itemId: 9 })
    await wrapper.find('.btn-coll').trigger('click')
    await flushPromises()

    // Swap the footer button for the inline input, type a name, submit.
    await wrapper.find('.coll-dd-add').trigger('click')
    await flushPromises()
    const input = wrapper.find('.coll-dd-input')
    expect(input.exists()).toBe(true)
    await input.setValue('Fresh')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/api/collections/', { name: 'Fresh' })
    expect(apiPost).toHaveBeenCalledWith('/api/collections/77/items', {
      item_type: 'playlist',
      item_id: 9,
      item_name: null,
    })
    // Input closed, new collection listed with a ✓.
    expect(wrapper.find('.coll-dd-input').exists()).toBe(false)
    const added = wrapper.findAll('.coll-dd-item').find((b) => b.text().includes('Fresh'))
    expect(added).toBeTruthy()
    expect(added.find('.coll-dd-check').exists()).toBe(true)
  })
})
