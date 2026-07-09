import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../utils/api.js', () => ({
  default: { get: apiGet },
}))

// Default filter mounts in "unmapped" mode (mappingShowUnmapped = true).
// Main fetch (limit 200, unmapped) → 12 unmapped rows out of 40 total.
function mappingsResponder(url, config) {
  if (url !== '/api/taxonomy/mappings') return Promise.resolve({ data: {} })
  const p = config?.params || {}
  if (p.unmapped && p.limit === 200) {
    return Promise.resolve({ data: { items: [{ id: 1 }], total: 12 } })
  }
  if (p.limit === 1 && !p.unmapped) {
    return Promise.resolve({ data: { total: 40 } }) // grand-total complement
  }
  if (p.limit === 1 && p.unmapped) {
    return Promise.resolve({ data: { total: 12 } })
  }
  return Promise.resolve({ data: { items: [], total: 0 } })
}

describe('AdminGenres mapping stats', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiGet.mockImplementation(mappingsResponder)
  })

  it('issues only 2 mappings calls on mount (main fetch derives one stat)', async () => {
    const { default: AdminGenres } = await import('../../components/admin/AdminGenres.vue')
    mount(AdminGenres)
    await flushPromises()

    const mappingCalls = apiGet.mock.calls.filter(([url]) => url === '/api/taxonomy/mappings')
    expect(mappingCalls.length).toBe(2)
  })

  it('still renders the correct unmapped / total badge', async () => {
    const { default: AdminGenres } = await import('../../components/admin/AdminGenres.vue')
    const wrapper = mount(AdminGenres)
    await flushPromises()

    expect(wrapper.find('.flag-count').text()).toContain('12 / 40')
  })
})
