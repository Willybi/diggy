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

    // D11 reskin: the backfill trigger is the accent job button (.btn--accent).
    await wrapper.find('.btn--accent').trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/artists/backfill-multi-artists')

    // drive the poll to completion
    pollOpts.value.onData(
      { status: 'done', result: { enriched: 3, errors: 0, total: 10 } },
      { stop: vi.fn() },
    )
    await flushPromises()
    // Counters render as icon/number/label pairs (.aj-result); the number and
    // label sit in adjacent spans, so .text() has no space between them.
    const result = wrapper.find('.aj-result')
    expect(result.text()).toContain('3')
    expect(result.text()).toContain('enrichis')
  })

  it('does NOT POST reset on the first click, only after confirmation', async () => {
    apiMock.post.mockResolvedValue({
      data: { status: 'reset', cleared: 5, bpm_reverted: 2, key_reverted: 1 },
    })
    const wrapper = mount(AdminEnrichmentActions)

    // D11 reskin: the danger button (.btn--danger) is the reset trigger; before
    // confirmation it's the only .btn--danger on screen. First click only reveals
    // the inline confirmation zone (.aj-confirm).
    await wrapper.find('.btn--danger').trigger('click')
    await flushPromises()
    expect(apiMock.post).not.toHaveBeenCalled()
    expect(wrapper.find('.aj-confirm').exists()).toBe(true)

    // Confirm → the trigger is hidden, the confirm .btn--danger fires the POST.
    const confirmBtn = wrapper.find('.aj-confirm-actions .btn--danger')
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/api/admin/reset-beatport')
    // Neutral result pairs (D6): number and label in adjacent spans.
    const result = wrapper.find('.aj-result')
    expect(result.text()).toContain('5')
    expect(result.text()).toContain('réinitialisés')
  })

  it('cancels the reset confirmation without POSTing', async () => {
    const wrapper = mount(AdminEnrichmentActions)

    await wrapper.find('.btn--danger').trigger('click')
    await flushPromises()
    // Cancel is the neutral first button of the confirmation actions.
    await wrapper.find('.aj-confirm-actions .btn:not(.btn--danger)').trigger('click')
    await flushPromises()

    expect(apiMock.post).not.toHaveBeenCalled()
    expect(wrapper.find('.aj-confirm').exists()).toBe(false)
  })
})
