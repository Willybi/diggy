import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useAudioPlayer } from '../../stores/audioPlayer.js'
import { useToast } from '../../stores/toast.js'
import api from '../../utils/api.js'

// Mock localStorage
const storage = {}
const localStorageMock = {
  getItem: vi.fn((key) => storage[key] ?? null),
  setItem: vi.fn((key, val) => {
    storage[key] = String(val)
  }),
  removeItem: vi.fn((key) => {
    delete storage[key]
  }),
}
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// Mock Audio — records listeners so tests can fire `ended` (auto-advance).
let lastAudio = null
class AudioMock {
  constructor() {
    this.volume = 1
    this.muted = false
    this.currentTime = 0
    this.paused = true
    this.src = ''
    this.listeners = {}
    lastAudio = this
  }
  play() {
    this.paused = false
    return Promise.resolve()
  }
  pause() {
    this.paused = true
  }
  addEventListener(type, fn) {
    ;(this.listeners[type] ||= []).push(fn)
  }
  fire(type) {
    ;(this.listeners[type] || []).forEach((fn) => fn())
  }
}
globalThis.Audio = AudioMock

// Mock api
vi.mock('../../utils/api.js', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: { preview_url: 'https://example.com/preview.mp3' } })),
    patch: vi.fn(() => Promise.resolve({ data: {} })),
  },
}))

describe('audioPlayer store', () => {
  beforeEach(() => {
    Object.keys(storage).forEach((k) => delete storage[k])
    setActivePinia(createPinia())
    lastAudio = null
    // Fresh api mocks per test with a default 200; individual tests queue overrides.
    api.get.mockReset()
    api.get.mockResolvedValue({ data: { preview_url: 'https://example.com/preview.mp3' } })
    api.patch.mockReset()
    api.patch.mockResolvedValue({ data: {} })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initial state: track null, playing false, visible false', () => {
    const player = useAudioPlayer()
    expect(player.track).toBeNull()
    expect(player.playing).toBe(false)
    expect(player.visible).toBe(false)
  })

  it('isCurrent returns true/false based on loaded track', () => {
    const player = useAudioPlayer()
    expect(player.isCurrent(42)).toBe(false)
    player.track = { catalog_id: 42, title: 'Test', artist: 'A' }
    expect(player.isCurrent(42)).toBe(true)
    expect(player.isCurrent(99)).toBe(false)
  })

  it('close() resets everything', async () => {
    const player = useAudioPlayer()
    player.track = { catalog_id: 1, title: 'T', artist: 'A' }
    player.playing = true
    player.loading = true

    player.close()
    expect(player.track).toBeNull()
    expect(player.playing).toBe(false)
    expect(player.loading).toBe(false)
  })

  it('setVolume updates volume and persists to localStorage', () => {
    const player = useAudioPlayer()
    player.setVolume(0.5)
    expect(player.volume).toBe(0.5)
    expect(localStorageMock.setItem).toHaveBeenCalledWith('diggy:volume', 0.5)
  })

  it('toggleMute inverts the muted state', () => {
    const player = useAudioPlayer()
    expect(player.muted).toBe(false)
    player.toggleMute()
    expect(player.muted).toBe(true)
    player.toggleMute()
    expect(player.muted).toBe(false)
  })

  it('play() requests the preview with the toast suppressed and starts playback', async () => {
    const player = useAudioPlayer()
    await player.play({ id: 3, catalog_id: 3, title: 'T', artist: 'A' })
    expect(api.get).toHaveBeenCalledWith('/api/catalog/3/preview-url', {
      suppressErrorToast: true,
    })
    expect(player.track?.catalog_id).toBe(3)
    expect(player.loading).toBe(false)
  })

  it('retries once on a transient 503, then plays on recovery', async () => {
    vi.useFakeTimers()
    const player = useAudioPlayer()
    api.get
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ data: { preview_url: 'https://x/p.mp3' } })

    const p = player.play({ catalog_id: 7 })
    await vi.advanceTimersByTimeAsync(800) // let the backoff + retry fire
    await p

    expect(api.get).toHaveBeenCalledTimes(2) // initial + one retry
    expect(player.track?.catalog_id).toBe(7)
    expect(player.loading).toBe(false)
  })

  it('closes and toasts (temporary) once 503 retries are exhausted', async () => {
    vi.useFakeTimers()
    const player = useAudioPlayer()
    const toast = useToast()
    const showSpy = vi.spyOn(toast, 'show')
    api.get.mockRejectedValue({ response: { status: 503 } })

    const p = player.play({ catalog_id: 9 })
    await vi.advanceTimersByTimeAsync(800)
    await p

    expect(api.get).toHaveBeenCalledTimes(2) // initial + one retry, then give up
    expect(player.track).toBeNull() // player closed
    expect(showSpy).toHaveBeenCalledWith('Preview temporairement indisponible, réessayez.')
  })

  it('closes immediately on a 404 without retrying', async () => {
    const player = useAudioPlayer()
    const toast = useToast()
    const showSpy = vi.spyOn(toast, 'show')
    api.get.mockRejectedValue({ response: { status: 404 } })

    await player.play({ catalog_id: 11 })

    expect(api.get).toHaveBeenCalledTimes(1) // genuine absence: no retry
    expect(player.track).toBeNull()
    expect(showSpy).not.toHaveBeenCalled() // silent, like a missing preview
  })

  it('adopts the avis returned by the preview endpoint (authoritative over the row)', async () => {
    const player = useAudioPlayer()
    api.get.mockResolvedValue({ data: { preview_url: 'https://x/p.mp3', avis: 'liked' } })

    await player.play({ catalog_id: 3, avis: null })

    expect(player.track.avis).toBe('liked')
  })
})

describe('audioPlayer queue / auto-advance', () => {
  const t = (id, extra = {}) => ({ id, catalog_id: id, title: `T${id}`, artist: 'A', ...extra })
  const listOf = (items, extra = {}) => ({ type: 'list', getItems: () => items, ...extra })

  beforeEach(() => {
    setActivePinia(createPinia())
    lastAudio = null
    api.get.mockReset()
    api.get.mockResolvedValue({ data: { preview_url: 'https://example.com/preview.mp3' } })
    api.patch.mockReset()
    api.patch.mockResolvedValue({ data: {} })
  })

  // Neutralise any in-flight fire-and-forget auto-advance chain so it can't
  // spill promises onto the next test file in the same vitest worker: close()
  // nulls source/track, making a surviving playNext() return immediately.
  afterEach(() => {
    useAudioPlayer().close()
    vi.useRealTimers()
  })

  it('single-shot play (no source): ended just stops', async () => {
    const player = useAudioPlayer()
    await player.play(t(1))
    expect(player.canNext).toBe(false)

    lastAudio.fire('ended')
    await Promise.resolve()

    expect(player.track.catalog_id).toBe(1) // no advance
  })

  it('list source: ended advances to the next displayed track', async () => {
    const player = useAudioPlayer()
    const items = [t(1), t(2), t(3)]
    await player.play(items[0], listOf(items))
    expect(player.canNext).toBe(true)

    lastAudio.fire('ended')
    await vi.waitFor(() => expect(player.track?.catalog_id).toBe(2))
  })

  it('list source: skips tracks without preview', async () => {
    const player = useAudioPlayer()
    const items = [t(1), t(2, { has_preview: false }), t(3)]
    await player.play(items[0], listOf(items))

    await player.playNext()

    expect(player.track.catalog_id).toBe(3)
  })

  it('list source: pulls the next page when the loaded window runs out', async () => {
    const player = useAudioPlayer()
    const items = [t(1)]
    const loadMore = vi.fn(() => {
      items.push(t(2))
      return Promise.resolve()
    })
    await player.play(items[0], listOf(items, { loadMore }))

    await player.playNext()

    expect(loadMore).toHaveBeenCalledTimes(1)
    expect(player.track.catalog_id).toBe(2)
  })

  it('list source: true end (loadMore makes no progress) → simple stop', async () => {
    const player = useAudioPlayer()
    const items = [t(1), t(2)]
    const loadMore = vi.fn(() => Promise.resolve())
    await player.play(items[1], listOf(items, { loadMore }))

    await player.playNext()

    expect(loadMore).toHaveBeenCalledTimes(1) // one attempt, no growth → stop
    expect(player.track.catalog_id).toBe(2) // bar stays on the last track
  })

  it('setAvis(disliked) PATCHes, syncs the origin row and skips immediately', async () => {
    const player = useAudioPlayer()
    const onAvis = vi.fn()
    const items = [t(1), t(2)]
    await player.play(items[0], listOf(items, { onAvis }))

    await player.setAvis('disliked')
    await vi.waitFor(() => expect(player.track?.catalog_id).toBe(2))

    expect(api.patch).toHaveBeenCalledWith('/api/catalog/1/avis', { avis: 'disliked' })
    expect(onAvis).toHaveBeenCalledWith(1, 'disliked')
  })

  it('setAvis(liked) keeps playing the current track', async () => {
    const player = useAudioPlayer()
    const items = [t(1), t(2)]
    await player.play(items[0], listOf(items))

    await player.setAvis('liked')

    expect(player.track.catalog_id).toBe(1)
    expect(player.track.avis).toBe('liked')
  })

  it('setAvis rolls back bar + row when the PATCH fails', async () => {
    const player = useAudioPlayer()
    const onAvis = vi.fn()
    api.patch.mockRejectedValue(new Error('boom'))
    await player.play(t(1, { avis: null }), listOf([t(1)], { onAvis }))

    await player.setAvis('liked')

    expect(player.track.avis).toBeNull()
    expect(onAvis).toHaveBeenNthCalledWith(1, 1, 'liked')
    expect(onAvis).toHaveBeenNthCalledWith(2, 1, null)
  })

  it('syncAvis updates the bar only for the currently playing track', async () => {
    const player = useAudioPlayer()
    await player.play(t(1))

    player.syncAvis(1, 'liked')
    expect(player.track.avis).toBe('liked')
    player.syncAvis(99, 'disliked')
    expect(player.track.avis).toBe('liked')
  })

  it('random genre source: ended re-rolls excluding the finished track', async () => {
    const player = useAudioPlayer()
    let rolls = 0
    api.get.mockImplementation((url) => {
      if (url.includes('random-track')) {
        rolls++
        return Promise.resolve({
          data: { catalog_id: rolls * 10, title: `R${rolls}`, artist: 'A' },
        })
      }
      return Promise.resolve({ data: { preview_url: 'https://x/p.mp3' } })
    })

    await player.playRandom('techno')
    expect(player.genrePlaying).toBe('techno')
    expect(player.track.catalog_id).toBe(10)

    lastAudio.fire('ended')
    await vi.waitFor(() => expect(player.track?.catalog_id).toBe(20))
    expect(player.genrePlaying).toBe('techno') // still the same session
    const secondRoll = api.get.mock.calls.filter(([u]) => u.includes('random-track'))[1]
    expect(secondRoll[1].params.exclude).toBe(10)
  })

  it('list source: a dead preview (404) advances to the next track instead of closing', async () => {
    const player = useAudioPlayer()
    const items = [t(1), t(2)]
    // track 1's preview is dead (404), track 2's is fine.
    api.get.mockImplementation((url) =>
      url === '/api/catalog/1/preview-url'
        ? Promise.reject({ response: { status: 404 } })
        : Promise.resolve({ data: { preview_url: 'https://x/p.mp3' } }),
    )

    await player.play(items[0], listOf(items))
    await vi.waitFor(() => expect(player.track?.catalog_id).toBe(2))
    await flushPromises() // drain the in-flight advance so nothing outlives the test

    expect(player.canNext).toBe(true) // the session survived the dead preview
  })

  it('list source: an all-dead queue stops within the dead-preview bound (no infinite loop)', async () => {
    const player = useAudioPlayer()
    const items = Array.from({ length: 10 }, (_, i) => t(i + 1))
    api.get.mockRejectedValue({ response: { status: 404 } }) // every preview dead

    await player.play(items[0], listOf(items))
    // The bounded advance chain ends by closing the session (track → null).
    await vi.waitFor(() => expect(player.track).toBeNull()) // gave up cleanly
    await flushPromises() // drain any residual advance so nothing outlives the test

    const previewCalls = api.get.mock.calls.filter(([u]) => u.includes('preview-url'))
    // Bounded: 1 initial load + at most DEAD_PREVIEW_MAX (5) advances = ≤ 6,
    // and strictly fewer than exhausting the whole 10-track list.
    expect(previewCalls.length).toBeLessThanOrEqual(6)
    expect(previewCalls.length).toBeLessThan(10)
  })

  it('close() drops the source (no ghost auto-advance)', async () => {
    const player = useAudioPlayer()
    await player.play(t(1), listOf([t(1), t(2)]))
    expect(player.canNext).toBe(true)

    player.close()

    expect(player.canNext).toBe(false)
  })
})
