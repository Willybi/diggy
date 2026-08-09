import { describe, it, expect, vi } from 'vitest'
import { ref, reactive, nextTick, effectScope } from 'vue'
import { useUrlSync } from '../../composables/useUrlSync.js'

// A route/router pair where router.replace round-trips the new query back onto
// the reactive route — the browser behaviour useUrlSync relies on.
function setup(query = {}) {
  const route = reactive({ query })
  const replace = vi.fn((arg) => {
    route.query = arg.query
  })
  const sort = ref('tracks')
  const fam = ref('all')
  useUrlSync(
    [
      { ref: sort, param: 'sort', default: 'tracks' },
      { ref: fam, param: 'fam', default: 'all' },
    ],
    { router: { replace }, route },
  )
  return { route, replace, sort, fam }
}

describe('useUrlSync', () => {
  it('hydrates refs from the URL on setup', () => {
    const { sort, fam } = setup({ sort: 'alpha', fam: 'house' })
    expect(sort.value).toBe('alpha')
    expect(fam.value).toBe('house')
  })

  it('writes non-default values to the URL and omits defaults', async () => {
    const { replace, sort, fam } = setup()

    sort.value = 'alpha'
    await nextTick()
    expect(replace).toHaveBeenCalledWith({ query: { sort: 'alpha' } }) // fam default omitted

    fam.value = 'techno'
    await nextTick()
    expect(replace).toHaveBeenLastCalledWith({ query: { sort: 'alpha', fam: 'techno' } })
  })

  it('drops a param once its ref returns to the default value', async () => {
    const { replace, sort } = setup({ sort: 'alpha' })

    sort.value = 'tracks'
    await nextTick()
    expect(replace).toHaveBeenCalledWith({ query: {} })
  })

  it('re-applies the URL into the refs on back/forward (query reset)', async () => {
    const { route, sort } = setup({ sort: 'alpha' })
    expect(sort.value).toBe('alpha')

    route.query = {} // browser back to the default entry
    await nextTick()
    expect(sort.value).toBe('tracks')
  })

  it('clears a pending debounced write on scope disposal (no leak onto the next route)', async () => {
    vi.useFakeTimers()
    try {
      const route = reactive({ query: {} })
      const replace = vi.fn((arg) => {
        route.query = arg.query
      })
      const q = ref('')
      const scope = effectScope()
      scope.run(() => {
        useUrlSync([{ ref: q, param: 'q', default: '', debounce: true }], {
          router: { replace },
          route,
          debounceMs: 300,
        })
      })

      q.value = 'house' // arm the debounced timer
      await nextTick() // let the watcher schedule the setTimeout
      expect(replace).not.toHaveBeenCalled() // still inside the debounce window

      scope.stop() // component unmounts before the timer fires
      vi.advanceTimersByTime(400) // past debounceMs

      expect(replace).not.toHaveBeenCalled() // timer was cleared, no stale write
    } finally {
      vi.useRealTimers()
    }
  })
})
