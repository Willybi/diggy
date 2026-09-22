import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// AdminChannels talks to /api/admin/channels (paginated list + PATCH override + POST
// add) and /api/admin/channels/candidates (seed) — all mocked here (pattern:
// AdminCohort.test.js). No router-link, no useTaskPoll → nothing else to stub.
const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
}))
vi.mock('../../utils/api.js', () => ({ default: apiMock }))

import AdminChannels from '../../components/admin/AdminChannels.vue'

function channelItem(over = {}) {
  return {
    id: 7,
    platform: 'youtube',
    external_id: 'UC123',
    name: 'Ritter Butzke',
    channel_type: null,
    artist_id: null,
    watched: true,
    excluded: false,
    last_checked_at: null,
    ...over,
  }
}

function candidateItem(over = {}) {
  return { name: 'Boiler Room', set_count: 3, trackid_count: 42, ...over }
}

// Default: channels list has one row, candidates has one entry.
function primeGet({ channels = [channelItem()], total = 1, candidates = [candidateItem()] } = {}) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/admin/channels') return Promise.resolve({ data: { total, items: channels } })
    if (url === '/api/admin/channels/candidates')
      return Promise.resolve({ data: { items: candidates } })
    return Promise.resolve({ data: {} })
  })
}

const mountChannels = () => mount(AdminChannels)

// Locate a <button> by its exact trimmed text (optionally scoped to a selector).
function btnByText(wrapper, text, scope) {
  const root = scope ? wrapper.find(scope) : wrapper
  return root.findAll('button').find((b) => b.text() === text)
}

describe('AdminChannels', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.patch.mockReset()
    apiMock.post.mockReset()
    primeGet()
  })

  it('fetches channels and candidates on mount and renders both', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels', {
      params: { page: 1, page_size: 50 },
    })
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels/candidates', {
      params: { limit: 50 },
    })
    // Channel row + candidate row both render.
    expect(wrapper.text()).toContain('Ritter Butzke')
    expect(wrapper.text()).toContain('UC123')
    expect(wrapper.text()).toContain('Boiler Room')
    expect(wrapper.text()).toContain('42') // trackid_count
  })

  it('toggles watched with a PATCH and swaps the row in place', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.patch.mockResolvedValue({ data: channelItem({ watched: false }) })
    await btnByText(wrapper, 'Ne plus surveiller').trigger('click')
    await flushPromises()

    expect(apiMock.patch).toHaveBeenCalledWith('/api/admin/channels/7', { watched: false })
    expect(btnByText(wrapper, 'Surveiller')).toBeTruthy()
  })

  it('toggles excluded with a PATCH', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.patch.mockResolvedValue({ data: channelItem({ excluded: true }) })
    await btnByText(wrapper, 'Exclure').trigger('click')
    await flushPromises()

    expect(apiMock.patch).toHaveBeenCalledWith('/api/admin/channels/7', { excluded: true })
    expect(btnByText(wrapper, 'Réintégrer')).toBeTruthy()
  })

  it('changes the channel type via the row select (PATCH, "" → null when cleared)', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.patch.mockResolvedValue({ data: channelItem({ channel_type: 'label' }) })
    await wrapper.find('.chn-select--sm').setValue('label')
    await flushPromises()

    expect(apiMock.patch).toHaveBeenCalledWith('/api/admin/channels/7', { channel_type: 'label' })
  })

  it('filters the channels list by watched with a re-fetch', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.get.mockClear()
    await btnByText(wrapper, 'Surveillées', '.at-seg').trigger('click')
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels', {
      params: { page: 1, page_size: 50, watched: true },
    })
  })

  it('adds a channel by URL (POST) then refetches the list', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.post.mockResolvedValue({ data: channelItem() })
    await wrapper
      .find('.chn-toolbar .chn-input--grow')
      .setValue('https://youtube.com/@ritterbutzke')
    apiMock.get.mockClear()
    await btnByText(wrapper, 'Ajouter', '.chn-toolbar').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/channels', {
      url: 'https://youtube.com/@ritterbutzke',
    })
    // The list is refreshed after a successful add.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels', {
      params: { page: 1, page_size: 50 },
    })
  })

  it('surfaces a 400 add error inline without toasting', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.post.mockRejectedValue({ response: { data: { detail: 'URL invalide' } } })
    await wrapper.find('.chn-toolbar .chn-input--grow').setValue('nope')
    await btnByText(wrapper, 'Ajouter', '.chn-toolbar').trigger('click')
    await flushPromises()

    expect(wrapper.find('.chn-add-error').text()).toContain('URL invalide')
  })

  it('adds a candidate with its name (POST) and removes it from the seed', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.post.mockResolvedValue({ data: channelItem() })
    await wrapper.find('.chn-cand-add .chn-input--grow').setValue('https://youtube.com/@boilerroom')
    await btnByText(wrapper, 'Ajouter', '.chn-cand-add').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/channels', {
      url: 'https://youtube.com/@boilerroom',
      name: 'Boiler Room',
    })
    // The candidate left the seed (it is now a watched channel).
    expect(wrapper.text()).not.toContain('Boiler Room')
  })
})
