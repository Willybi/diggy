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

  // Sémantique des badges REVUE (volontaire) : un badge ne compte plus QUE les files
  // d'action humaine (flags artistes, set-flags de dédup, DLQ) — les backlogs qui se
  // drainent automatiquement la nuit (Beatport, genres, artistes à lier/sans pochette,
  // recrawl sets, playlists dues) ne sont plus badgés. Le fixture existant a
  // artist_flags.pending=0 et sets.flags_pending=158 → seul Sets porte un badge.
  it('badges only the human-action queues (flags artistes, set-flags, DLQ)', async () => {
    const wrapper = await mountView()
    // artists = artist_flags.pending 0 → masqué · sets = flags_pending 158 ·
    // observability = dlq 0 → masqué · genres/enrichment/overview → jamais de badge.
    expect(norm(tabByLabel(wrapper, 'Sets').find('.tab-badge').text())).toBe('158')
    // Seul Sets porte un badge ici (les autres files d'action sont à 0).
    expect(wrapper.findAll('.tab-badge')).toHaveLength(1)
    expect(tabByLabel(wrapper, 'Artistes').find('.tab-badge').exists()).toBe(false)
    expect(tabByLabel(wrapper, 'Enrichissement').find('.tab-badge').exists()).toBe(false)
    expect(tabByLabel(wrapper, 'Genres').find('.tab-badge').exists()).toBe(false)
    expect(tabByLabel(wrapper, 'Observabilité').find('.tab-badge').exists()).toBe(false)
    expect(tabByLabel(wrapper, 'Aperçu').find('.tab-badge').exists()).toBe(false)
  })

  it('badges the Artistes tab with artist_flags.pending only', async () => {
    const b = backlogFixture()
    b.artist_flags.pending = 12
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    // 12 flags artistes à valider — to_link/no_artwork (backlogs auto) ne comptent plus.
    expect(norm(tabByLabel(wrapper, 'Artistes').find('.tab-badge').text())).toBe('12')
  })

  it('abbreviates a large action-queue badge above 9 999', async () => {
    const b = backlogFixture()
    b.sets.flags_pending = 42031
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    expect(tabByLabel(wrapper, 'Sets').find('.tab-badge').text()).toBe('42,0 k')
  })

  it('hides a badge whose count is 0', async () => {
    const b = backlogFixture()
    b.sets.flags_pending = 0
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    expect(tabByLabel(wrapper, 'Sets').find('.tab-badge').exists()).toBe(false)
  })

  it('badges the Observabilité tab with the DLQ count', async () => {
    const b = backlogFixture()
    b.crawl.dlq = 7
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    expect(norm(tabByLabel(wrapper, 'Observabilité').find('.tab-badge').text())).toBe('7')
  })

  it('treats a null DLQ (Redis down) as 0 in the observability badge', async () => {
    const b = backlogFixture()
    b.crawl.dlq = null
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: b })
    const wrapper = await mountView()
    // dlq null → 0 → pas de badge, pas de NaN.
    expect(tabByLabel(wrapper, 'Observabilité').find('.tab-badge').exists()).toBe(false)
  })

  it('shows no badges while the backlog fails to load', async () => {
    apiMock.get.mockReset()
    apiMock.get.mockRejectedValue(new Error('boom'))
    const wrapper = await mountView()
    expect(wrapper.findAll('.tab-badge')).toHaveLength(0)
  })
})
