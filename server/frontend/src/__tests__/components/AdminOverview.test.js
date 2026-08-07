import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// The card actions POST enrichment jobs; mock the API so a click resolves to a
// task id (fire-and-forget — AdminOverview does not poll the task).
const { apiMock } = vi.hoisted(() => ({ apiMock: { post: vi.fn(), get: vi.fn() } }))
vi.mock('../../utils/api.js', () => ({ default: apiMock }))

import AdminOverview from '../../components/admin/AdminOverview.vue'

// 8 chantiers en backlog (compteur > 0), 4 à jour (compteur 0). Reprend les
// valeurs prod 06/08 du BRIEF (+ catalog.bpm_missing pour la 12ᵉ carte E2.c).
function backlogFixture() {
  return {
    captured_at: '2026-08-06T11:30:00Z',
    beatport: { pending: 2607, total_missing: 65722, abandoned: 14 },
    deezer: { pending: 0, total_missing: 29403, abandoned: 78 },
    artists: { to_link: 5, no_artwork: 2990 },
    sets: { recrawl: 501, flags_pending: 158 },
    artist_flags: { pending: 0 },
    genres: { unclassified: 42031, mappings_unmapped: 0 },
    catalog: { bpm_missing: 1234 },
    crawl: { playlists_due: 56, dlq: 0 },
  }
}

const norm = (s) => s.replace(/\s/g, '')

function mountOverview(props = {}) {
  return mount(AdminOverview, {
    props: { backlog: backlogFixture(), loading: false, error: false, ...props },
  })
}

describe('AdminOverview', () => {
  beforeEach(() => {
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: { task_id: 'job-1' } })
  })

  it('renders the 12 chantier cards', () => {
    const wrapper = mountOverview()
    expect(wrapper.findAll('.oc-card')).toHaveLength(12)
  })

  it('splits cards into backlog vs à-jour by their own counter', () => {
    const wrapper = mountOverview()
    // 8 backlog / 4 à jour.
    expect(wrapper.findAll('.oc-card--backlog')).toHaveLength(8)
    expect(wrapper.findAll('.oc-card--ok')).toHaveLength(4)
    // Backlog cards show a big mono value; à-jour cards show « À jour », never a 0.
    expect(wrapper.findAll('.oc-value')).toHaveLength(8)
    expect(wrapper.findAll('.oc-uptodate')).toHaveLength(4)
    expect(wrapper.text()).not.toContain('0 tracks')
    // Beatport backlog value surfaced (fr-FR thin space normalised away).
    const beatport = wrapper.findAll('.oc-card').find((c) => c.text().includes('Beatport'))
    expect(norm(beatport.find('.oc-value').text())).toBe('2607')
    expect(beatport.text()).toContain('Tracks à enrichir')
  })

  it('writes the synthesis count and a snapshot stamp', () => {
    const wrapper = mountOverview()
    expect(wrapper.find('.oc-summary-line').text()).toBe(
      '8 chantiers sur 12 ont du travail en attente.',
    )
    expect(wrapper.find('.oc-snapshot').text()).toMatch(/Snapshot \d{2}\/\d{2} · \d{2}:\d{2}/)
  })

  it('renders the unknown regime for a null counter (DLQ Redis down), excluded from the pending count', () => {
    const b = backlogFixture()
    b.crawl.dlq = null // Redis injoignable → compteur null, ni backlog ni « à jour ».
    const wrapper = mountOverview({ backlog: b })
    // Régimes : 8 backlog · 1 unknown (DLQ) · 3 ok (dlq n'est plus « à jour »).
    expect(wrapper.findAll('.oc-card--backlog')).toHaveLength(8)
    expect(wrapper.findAll('.oc-card--unknown')).toHaveLength(1)
    expect(wrapper.findAll('.oc-card--ok')).toHaveLength(3)
    // La carte DLQ rend un « — » (pas de pastille verte, pas de chiffre) + contexte Redis.
    const dlq = wrapper.findAll('.oc-card').find((c) => c.text().includes("File d'échec"))
    expect(dlq.classes()).toContain('oc-card--unknown')
    expect(dlq.find('.oc-unknown').text()).toBe('—')
    expect(dlq.find('.oc-check').exists()).toBe(false)
    expect(dlq.find('.oc-value').exists()).toBe(false)
    expect(dlq.text()).toContain('Redis injoignable')
    // Unknown n'est PAS « en attente » : la synthèse compte toujours 8 backlog.
    expect(wrapper.find('.oc-summary-line').text()).toBe(
      '8 chantiers sur 12 ont du travail en attente.',
    )
  })

  it('reads « Les 12 chantiers sont à jour. » when nothing is pending', () => {
    const clean = backlogFixture()
    clean.beatport.pending = 0
    clean.artists.to_link = 0
    clean.artists.no_artwork = 0
    clean.sets.recrawl = 0
    clean.sets.flags_pending = 0
    clean.genres.unclassified = 0
    clean.catalog.bpm_missing = 0
    clean.crawl.playlists_due = 0
    const wrapper = mountOverview({ backlog: clean })
    expect(wrapper.findAll('.oc-card--ok')).toHaveLength(12)
    expect(wrapper.find('.oc-summary-line').text()).toBe('Les 12 chantiers sont à jour.')
  })

  it('emits navigate with the target tab from a renvoi button', async () => {
    const wrapper = mountOverview()
    const monBtn = wrapper.findAll('button').find((b) => b.text() === 'Voir le monitoring')
    await monBtn.trigger('click')
    expect(wrapper.emitted('navigate')[0]).toEqual(['monitoring'])
  })

  it('renders the catalog-bpm card as a NEUTRAL nav renvoi to monitoring', async () => {
    // E2.c 12ᵉ carte : renvoi neutre (jamais btn--accent, jamais de job) vers le
    // monitoring — le drain BPM est une tâche nocturne automatique.
    const wrapper = mountOverview()
    const bpm = wrapper.findAll('.oc-card').find((c) => c.text().includes('À analyser (BPM)'))
    expect(bpm).toBeTruthy()
    const btn = bpm.find('button')
    expect(btn.text()).toBe('Voir le monitoring')
    expect(btn.classes()).not.toContain('btn--accent')
    expect(bpm.find('.oc-job').exists()).toBe(false)
    await btn.trigger('click')
    expect(wrapper.emitted('navigate').at(-1)).toEqual(['monitoring'])
  })

  it('emits refresh from the Actualiser button', async () => {
    const wrapper = mountOverview()
    await wrapper.find('.oc-refresh').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('POSTs the job endpoint and switches the card to « En cours… » on a job click', async () => {
    const wrapper = mountOverview()
    const jobBtn = wrapper.findAll('button').find((b) => b.text() === "Lancer l'enrichissement")
    await jobBtn.trigger('click')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/enrich-beatport')
    // The card now shows the job-in-progress line and the disabled « En cours… » button.
    const beatport = wrapper.findAll('.oc-card').find((c) => c.text().includes('Beatport'))
    expect(beatport.find('.oc-job').exists()).toBe(true)
    expect(beatport.find('button').text()).toBe('En cours…')
    expect(beatport.find('button').attributes('disabled')).toBeDefined()
  })

  it('shows 12 skeleton cards on first load (no backlog yet)', () => {
    const wrapper = mountOverview({ backlog: null, loading: true })
    expect(wrapper.findAll('.oc-card--skel')).toHaveLength(12)
    expect(wrapper.find('.oc-value').exists()).toBe(false)
  })

  it('shows the error banner and no grid when error is set', () => {
    const wrapper = mountOverview({ backlog: null, error: true })
    expect(wrapper.find('.oc-error').exists()).toBe(true)
    expect(wrapper.find('.oc-grid').exists()).toBe(false)
    // Réessayer re-emits refresh.
    wrapper.find('.oc-error .btn').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })
})
