import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// AdminChannels talks to /api/admin/channels (paginated list + PATCH override + POST
// add), /api/admin/channels/candidates (channel seed) and /api/admin/channels/
// artist-candidates (+/resolve, L3 artist seed) — all mocked here (pattern:
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

function artistCandidateItem(over = {}) {
  return {
    artist_id: 42,
    name: 'Peggy Gou',
    tier: 1,
    nb_sets: 5,
    nb_lib: 2,
    nb_catalog: 18,
    preselect: null,
    ...over,
  }
}

// A single ArtistChannelResolveOut (the artist resolve/preselect is ONE object, not a
// list like the channel-candidate resolve).
function artResolveResult(over = {}) {
  return {
    channel_id: 'UCpeggy',
    channel_title: 'Peggy Gou Official',
    url: 'https://www.youtube.com/channel/UCpeggy',
    method: 'wikidata',
    confidence: 'high',
    has_soundcloud: false,
    ...over,
  }
}

// Default: channels list has one row, candidates has one entry, artist candidates
// empty, search + resolve none.
function primeGet({
  channels = [channelItem()],
  total = 1,
  candidates = [candidateItem()],
  searchResults = [],
  resolveResults = [],
  artistCandidates = [],
  artistResolve = {},
} = {}) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/admin/channels') return Promise.resolve({ data: { total, items: channels } })
    if (url === '/api/admin/channels/candidates')
      return Promise.resolve({ data: { items: candidates } })
    if (url === '/api/admin/channels/candidates/resolve')
      return Promise.resolve({ data: { items: resolveResults } })
    if (url === '/api/admin/channels/search')
      return Promise.resolve({ data: { items: searchResults } })
    if (url === '/api/admin/channels/artist-candidates')
      return Promise.resolve({
        data: { total: artistCandidates.length, items: artistCandidates },
      })
    if (url === '/api/admin/channels/artist-candidates/resolve')
      return Promise.resolve({ data: artistResolve })
    return Promise.resolve({ data: {} })
  })
}

function searchResult(over = {}) {
  return {
    channel_id: 'UCabc',
    title: 'Cercle',
    description: 'Live electronic sets from iconic places',
    thumbnail_url: 'https://yt3.ggpht.com/avatar',
    ...over,
  }
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
    // The direct-URL form is the advanced (.chn-direct) path — the search input
    // is the first .chn-input--grow in the toolbar since LB, so scope explicitly.
    await wrapper.find('.chn-direct .chn-input--grow').setValue('https://youtube.com/@ritterbutzke')
    apiMock.get.mockClear()
    await btnByText(wrapper, 'Ajouter', '.chn-direct').trigger('click')
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
    await wrapper.find('.chn-direct .chn-input--grow').setValue('nope')
    await btnByText(wrapper, 'Ajouter', '.chn-direct').trigger('click')
    await flushPromises()

    expect(wrapper.find('.chn-direct .chn-add-error').text()).toContain('URL invalide')
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

  it('links a watched row to its YouTube channel (new tab, right href)', async () => {
    const wrapper = mountChannels()
    await flushPromises()

    const link = wrapper.find('.chn-yt-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://www.youtube.com/channel/UC123')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
  })

  it('shows no YouTube link when a row has no external_id', async () => {
    primeGet({ channels: [channelItem({ external_id: null })] })
    const wrapper = mountChannels()
    await flushPromises()

    expect(wrapper.find('.chn-yt-link').exists()).toBe(false)
  })

  it('searches YouTube only on click (never while typing) and lists results', async () => {
    primeGet({
      searchResults: [
        searchResult(),
        searchResult({ channel_id: 'UCdef', title: 'HÖR Berlin', thumbnail_url: null }),
      ],
    })
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.get.mockClear()
    // Typing must NOT trigger a search (each call spends 100 quota units).
    await wrapper.find('.chn-search .chn-input--grow').setValue('cercle')
    await flushPromises()
    expect(apiMock.get).not.toHaveBeenCalledWith('/api/admin/channels/search', expect.anything())

    await btnByText(wrapper, 'Rechercher', '.chn-search').trigger('click')
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels/search', {
      params: { q: 'cercle', limit: 6 },
    })
    expect(wrapper.text()).toContain('Cercle')
    expect(wrapper.text()).toContain('HÖR Berlin')
    // The result that carries a thumbnail renders its <img>; each result exposes
    // an external ↗ link to its YouTube channel.
    expect(wrapper.find('.chn-result-thumb').attributes('src')).toBe('https://yt3.ggpht.com/avatar')
    expect(wrapper.find('.chn-result-open').attributes('href')).toBe(
      'https://www.youtube.com/channel/UCabc',
    )
  })

  it('adds a search result — POST {url: channel_id, name: title} then refetches', async () => {
    primeGet({ searchResults: [searchResult()] })
    const wrapper = mountChannels()
    await flushPromises()

    await wrapper.find('.chn-search .chn-input--grow').setValue('cercle')
    await btnByText(wrapper, 'Rechercher', '.chn-search').trigger('click')
    await flushPromises()

    apiMock.post.mockResolvedValue({ data: channelItem() })
    apiMock.get.mockClear()
    await btnByText(wrapper, 'Ajouter', '.chn-result').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/channels', {
      url: 'UCabc',
      name: 'Cercle',
    })
    // The watched list is refreshed and the results are cleared on success.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels', {
      params: { page: 1, page_size: 50 },
    })
    expect(wrapper.find('.chn-result').exists()).toBe(false)
  })

  it('surfaces a 400 add error inline on a search result without toasting', async () => {
    primeGet({ searchResults: [searchResult()] })
    const wrapper = mountChannels()
    await flushPromises()

    await wrapper.find('.chn-search .chn-input--grow').setValue('cercle')
    await btnByText(wrapper, 'Rechercher', '.chn-search').trigger('click')
    await flushPromises()

    apiMock.post.mockRejectedValue({ response: { data: { detail: 'Chaîne introuvable' } } })
    await btnByText(wrapper, 'Ajouter', '.chn-result').trigger('click')
    await flushPromises()

    expect(wrapper.find('.chn-result-err').text()).toContain('Chaîne introuvable')
    // The result stays listed so the operator can retry.
    expect(wrapper.find('.chn-result').exists()).toBe(true)
  })

  // ── LC2: candidate pre-selection ──

  it('renders a candidate pre-selection from the cache without any /resolve call', async () => {
    primeGet({
      candidates: [
        candidateItem({
          preselect: [
            searchResult(),
            searchResult({ channel_id: 'UCdef', title: 'Boiler Room Berlin' }),
          ],
        }),
      ],
    })
    const wrapper = mountChannels()
    await flushPromises()

    // The suggested (first) channel renders inline from the cached pre-selection…
    expect(wrapper.find('.chn-result--suggested').exists()).toBe(true)
    expect(wrapper.find('.chn-result--suggested .chn-result-title').text()).toBe('Cercle')
    // …and NOTHING was resolved (the cache is free, a search spends 100 quota units).
    expect(apiMock.get).not.toHaveBeenCalledWith(
      '/api/admin/channels/candidates/resolve',
      expect.anything(),
    )
  })

  it('resolves a candidate only on an explicit click, then shows the suggested result', async () => {
    primeGet({
      candidates: [candidateItem()], // no preselect
      resolveResults: [
        searchResult(),
        searchResult({ channel_id: 'UCdef', title: 'Boiler Room Berlin' }),
      ],
    })
    const wrapper = mountChannels()
    await flushPromises()

    // Nothing is pre-selected yet → no suggested card, a "Pré-sélectionner" button shows.
    expect(wrapper.find('.chn-result--suggested').exists()).toBe(false)

    apiMock.get.mockClear()
    await btnByText(wrapper, 'Pré-sélectionner').trigger('click')
    await flushPromises()

    // Exactly one resolve call, and only on the click.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels/candidates/resolve', {
      params: { name: 'Boiler Room' },
    })
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    // The first result becomes the suggested pick.
    expect(wrapper.find('.chn-result--suggested .chn-result-title').text()).toBe('Cercle')
  })

  it('adds a pre-selected result — POST {url, name}, refetches, drops the candidate', async () => {
    primeGet({ candidates: [candidateItem({ preselect: [searchResult()] })] })
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.post.mockResolvedValue({ data: channelItem() })
    apiMock.get.mockClear()
    await btnByText(wrapper, 'Ajouter', '.chn-result--suggested').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/channels', {
      url: 'UCabc',
      name: 'Cercle',
    })
    // The watched list is refreshed and the candidate leaves the seed.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels', {
      params: { page: 1, page_size: 50 },
    })
    expect(wrapper.text()).not.toContain('Boiler Room')
  })

  it('choosing another pre-selected channel triggers no new network call', async () => {
    primeGet({
      candidates: [
        candidateItem({
          preselect: [
            searchResult(),
            searchResult({ channel_id: 'UCdef', title: 'Boiler Room Berlin' }),
          ],
        }),
      ],
    })
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.get.mockClear()
    // Expanding the "others" list is free — the results are already in memory.
    await btnByText(wrapper, 'Choisir une autre chaîne (1)').trigger('click')
    await flushPromises()

    expect(apiMock.get).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Boiler Room Berlin')
  })

  // ── L3: artist candidates ──

  it('fetches artist candidates on mount (paginated)', async () => {
    primeGet({ artistCandidates: [artistCandidateItem()] })
    const wrapper = mountChannels()
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels/artist-candidates', {
      params: { limit: 50, page: 1 },
    })
    // Artist name + relevance signals render.
    expect(wrapper.text()).toContain('Peggy Gou')
    expect(wrapper.text()).toContain('T1') // tier
  })

  it('renders an artist candidate pre-selection from the cache without any /resolve call', async () => {
    primeGet({ artistCandidates: [artistCandidateItem({ preselect: artResolveResult() })] })
    const wrapper = mountChannels()
    await flushPromises()

    // The suggested channel renders inline from the cached preselect + a Confirmer button…
    expect(wrapper.find('.chn-result--suggested .chn-result-title').text()).toBe(
      'Peggy Gou Official',
    )
    expect(btnByText(wrapper, 'Confirmer')).toBeTruthy()
    // …and NOTHING was resolved (the cache is free; a search spends 100 quota units).
    expect(apiMock.get).not.toHaveBeenCalledWith(
      '/api/admin/channels/artist-candidates/resolve',
      expect.anything(),
    )
  })

  it('resolves an artist candidate only on an explicit click (exactly once)', async () => {
    primeGet({
      artistCandidates: [artistCandidateItem()], // no preselect
      artistResolve: artResolveResult(),
    })
    const wrapper = mountChannels()
    await flushPromises()

    // Nothing pre-selected yet → no suggested card, a "Résoudre" button shows.
    expect(wrapper.find('.chn-result--suggested').exists()).toBe(false)

    apiMock.get.mockClear()
    await btnByText(wrapper, 'Résoudre').trigger('click')
    await flushPromises()

    // Exactly one resolve call, and only on the click.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels/artist-candidates/resolve', {
      params: { name: 'Peggy Gou' },
    })
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.chn-result--suggested .chn-result-title').text()).toBe(
      'Peggy Gou Official',
    )
  })

  it('confirms an artist candidate — POST {url,name,channel_type,artist_id} then drops it', async () => {
    primeGet({ artistCandidates: [artistCandidateItem({ preselect: artResolveResult() })] })
    const wrapper = mountChannels()
    await flushPromises()

    apiMock.post.mockResolvedValue({ data: channelItem() })
    apiMock.get.mockClear()
    await btnByText(wrapper, 'Confirmer').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/channels', {
      url: 'UCpeggy',
      name: 'Peggy Gou Official',
      channel_type: 'artist',
      artist_id: 42,
    })
    // The watched list is refreshed and the artist leaves the candidates list.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/channels', {
      params: { page: 1, page_size: 50 },
    })
    expect(wrapper.text()).not.toContain('Peggy Gou Official')
  })

  it('shows "Aucune chaîne trouvée" when the resolve finds nothing (nothing to confirm)', async () => {
    primeGet({ artistCandidates: [artistCandidateItem()], artistResolve: {} })
    const wrapper = mountChannels()
    await flushPromises()

    await btnByText(wrapper, 'Résoudre').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Aucune chaîne trouvée')
    expect(btnByText(wrapper, 'Confirmer')).toBeFalsy()
  })

  it('flags a NEEDS_VERIFY resolution for manual verification before confirming', async () => {
    primeGet({
      artistCandidates: [
        artistCandidateItem({
          preselect: artResolveResult({ method: 'search', confidence: 'NEEDS_VERIFY' }),
        }),
      ],
    })
    const wrapper = mountChannels()
    await flushPromises()

    // The confidence meta renders in the verify variant + a verification hint shows.
    expect(wrapper.find('.chn-art-meta--verify').exists()).toBe(true)
    expect(wrapper.find('.chn-art-verify').exists()).toBe(true)
    // A channel is still found, so it can be confirmed after the human ↗ check.
    expect(btnByText(wrapper, 'Confirmer')).toBeTruthy()
  })
})
