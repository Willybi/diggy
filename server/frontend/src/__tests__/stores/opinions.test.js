import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useOpinionsStore } from '../../stores/opinions.js'

vi.mock('../../utils/api.js', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    patch: vi.fn(() => Promise.resolve({ data: {} })),
  },
}))

describe('opinions store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('get() returns null when nothing is set', () => {
    const store = useOpinionsStore()
    expect(store.get('artist', '42')).toBeNull()
  })

  it('get() returns value after set()', async () => {
    const store = useOpinionsStore()
    await store.set('artist', '42', 'liked')
    expect(store.get('artist', '42')).toBe('liked')
  })

  it('set() performs optimistic update in data', async () => {
    const store = useOpinionsStore()
    const promise = store.set('set', '10', 'disliked')
    // Optimistic: available immediately before await
    expect(store.get('set', '10')).toBe('disliked')
    await promise
  })

  it('reset() clears all data and resets loaded', async () => {
    const store = useOpinionsStore()
    await store.set('artist', '1', 'liked')
    expect(store.get('artist', '1')).toBe('liked')

    store.reset()
    expect(store.get('artist', '1')).toBeNull()
    expect(Object.keys(store.data).length).toBe(0)
  })
})
