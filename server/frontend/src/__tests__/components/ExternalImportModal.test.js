import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))

vi.mock('../../utils/api.js', () => ({
  default: { get: apiGet, post: apiPost },
}))

// The component imports RouterLink directly from vue-router; stub it so no
// router instance is required (script-setup binds the import, not a global).
vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a class="rl" :href="to"><slot /></a>',
  },
}))

const deezerItem = {
  source: 'deezer',
  external_id: 'd1',
  title: 'One More Time',
  artist: 'Daft Punk',
  isrc: null,
  duration_ms: 320000,
  artwork_url: null,
  catalog_id: null,
}
const tidalItem = {
  source: 'tidal',
  external_id: 't1',
  title: 'Teardrop',
  artist: 'Massive Attack',
  isrc: null,
  duration_ms: 330000,
  artwork_url: null,
  catalog_id: null,
}

async function mountWith(items) {
  apiGet.mockResolvedValue({ data: { items } })
  const { default: ExternalImportModal } = await import(
    '../../components/ExternalImportModal.vue'
  )
  const wrapper = mount(ExternalImportModal)
  // Bypass the SearchBox debounce by emitting the model update directly.
  wrapper.findComponent({ name: 'SearchBox' }).vm.$emit('update:modelValue', 'query')
  await flushPromises()
  return wrapper
}

describe('ExternalImportModal', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
  })

  it('runs an external search on query change and renders results', async () => {
    const wrapper = await mountWith([deezerItem, tidalItem])

    expect(apiGet).toHaveBeenCalledWith('/api/search/external', {
      params: { q: 'query' },
    })
    expect(wrapper.findAll('.rrow')).toHaveLength(2)
    expect(wrapper.text()).toContain('One More Time')
    expect(wrapper.text()).toContain('Massive Attack')
  })

  it('shows "in catalog" and no import button for an already-known track', async () => {
    const wrapper = await mountWith([{ ...deezerItem, catalog_id: 42 }])

    const link = wrapper.find('.in-catalog')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/catalog/42')
    expect(wrapper.find('.btn-import').exists()).toBe(false)
  })

  it('imports a deezer result with { deezer_id }', async () => {
    apiPost.mockResolvedValue({
      data: { catalog_id: 99, created: true, title: 'One More Time', artist: 'Daft Punk' },
    })
    const wrapper = await mountWith([deezerItem])

    await wrapper.find('.btn-import').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/api/catalog/import', { deezer_id: 'd1' })
  })

  it('imports a tidal result with { tidal_id }', async () => {
    apiPost.mockResolvedValue({
      data: { catalog_id: 100, created: true, title: 'Teardrop', artist: 'Massive Attack' },
    })
    const wrapper = await mountWith([tidalItem])

    await wrapper.find('.btn-import').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/api/catalog/import', { tidal_id: 't1' })
  })

  it('switches the row to the imported state (link to the catalog entry) on success', async () => {
    apiPost.mockResolvedValue({
      data: { catalog_id: 99, created: true, title: 'One More Time', artist: 'Daft Punk' },
    })
    const wrapper = await mountWith([deezerItem])

    expect(wrapper.find('.in-catalog').exists()).toBe(false)
    await wrapper.find('.btn-import').trigger('click')
    await flushPromises()

    const link = wrapper.find('.in-catalog')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/catalog/99')
    expect(wrapper.find('.btn-import').exists()).toBe(false)
    expect(wrapper.emitted('imported')).toBeTruthy()
  })
})
