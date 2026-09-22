import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

// AdminCohort talks to /api/admin/cohort (list + PATCH override) and dispatches a
// Celery recompute polled through useTaskPoll — both mocked here (pattern:
// AdminEnrichmentActions.test.js). The component links to the artist fiche via
// <router-link> → RouterLinkStub registered through global.components.
const { apiMock, pollOpts } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
  pollOpts: { value: null },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))
vi.mock('../../composables/useTaskPoll.js', () => ({
  useTaskPoll: (_urlFn, opts) => {
    pollOpts.value = opts
    return { start: vi.fn() }
  },
}))

import AdminCohort from '../../components/admin/AdminCohort.vue'

function cohortItem(over = {}) {
  return {
    artist_id: 42,
    name: 'Schrotthagen',
    deezer_id: '123',
    tier: 1,
    computed_tier: 1,
    forced_tier: null,
    pinned: false,
    excluded: false,
    signals: { nb_lib: 5, nb_likes: 2, nb_sets_12m: 3, nb_catalog: 12, followed: false },
    last_checked_at: '2026-09-20T10:00:00Z',
    last_recomputed_at: '2026-09-21T05:45:00Z',
    ...over,
  }
}

const mountCohort = () =>
  mount(AdminCohort, { global: { components: { RouterLink: RouterLinkStub } } })

// Locate a <button> by its exact trimmed text (optionally scoped to a selector).
function btnByText(wrapper, text, scope) {
  const root = scope ? wrapper.find(scope) : wrapper
  return root.findAll('button').find((b) => b.text() === text)
}

describe('AdminCohort', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.patch.mockReset()
    apiMock.post.mockReset()
    pollOpts.value = null
    apiMock.get.mockResolvedValue({ data: { total: 1, items: [cohortItem()] } })
  })

  it('fetches the cohort on mount and renders a member row', async () => {
    const wrapper = mountCohort()
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/cohort', {
      params: { page: 1, page_size: 50 },
    })
    // Name links to the artist fiche, tier badge + signals render.
    const link = wrapper.findComponent(RouterLinkStub)
    expect(link.props('to')).toBe('/artist/42')
    expect(link.text()).toContain('Schrotthagen')
    expect(wrapper.text()).toContain('T1')
    const chips = wrapper.find('.at-chips')
    expect(chips.text()).toContain('lib')
    expect(chips.text()).toContain('12') // nb_catalog
  })

  it('pins a member with a PATCH and swaps the row in place', async () => {
    const wrapper = mountCohort()
    await flushPromises()

    apiMock.patch.mockResolvedValue({ data: cohortItem({ pinned: true }) })
    await btnByText(wrapper, 'Épingler').trigger('click')
    await flushPromises()

    expect(apiMock.patch).toHaveBeenCalledWith('/api/admin/cohort/42', { pinned: true })
    // The row now shows the "Désépingler" toggle and the pinned pill.
    expect(btnByText(wrapper, 'Désépingler')).toBeTruthy()
    expect(wrapper.text()).toContain('Épinglé')
  })

  it('excludes a member with a PATCH', async () => {
    const wrapper = mountCohort()
    await flushPromises()

    apiMock.patch.mockResolvedValue({ data: cohortItem({ excluded: true }) })
    await btnByText(wrapper, 'Exclure').trigger('click')
    await flushPromises()

    expect(apiMock.patch).toHaveBeenCalledWith('/api/admin/cohort/42', { excluded: true })
    expect(btnByText(wrapper, 'Réintégrer')).toBeTruthy()
    expect(wrapper.text()).toContain('Exclu')
  })

  it('forces a tier with a PATCH', async () => {
    const wrapper = mountCohort()
    await flushPromises()

    apiMock.patch.mockResolvedValue({ data: cohortItem({ forced_tier: 2, tier: 2 }) })
    // The force control is the scoped segmented group; its T2 button is distinct
    // from the header tier filter's T2.
    await btnByText(wrapper, 'T2', '.ch-force').trigger('click')
    await flushPromises()

    expect(apiMock.patch).toHaveBeenCalledWith('/api/admin/cohort/42', { forced_tier: 2 })
    expect(wrapper.text()).toContain('Forcé T2')
  })

  it('un-forces a tier via the Auto segment with an explicit null', async () => {
    // A forced row: the Auto segment un-forces it (PATCH forced_tier=null) and the
    // swapped-in row drops back to the computed tier with no "Forcé" pill.
    apiMock.get.mockResolvedValue({
      data: { total: 1, items: [cohortItem({ forced_tier: 2, tier: 2 })] },
    })
    const wrapper = mountCohort()
    await flushPromises()
    expect(wrapper.text()).toContain('Forcé T2')

    apiMock.patch.mockResolvedValue({ data: cohortItem({ forced_tier: null, tier: 1 }) })
    await btnByText(wrapper, 'Auto', '.ch-force').trigger('click')
    await flushPromises()

    expect(apiMock.patch).toHaveBeenCalledWith('/api/admin/cohort/42', { forced_tier: null })
    expect(wrapper.text()).not.toContain('Forcé T2')
    // Auto is now the active segment (no tier forced).
    expect(btnByText(wrapper, 'Auto', '.ch-force').classes()).toContain('active')
  })

  it('filters the list by tier with a re-fetch', async () => {
    const wrapper = mountCohort()
    await flushPromises()

    apiMock.get.mockClear()
    await btnByText(wrapper, 'T2', '.ch-filters').trigger('click')
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/cohort', {
      params: { page: 1, page_size: 50, tier: 2 },
    })
  })

  it('dispatches the recompute job and shows its result', async () => {
    apiMock.post.mockResolvedValue({ data: { status: 'queued', task_id: 'zzz' } })
    const wrapper = mountCohort()
    await flushPromises()

    await wrapper.find('.btn--accent').trigger('click')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/cohort/recompute')

    // Drive the poll to completion; the result pairs render.
    apiMock.get.mockClear()
    pollOpts.value.onData(
      {
        status: 'done',
        result: { n_total: 3400, n_t1: 3000, n_t2: 400, n_pinned: 13, n_excluded: 2, n_pruned: 5 },
      },
      { stop: vi.fn() },
    )
    await flushPromises()

    const result = wrapper.find('.ch-result')
    expect(result.text()).toContain('membres')
    expect(result.text()).toContain('T1')
    // A successful recompute refreshes the current page.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/cohort', {
      params: { page: 1, page_size: 50 },
    })
  })

  it('shows the already-running notice when the recompute is skipped', async () => {
    apiMock.post.mockResolvedValue({ data: { status: 'queued', task_id: 'zzz' } })
    const wrapper = mountCohort()
    await flushPromises()

    await wrapper.find('.btn--accent').trigger('click')
    await flushPromises()

    pollOpts.value.onData(
      { status: 'done', result: { skipped: 'already_running', holder: 'abc' } },
      { stop: vi.fn() },
    )
    await flushPromises()

    expect(wrapper.find('.ch-skip').exists()).toBe(true)
  })
})
