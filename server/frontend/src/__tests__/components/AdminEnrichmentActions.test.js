import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { apiMock, pollOpts } = vi.hoisted(() => ({
  apiMock: { post: vi.fn() },
  pollOpts: { value: null },
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))
vi.mock('../../composables/useTaskPoll.js', () => ({
  useTaskPoll: (_urlFn, opts) => {
    pollOpts.value = opts
    return { start: vi.fn() }
  },
}))

import AdminEnrichmentActions from '../../components/admin/AdminEnrichmentActions.vue'

describe('AdminEnrichmentActions', () => {
  beforeEach(() => {
    apiMock.post.mockReset()
    pollOpts.value = null
  })

  it('starts the backfill job on click', async () => {
    apiMock.post.mockResolvedValue({ data: { task_id: 'xyz' } })
    const wrapper = mount(AdminEnrichmentActions)

    await wrapper.find('.btn-sync').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/artists/backfill-multi-artists')

    // drive the poll to completion
    pollOpts.value.onData(
      { status: 'done', result: { enriched: 3, errors: 0, total: 10 } },
      { stop: vi.fn() },
    )
    await flushPromises()
    expect(wrapper.find('.sync-result').text()).toContain('3 enrichis')
  })

  it('does NOT POST reset on the first click, only after confirmation', async () => {
    apiMock.post.mockResolvedValue({
      data: { status: 'reset', cleared: 5, bpm_reverted: 2, key_reverted: 1 },
    })
    const wrapper = mount(AdminEnrichmentActions)

    // First click only reveals the confirmation zone.
    await wrapper.find('.btn-danger').trigger('click')
    await flushPromises()
    expect(apiMock.post).not.toHaveBeenCalled()
    expect(wrapper.find('.confirm-zone').exists()).toBe(true)

    // Confirm → the actual POST fires.
    const confirmBtn = wrapper.findAll('.confirm-actions .btn-danger').at(0)
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/reset-beatport')
    expect(wrapper.find('.sync-result').text()).toContain('5 réinitialisés')
  })

  it('cancels the reset confirmation without POSTing', async () => {
    const wrapper = mount(AdminEnrichmentActions)

    await wrapper.find('.btn-danger').trigger('click')
    await flushPromises()
    await wrapper.find('.btn-cancel').trigger('click')
    await flushPromises()

    expect(apiMock.post).not.toHaveBeenCalled()
    expect(wrapper.find('.confirm-zone').exists()).toBe(false)
  })
})
