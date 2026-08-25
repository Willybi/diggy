import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn() },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))

import AdminAuditLog from '../../components/admin/AdminAuditLog.vue'

const PAGE1 = {
  total: 25,
  items: [
    {
      id: 2,
      user_id: 7,
      user_email: 'admin@diggy.fr',
      action: 'reset_beatport',
      target_type: null,
      target_id: null,
      details: { cleared: 42 },
      created_at: '2026-08-24T10:15:00Z',
    },
    {
      id: 1,
      user_id: null,
      user_email: null,
      action: 'resolve_flag',
      target_type: 'set',
      target_id: 99,
      details: null,
      created_at: '2026-08-24T09:00:00Z',
    },
  ],
}

describe('AdminAuditLog', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.get.mockResolvedValue({ data: PAGE1 })
  })

  it('renders the rows of a mocked response', async () => {
    const wrapper = mount(AdminAuditLog)
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('reset_beatport')
    expect(wrapper.text()).toContain('admin@diggy.fr')
    // author fallback for a null email
    expect(wrapper.text()).toContain('—')
    // target rendered as type #id
    expect(wrapper.text()).toContain('set #99')
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/audit-log', {
      params: { page: 1, per_page: 20 },
    })
  })

  it('paginates to the next page', async () => {
    const wrapper = mount(AdminAuditLog)
    await flushPromises()

    // total 25 / 20 per page → 2 pages, Next enabled
    const nextBtn = wrapper.findAll('.crawl-pagination button').at(1)
    await nextBtn.trigger('click')
    await flushPromises()

    expect(apiMock.get).toHaveBeenLastCalledWith('/api/admin/audit-log', {
      params: { page: 2, per_page: 20 },
    })
  })
})
