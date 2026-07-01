import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAudioPlayer } from '../../stores/audioPlayer.js'

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
})
