import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useBeatportOverlay } from '../../stores/beatportOverlay.js'

// The store only consumes the audioPlayer PUBLIC api (playing + toggle):
// a plain mock keeps the test at that boundary.
const { playerMock } = vi.hoisted(() => ({
  playerMock: { playing: false, toggle: vi.fn() },
}))
vi.mock('../../stores/audioPlayer.js', () => ({
  useAudioPlayer: () => playerMock,
}))

const TRACK = { catalog_id: 42, title: 'Higher State', artist: 'Josh Wink', beatport_id: 987 }

describe('beatportOverlay store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    playerMock.playing = false
    playerMock.toggle.mockReset()
  })

  it('starts closed (track null, visible false)', () => {
    const overlay = useBeatportOverlay()
    expect(overlay.track).toBeNull()
    expect(overlay.visible).toBe(false)
  })

  it('open() stores the track and shows the overlay', () => {
    const overlay = useBeatportOverlay()
    overlay.open(TRACK)
    expect(overlay.visible).toBe(true)
    expect(overlay.track).toEqual({
      id: 42,
      title: 'Higher State',
      artist: 'Josh Wink',
      beatport_id: 987,
    })
  })

  it('open() falls back to `id` when the row has no catalog_id', () => {
    const overlay = useBeatportOverlay()
    overlay.open({ id: 7, title: 'T', artist: 'A', beatport_id: 1 })
    expect(overlay.track.id).toBe(7)
  })

  it('open() pauses the Deezer player when it is playing', () => {
    playerMock.playing = true
    const overlay = useBeatportOverlay()
    overlay.open(TRACK)
    expect(playerMock.toggle).toHaveBeenCalledTimes(1)
  })

  it('open() leaves the player untouched when it is not playing', () => {
    const overlay = useBeatportOverlay()
    overlay.open(TRACK)
    expect(playerMock.toggle).not.toHaveBeenCalled()
  })

  it('close() resets the track and hides the overlay', () => {
    const overlay = useBeatportOverlay()
    overlay.open(TRACK)
    overlay.close()
    expect(overlay.track).toBeNull()
    expect(overlay.visible).toBe(false)
  })
})
