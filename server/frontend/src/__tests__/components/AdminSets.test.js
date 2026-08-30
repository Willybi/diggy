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

function getResponder(url) {
  if (url === '/api/admin/set-flags?status=pending&limit=50') {
    return Promise.resolve({ data: { total: 0, items: [] } })
  }
  if (url === '/api/admin/set-flags?status=attached&limit=50') {
    return Promise.resolve({
      data: {
        total: 2,
        items: [
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
        ],
      },
    })
  }
  return Promise.resolve({ data: { total: 0, items: [] } })
}

describe('AdminSets — section « Sets attachés »', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.get.mockImplementation(getResponder)
    apiMock.post.mockResolvedValue({ data: { ok: true } })
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

  it('POSTs the detach endpoint and removes the row on success', async () => {
    const wrapper = mount(AdminSets)
    await flushPromises()

    const firstRow = wrapper.findAll('.attached-set')[0]
    await firstRow.find('button').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/sets/100/detach')
    // The detached set is gone; the sibling set of the pair remains.
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

    // Same pattern as attach/reject: a section-level error line is shown.
    // D11 reskin renamed the legacy `.sync-error` line to `.sf-state--err`.
    expect(wrapper.find('.sf-state--err').text()).toContain('Boom')
  })
})
