import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useBeatportBar } from '../../stores/beatportBar.js'

// The store only consumes the audioPlayer PUBLIC api (playing + toggle):
// a plain mock keeps the test at that boundary.
const { playerMock } = vi.hoisted(() => ({
  playerMock: { playing: false, toggle: vi.fn() },
}))
vi.mock('../../stores/audioPlayer.js', () => ({
  useAudioPlayer: () => playerMock,
}))

const TRACK = { catalog_id: 42, title: 'Higher State', artist: 'Josh Wink', beatport_id: 987 }

describe('beatportBar store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    playerMock.playing = false
    playerMock.toggle.mockReset()
  })

  it('starts closed (track null, visible false)', () => {
    const bar = useBeatportBar()
    expect(bar.track).toBeNull()
    expect(bar.visible).toBe(false)
  })

  it('open() stores the track and shows the bar', () => {
    const bar = useBeatportBar()
    bar.open(TRACK)
    expect(bar.visible).toBe(true)
    expect(bar.track).toEqual({
      id: 42,
      title: 'Higher State',
      artist: 'Josh Wink',
      beatport_id: 987,
    })
  })

  it('open() falls back to `id` when the row has no catalog_id', () => {
    const bar = useBeatportBar()
    bar.open({ id: 7, title: 'T', artist: 'A', beatport_id: 1 })
    expect(bar.track.id).toBe(7)
  })

  it('open() pauses the Deezer player when it is playing', () => {
    playerMock.playing = true
    const bar = useBeatportBar()
    bar.open(TRACK)
    expect(playerMock.toggle).toHaveBeenCalledTimes(1)
  })

  it('open() leaves the player untouched when it is not playing', () => {
    const bar = useBeatportBar()
    bar.open(TRACK)
    expect(playerMock.toggle).not.toHaveBeenCalled()
  })

  it('open() on another track replaces the current one', () => {
    const bar = useBeatportBar()
    bar.open(TRACK)
    bar.open({ catalog_id: 43, title: 'Flash', artist: 'Green Velvet', beatport_id: 654 })
    expect(bar.track).toEqual({
      id: 43,
      title: 'Flash',
      artist: 'Green Velvet',
      beatport_id: 654,
    })
  })

  it('close() resets the track and hides the bar', () => {
    const bar = useBeatportBar()
    bar.open(TRACK)
    bar.close()
    expect(bar.track).toBeNull()
    expect(bar.visible).toBe(false)
  })
})
