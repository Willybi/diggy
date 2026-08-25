import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// D10 : l'IA admin est passée de 8 onglets en v-if (zéro URL) à 6 onglets
// URL-adressables (`/admin/:tab`). Ce fichier remplace LÉGITIMEMENT l'ancien test
// 8-onglets — l'IA a volontairement changé (onglets Flags/Beatport/Crawl/Monitoring
// fusionnés dans Artistes/Enrichissement/Observabilité).
//
// AdminView lit l'onglet actif dans la route et pousse `/admin/:tab` au clic ou sur
// l'événement `navigate` de l'Aperçu → on mocke vue-router (useRoute/useRouter,
// pattern LoginCallbackView.test.js). On mocke aussi l'API (le fetch backlog du
// montage) et on stub les panneaux pour que leurs propres montages ne tirent pas
// d'appel réseau.
const { apiMock } = vi.hoisted(() => ({ apiMock: { get: vi.fn() } }))
vi.mock('../../utils/api.js', () => ({ default: apiMock }))

const { routeState, pushMock } = vi.hoisted(() => ({
  routeState: { value: { params: {} } },
  pushMock: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => routeState.value,
  useRouter: () => ({ push: pushMock }),
}))

import AdminView from '../../views/AdminView.vue'
import AdminOverview from '../../components/admin/AdminOverview.vue'

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

// Chaque panneau est stubbé par un div identifiable — un onglet peut en empiler
// plusieurs (Artistes = Artistes + Flags, etc.).
const STUBS = {
  AdminOverview: { template: '<div class="stub-overview"></div>' },
  AdminArtists: { template: '<div class="stub-artists"></div>' },
  AdminFlags: { template: '<div class="stub-flags"></div>' },
  AdminSets: { template: '<div class="stub-sets"></div>' },
  AdminGenres: { template: '<div class="stub-genres"></div>' },
  AdminBeatport: { template: '<div class="stub-beatport"></div>' },
  AdminEnrichmentActions: { template: '<div class="stub-enrich-actions"></div>' },
  AdminMonitoring: { template: '<div class="stub-monitoring"></div>' },
  AdminCrawl: { template: '<div class="stub-crawl"></div>' },
  AdminAuditLog: { template: '<div class="stub-audit"></div>' },
}

const norm = (s) => s.replace(/\s/g, '')
const tabByLabel = (wrapper, label) =>
  wrapper.findAll('.tab-btn').find((b) => b.text().includes(label))

// `tab` non défini → route sans param → activeTab retombe sur « overview ».
async function mountView(tab) {
  if (tab !== undefined) routeState.value = { params: { tab } }
  const wrapper = mount(AdminView, { global: { stubs: STUBS } })
  await flushPromises()
  return wrapper
}

describe('AdminView', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: backlogFixture() })
    pushMock.mockReset()
    routeState.value = { params: {} }
  })

  it('fetches the backlog once on mount', async () => {
    await mountView()
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/backlog')
    expect(apiMock.get).toHaveBeenCalledTimes(1)
  })

  it('renders the 6 tabs of the new IA in order', async () => {
    const wrapper = await mountView()
    const texts = wrapper.findAll('.tab-btn').map((b) => b.text())
    expect(texts).toHaveLength(6)
    expect(texts[0]).toContain('Aperçu')
    expect(texts[1]).toContain('Artistes')
    expect(texts[2]).toContain('Sets')
    expect(texts[3]).toContain('Genres')
    expect(texts[4]).toContain('Enrichissement')
    expect(texts[5]).toContain('Observabilité')
  })

  it('lands on the Aperçu tab by default (no tab param)', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.stub-overview').exists()).toBe(true)
    expect(wrapper.find('.stub-artists').exists()).toBe(false)
    const first = wrapper.findAll('.tab-btn')[0]
    expect(first.text()).toContain('Aperçu')
    expect(first.classes()).toContain('active')
  })

  it('reads the active tab from the route param', async () => {
    const wrapper = await mountView('genres')
    expect(wrapper.find('.stub-genres').exists()).toBe(true)
    expect(wrapper.find('.stub-overview').exists()).toBe(false)
    expect(tabByLabel(wrapper, 'Genres').classes()).toContain('active')
  })

  it('falls back to Aperçu for an unknown tab param', async () => {
    const wrapper = await mountView('does-not-exist')
    expect(wrapper.find('.stub-overview').exists()).toBe(true)
    expect(wrapper.findAll('.tab-btn')[0].classes()).toContain('active')
  })

  it('stacks Artistes + Flags on the artists tab', async () => {
    const wrapper = await mountView('artists')
    expect(wrapper.find('.stub-artists').exists()).toBe(true)
    expect(wrapper.find('.stub-flags').exists()).toBe(true)
  })

  it('stacks Beatport + EnrichmentActions on the enrichment tab', async () => {
    const wrapper = await mountView('enrichment')
    expect(wrapper.find('.stub-beatport').exists()).toBe(true)
    expect(wrapper.find('.stub-enrich-actions').exists()).toBe(true)
  })

  it('stacks Monitoring + Crawl + AuditLog on the observability tab', async () => {
    const wrapper = await mountView('observability')
    expect(wrapper.find('.stub-monitoring').exists()).toBe(true)
    expect(wrapper.find('.stub-crawl').exists()).toBe(true)
    expect(wrapper.find('.stub-audit').exists()).toBe(true)
  })

  it('pushes /admin/:tab when a tab is clicked', async () => {
    const wrapper = await mountView()
    await tabByLabel(wrapper, 'Artistes').trigger('click')
    expect(pushMock).toHaveBeenCalledWith('/admin/artists')
  })

  it('does not re-push when the already-active tab is clicked', async () => {
    const wrapper = await mountView()
    await tabByLabel(wrapper, 'Aperçu').trigger('click')
    expect(pushMock).not.toHaveBeenCalled()
  })

  // Nav PROGRAMMATIQUE (une carte de renvoi de l'Aperçu émet `navigate`) → push de
  // l'URL cible. Le smooth-scroll a besoin du layout → non asserté ici.
  it('pushes the target route on a programmatic navigate', async () => {
    const wrapper = await mountView()
    wrapper.findComponent(AdminOverview).vm.$emit('navigate', 'observability')
    await flushPromises()
    expect(pushMock).toHaveBeenCalledWith('/admin/observability')
  })

  it('renders tab badges recalculated for the new IA', async () => {
    const wrapper = await mountView()
    // artists = 5 + 2990 + artist_flags 0 = 2 995 · sets = 501 + 158 = 659 ·
    // enrichment = beatport.pending 2 607 · observability = 56 + dlq 0 = 56 ·
    // genres = 42 031 → abrégé « 42,0 k ».
    expect(norm(tabByLabel(wrapper, 'Artistes').find('.tab-badge').text())).toBe('2995')
    expect(norm(tabByLabel(wrapper, 'Sets').find('.tab-badge').text())).toBe('659')
    expect(norm(tabByLabel(wrapper, 'Enrichissement').find('.tab-badge').text())).toBe('2607')
    expect(norm(tabByLabel(wrapper, 'Observabilité').find('.tab-badge').text())).toBe('56')
    expect(tabByLabel(wrapper, 'Genres').find('.tab-badge').text()).toBe('42,0 k')
    // 5 badge-bearing tabs (overview never carries one).
    expect(wrapper.findAll('.tab-badge')).toHaveLength(5)
    expect(tabByLabel(wrapper, 'Aperçu').find('.tab-badge').exists()).toBe(false)
  })

  it('folds artist_flags.pending into the Artistes badge', async () => {
    const b = backlogFixture()
    b.artist_flags.pending = 12
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    // 5 + 2990 + 12 = 3 007.
    expect(norm(tabByLabel(wrapper, 'Artistes').find('.tab-badge').text())).toBe('3007')
  })

  it('hides a badge whose sum is 0', async () => {
    const b = backlogFixture()
    b.crawl.playlists_due = 0
    b.crawl.dlq = 0
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    expect(tabByLabel(wrapper, 'Observabilité').find('.tab-badge').exists()).toBe(false)
  })

  it('treats a null DLQ (Redis down) as 0 in the observability badge', async () => {
    const b = backlogFixture()
    b.crawl.dlq = null
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    // playlists_due 56 + (null → 0) = 56, pas de NaN.
    expect(norm(tabByLabel(wrapper, 'Observabilité').find('.tab-badge').text())).toBe('56')
  })

  it('shows no badges while the backlog fails to load', async () => {
    apiMock.get.mockReset()
    apiMock.get.mockRejectedValue(new Error('boom'))
    const wrapper = await mountView()
    expect(wrapper.findAll('.tab-badge')).toHaveLength(0)
  })
})
