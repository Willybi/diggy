import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Capture the useTaskPoll options so we can drive onData() by hand, and mock the
// API so the "Enrich" click resolves to a task id.
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

import AdminBeatport from '../../components/admin/AdminBeatport.vue'

async function startRun(wrapper) {
  await wrapper.find('.btn-sync').trigger('click')
  await flushPromises()
}

describe('AdminBeatport skip-lock', () => {
  beforeEach(() => {
    apiMock.post.mockReset()
    apiMock.post.mockResolvedValue({ data: { task_id: 'abc' } })
    pollOpts.value = null
  })

  it('shows « déjà en cours » when the sweep is already running (skip result)', async () => {
    const wrapper = mount(AdminBeatport)
    await startRun(wrapper)

    // Lock held upstream → task returns {skipped} with no counters (holder can be null).
    pollOpts.value.onData(
      { status: 'done', result: { skipped: 'already_running', holder: null } },
      { stop: vi.fn() },
    )
    await flushPromises()

    const info = wrapper.find('.sync-info')
    expect(info.exists()).toBe(true)
    expect(info.text()).toContain('déjà en cours')
    // No blank counters row.
    expect(wrapper.find('.sync-result').exists()).toBe(false)
  })

  it('shows the counters on a normal completion', async () => {
    const wrapper = mount(AdminBeatport)
    await startRun(wrapper)

    pollOpts.value.onData(
      { status: 'done', result: { enriched: 4, not_found: 1, errors: 0, total: 5 } },
      { stop: vi.fn() },
    )
    await flushPromises()

    const result = wrapper.find('.sync-result')
    expect(result.exists()).toBe(true)
    expect(result.text()).toContain('4 enrichis')
    expect(wrapper.find('.sync-info').exists()).toBe(false)
  })
})
