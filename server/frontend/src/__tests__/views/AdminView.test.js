import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// AdminView fetches /api/admin/backlog once on mount to feed BOTH the tab badges
// and the Aperçu panel. Mock the API; stub the 8 tab panels so their own mounts
// don't fire network calls.
const { apiMock } = vi.hoisted(() => ({ apiMock: { get: vi.fn() } }))
vi.mock('../../utils/api.js', () => ({ default: apiMock }))

import AdminView from '../../views/AdminView.vue'

function backlogFixture() {
  return {
    captured_at: '2026-08-06T11:30:00Z',
    beatport: { pending: 2607, total_missing: 65722, abandoned: 14 },
    deezer: { pending: 0, total_missing: 29403, abandoned: 78 },
    artists: { to_link: 5, no_artwork: 2990 },
    sets: { recrawl: 501, flags_pending: 158 },
    artist_flags: { pending: 0 },
    genres: { unclassified: 42031, mappings_unmapped: 0 },
    crawl: { playlists_due: 56, dlq: 0 },
  }
}

const STUBS = {
  AdminOverview: { template: '<div class="stub-overview"></div>' },
  AdminArtists: { template: '<div class="stub-artists"></div>' },
  AdminFlags: true,
  AdminSets: true,
  AdminGenres: true,
  AdminCrawl: true,
  AdminMonitoring: true,
  AdminBeatport: true,
}

const norm = (s) => s.replace(/\s/g, '')
const tabByLabel = (wrapper, label) =>
  wrapper.findAll('.tab-btn').find((b) => b.text().includes(label))

async function mountView() {
  const wrapper = mount(AdminView, { global: { stubs: STUBS } })
  await flushPromises()
  return wrapper
}

describe('AdminView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: backlogFixture() })
  })

  it('fetches the backlog once on mount', async () => {
    await mountView()
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/backlog')
    expect(apiMock.get).toHaveBeenCalledTimes(1)
  })

  it('lands on the Aperçu tab by default', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.stub-overview').exists()).toBe(true)
    expect(wrapper.find('.stub-artists').exists()).toBe(false)
    // Aperçu is the first tab and is active.
    const first = wrapper.findAll('.tab-btn')[0]
    expect(first.text()).toContain('Aperçu')
    expect(first.classes()).toContain('active')
  })

  it('switches panel when another tab is clicked', async () => {
    const wrapper = await mountView()
    await tabByLabel(wrapper, 'Artistes').trigger('click')
    expect(wrapper.find('.stub-artists').exists()).toBe(true)
    expect(wrapper.find('.stub-overview').exists()).toBe(false)
  })

  it('renders tab badges from the backlog sums', async () => {
    const wrapper = await mountView()
    // artists = 5 + 2990 = 2 995 · sets = 501 + 158 = 659 · beatport = 2 607 ·
    // crawl = 56 + 0 = 56 · genres = 42 031 → abbreviated « 42,0 k ».
    expect(norm(tabByLabel(wrapper, 'Artistes').find('.tab-badge').text())).toBe('2995')
    expect(norm(tabByLabel(wrapper, 'Sets').find('.tab-badge').text())).toBe('659')
    expect(norm(tabByLabel(wrapper, 'Beatport').find('.tab-badge').text())).toBe('2607')
    expect(tabByLabel(wrapper, 'Genres').find('.tab-badge').text()).toBe('42,0 k')
    // 5 badge-bearing tabs (flags is 0 → hidden).
    expect(wrapper.findAll('.tab-badge')).toHaveLength(5)
  })

  it('hides the badge on a 0-sum tab and never on Aperçu / Monitoring', async () => {
    const wrapper = await mountView()
    expect(tabByLabel(wrapper, 'Flags').find('.tab-badge').exists()).toBe(false)
    expect(tabByLabel(wrapper, 'Aperçu').find('.tab-badge').exists()).toBe(false)
    expect(tabByLabel(wrapper, 'Monitoring').find('.tab-badge').exists()).toBe(false)
  })

  it('shows no badges while the backlog fails to load', async () => {
    apiMock.get.mockReset()
    apiMock.get.mockRejectedValue(new Error('boom'))
    const wrapper = await mountView()
    expect(wrapper.findAll('.tab-badge')).toHaveLength(0)
  })
})
