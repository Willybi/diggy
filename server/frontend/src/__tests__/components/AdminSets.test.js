import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Mock the API (get for the flags/attached lists, post for detach) and neuter
// useTaskPoll (the link-artists poller is irrelevant to the detach section).
const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))
vi.mock('../../composables/useTaskPoll.js', () => ({
  useTaskPoll: () => ({ start: vi.fn() }),
}))

import AdminSets from '../../components/admin/AdminSets.vue'

// S1: the flags/attached lists are now paginated SERVER-side (limit=10&offset=N).
// The "server" model of attached groups is mutable so a detach POST (which
// mutates it) is reflected by the follow-up refetch — mirroring prod, where the
// component reloads the page after every action instead of mutating locally.
let attachedGroups

function resetServer() {
  attachedGroups = [
    {
      id: 10,
      set_id_a: 100,
      set_id_b: 101,
      title_a: 'Set A',
      title_b: 'Set B',
      member_set_ids: null,
      member_titles: [],
    },
    {
      id: 20,
      set_id_a: 200,
      set_id_b: null,
      title_a: '',
      title_b: null,
      member_set_ids: [200, 201, 202],
      member_titles: ['Grp 1', 'Grp 2', 'Grp 3'],
    },
  ]
}

function getResponder(url) {
  if (url.startsWith('/api/admin/set-flags?status=pending')) {
    return Promise.resolve({ data: { total: 0, items: [] } })
  }
  if (url.startsWith('/api/admin/set-flags?status=attached')) {
    // limit=10 fits both groups on page 1 → no offset slicing needed here.
    return Promise.resolve({
      data: { total: attachedGroups.length, items: attachedGroups.slice(0, 10) },
    })
  }
  return Promise.resolve({ data: { total: 0, items: [] } })
}

// A detach POST mutates the server model so the refetch sees the change:
// on a group (member arrays) it drops the one set; on a pair it nulls that side.
function detachPost(url) {
  const m = url.match(/\/api\/admin\/sets\/(\d+)\/detach/)
  if (m) {
    const setId = Number(m[1])
    attachedGroups = attachedGroups.map((g) => {
      if (g.member_set_ids) {
        const idx = g.member_set_ids.indexOf(setId)
        if (idx === -1) return g
        return {
          ...g,
          member_set_ids: g.member_set_ids.filter((x) => x !== setId),
          member_titles: g.member_titles.filter((_, i) => i !== idx),
        }
      }
      if (g.set_id_a === setId) return { ...g, set_id_a: null, title_a: null }
      if (g.set_id_b === setId) return { ...g, set_id_b: null, title_b: null }
      return g
    })
  }
  return Promise.resolve({ data: { ok: true } })
}

describe('AdminSets — section « Sets attachés »', () => {
  beforeEach(() => {
    resetServer()
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.get.mockImplementation(getResponder)
    apiMock.post.mockImplementation(detachPost)
  })

  it('renders attached sets (pair + group) with a « Détacher » button per set', async () => {
    const wrapper = mount(AdminSets)
    await flushPromises()

    const rows = wrapper.findAll('.attached-set')
    // Pair flag → 2 sets, group flag → 3 sets.
    expect(rows.length).toBe(5)
    expect(wrapper.text()).toContain('Set A')
    expect(wrapper.text()).toContain('Grp 2')
    // D11 reskin: the per-set detach control is now an icon button (link-off)
    // labelled via aria-label instead of visible text.
    rows.forEach((row) => {
      const btn = row.find('button')
      expect(btn.exists()).toBe(true)
      expect(btn.attributes('aria-label')).toBe('Détacher')
    })
  })

  it('POSTs the detach endpoint and reflects the server after refetch', async () => {
    const wrapper = mount(AdminSets)
    await flushPromises()

    const firstRow = wrapper.findAll('.attached-set')[0]
    await firstRow.find('button').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/sets/100/detach')
    // S1: the component refetches the page; the detached set (Set A) is gone,
    // the sibling of the pair (Set B) remains.
    const rows = wrapper.findAll('.attached-set')
    expect(rows.length).toBe(4)
    expect(wrapper.text()).not.toContain('Set A')
    expect(wrapper.text()).toContain('Set B')
  })

  it('surfaces an inline error on a failed detach (list not mutated)', async () => {
    apiMock.post.mockRejectedValue({ response: { data: { detail: 'Boom' } } })
    const wrapper = mount(AdminSets)
    await flushPromises()

    await wrapper.findAll('.attached-set')[0].find('button').trigger('click')
    await flushPromises()

    // Same pattern as attach/reject: a section-level error line is shown and the
    // list is left as-is (no refetch on the error path).
    // D11 reskin renamed the legacy `.sync-error` line to `.sf-state--err`.
    expect(wrapper.find('.sf-state--err').text()).toContain('Boom')
    expect(wrapper.findAll('.attached-set').length).toBe(5)
  })
})

describe('AdminSets — flags en attente : paires twin_rule', () => {
  function twinFlag(overrides = {}, signals = {}) {
    return {
      id: 1,
      set_id_a: 100,
      set_id_b: 101,
      flag_type: 'duplicate_candidate',
      confidence: null,
      signals: {
        dd: 0.0164,
        twin_rule: 'date',
        reason: 'same date, each title has own words',
        ...signals,
      },
      status: 'pending',
      created_at: '2026-09-01T00:00:00Z',
      title_a: 'Ana @ Boiler Room',
      title_b: 'Ana b2b Aya @ Boiler Room',
      event_date_a: null,
      event_date_b: null,
      channel_a: 'Boiler Room',
      channel_b: 'Boiler Room Official',
      duration_ms_a: 3600000,
      duration_ms_b: 3660000,
      source_url_a: 'https://www.youtube.com/watch?v=abc',
      source_url_b: 'https://trackid.net/audiostream/ana',
      played_date_a: '2026-06-21',
      played_date_b: '2026-06-22',
      source_a: 'youtube',
      source_b: 'trackid',
      member_set_ids: null,
      member_titles: [],
      member_event_dates: [],
      ...overrides,
    }
  }

  async function mountWith(flag) {
    apiMock.get.mockReset()
    apiMock.get.mockImplementation((url) => {
      if (url.startsWith('/api/admin/set-flags?status=pending')) {
        return Promise.resolve({ data: { total: 1, items: [flag] } })
      }
      return Promise.resolve({ data: { total: 0, items: [] } })
    })
    const wrapper = mount(AdminSets)
    await flushPromises()
    return wrapper
  }

  function chips(wrapper) {
    return wrapper.findAll('.sf-chip').map((c) => c.text())
  }

  it('shows source, channel, duration, link and translated reason per set', async () => {
    const wrapper = await mountWith(twinFlag())

    const members = wrapper.findAll('.sf-member')
    expect(members.length).toBe(2)
    expect(members[0].find('.sf-member-pos').text()).toBe('YouTube')
    expect(members[1].find('.sf-member-pos').text()).toBe('TrackID')
    expect(wrapper.text()).not.toContain('p. 1')

    expect(members[0].find('.sf-member-meta').text()).toContain('Boiler Room')
    expect(members[0].find('.sf-member-meta').text()).toContain('60\u00A0min')
    expect(members[1].find('.sf-member-meta').text()).toContain('61\u00A0min')

    const link = members[0].find('a.sf-member-link')
    expect(link.text()).toBe('Ouvrir')
    expect(link.attributes('href')).toBe('https://www.youtube.com/watch?v=abc')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener noreferrer')

    expect(wrapper.find('.sf-card-conf').text()).toBe('Même date')
    expect(chips(wrapper)).toEqual(['Mots propres à chaque titre', 'écart durée 2\u00A0%'])
  })

  it('shows the publication date on the YouTube side only', async () => {
    const wrapper = await mountWith(twinFlag())
    const members = wrapper.findAll('.sf-member')
    expect(members[0].find('.sf-member-meta').text()).toContain('Publié le')
    expect(members[0].find('.sf-member-meta').text()).toContain('2026')
    expect(members[1].find('.sf-member-meta').text()).not.toContain('Publié le')
  })

  it.each([
    ['video', 'Même vidéo'],
    ['channel', 'Même chaîne'],
  ])('labels the %s step', async (step, label) => {
    const wrapper = await mountWith(twinFlag({}, { twin_rule: step }))
    expect(wrapper.find('.sf-card-conf').text()).toBe(label)
  })

  it.each([
    ['collaboration marker in one title only: ["b2b"]', "B2B d'un seul côté"],
    ['number in one title only: ["2"]', "Numéro d'un seul côté"],
    ['short title, the other has extra words', 'Titre court'],
    ['one-word title, close duration', "Titre d'un mot"],
    ['uploaded long after the event', 'Publié longtemps après'],
    ['each title has own words', 'Mots propres à chaque titre'],
    ['same date, each title has own words', 'Mots propres à chaque titre'],
    ['ambiguous: several candidates', 'Plusieurs candidats'],
    ['ambiguous: several youtube sets on one twin', 'Plusieurs vidéos sur ce set'],
    ['youtube set already in another family', 'Vidéo déjà rattachée ailleurs'],
    ['youtube set has too many channel candidates', 'Chaîne trop fournie'],
  ])('translates the reason « %s »', async (reason, label) => {
    const wrapper = await mountWith(twinFlag({}, { reason }))
    expect(chips(wrapper)[0]).toBe(label)
  })

  it('shows an unknown reason as is', async () => {
    const wrapper = await mountWith(twinFlag({}, { reason: 'brand new reason' }))
    expect(chips(wrapper)[0]).toBe('brand new reason')
  })

  it('hides the link when source_url is absent or not a web link', async () => {
    const wrapper = await mountWith(
      twinFlag({ source_url_a: null, source_url_b: 'javascript:alert(1)' }),
    )
    expect(wrapper.find('a.sf-member-link').exists()).toBe(false)
  })

  it('shows no duration gap chip when dd is null, but keeps a gap of 0', async () => {
    let wrapper = await mountWith(twinFlag({}, { dd: null }))
    expect(chips(wrapper)).toEqual(['Mots propres à chaque titre'])
    wrapper = await mountWith(twinFlag({}, { dd: 0 }))
    expect(chips(wrapper)).toContain('écart durée 0\u00A0%')
  })

  it('leaves a classic pair flag unchanged, even with the new API fields', async () => {
    const wrapper = await mountWith(
      twinFlag(
        { confidence: 0.7 },
        { twin_rule: undefined, reason: 'ignored', dd: 0.5, date_gap_days: 3 },
      ),
    )
    const members = wrapper.findAll('.sf-member')
    expect(members[0].find('.sf-member-pos').text()).toBe('p. 1')
    expect(members[1].find('.sf-member-pos').text()).toBe('p. 2')
    expect(wrapper.find('.sf-member-meta').exists()).toBe(false)
    expect(wrapper.find('a.sf-member-link').exists()).toBe(false)
    expect(wrapper.find('.sf-member-body').exists()).toBe(false)
    expect(wrapper.find('.sf-card-conf').text()).toBe('confiance 70\u00A0%')
    expect(chips(wrapper)).toEqual(['écart 3 j'])
    expect(wrapper.text()).not.toContain('Boiler Room Official')
  })
})

describe('AdminSets — flags en attente : event_date (C13.e)', () => {
  it('renders an event_date chip next to a set title when present', async () => {
    // A pairwise pending flag: set A has an event_date, set B does not.
    apiMock.get.mockReset()
    apiMock.get.mockImplementation((url) => {
      if (url.startsWith('/api/admin/set-flags?status=pending')) {
        return Promise.resolve({
          data: {
            total: 1,
            items: [
              {
                id: 1,
                set_id_a: 100,
                set_id_b: 101,
                flag_type: 'duplicate_candidate',
                confidence: 0.7,
                signals: {},
                status: 'pending',
                created_at: '2026-09-01T00:00:00Z',
                title_a: 'Boiler Room Berlin',
                title_b: 'Boiler Room Berlin (reupload)',
                event_date_a: '2026-06-20',
                event_date_b: null,
                member_set_ids: null,
                member_titles: [],
                member_event_dates: [],
              },
            ],
          },
        })
      }
      return Promise.resolve({ data: { total: 0, items: [] } })
    })

    const wrapper = mount(AdminSets)
    await flushPromises()

    // Exactly one member carries a date → exactly one date chip renders.
    const dateChips = wrapper.findAll('.sf-member-date')
    expect(dateChips.length).toBe(1)
    // fmtDate → DD/MM/YYYY (fr-FR); assert the year survives regardless of TZ.
    expect(dateChips[0].text()).toContain('2026')
  })
})
