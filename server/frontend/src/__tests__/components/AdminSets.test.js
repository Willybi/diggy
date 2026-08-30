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
