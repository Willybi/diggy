import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
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

// Mock Audio
class AudioMock {
  constructor() {
    this.volume = 1
    this.muted = false
    this.currentTime = 0
    this.paused = true
    this.src = ''
  }
  play() {
    this.paused = false
    return Promise.resolve()
  }
  pause() {
    this.paused = true
  }
  addEventListener() {}
}
globalThis.Audio = AudioMock

// Mock api
vi.mock('../../utils/api.js', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: { preview_url: 'https://example.com/preview.mp3' } })),
  },
}))

describe('audioPlayer store', () => {
  beforeEach(() => {
    Object.keys(storage).forEach((k) => delete storage[k])
    setActivePinia(createPinia())
    // Fresh api.get per test with a default 200; individual tests queue overrides.
    api.get.mockReset()
    api.get.mockResolvedValue({ data: { preview_url: 'https://example.com/preview.mp3' } })
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
})
