import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import BeatportPlayButton from '../../components/BeatportPlayButton.vue'
import { useBeatportOverlay } from '../../stores/beatportOverlay.js'

// The overlay store pauses the player on open — mock the audioPlayer boundary
// so the click path runs without the real audio machinery.
const { playerMock } = vi.hoisted(() => ({
  playerMock: { playing: false, toggle: vi.fn() },
}))
vi.mock('../../stores/audioPlayer.js', () => ({
  useAudioPlayer: () => playerMock,
}))

const TRACK = { catalog_id: 42, title: 'Higher State', artist: 'Josh Wink', beatport_id: 987 }

describe('BeatportPlayButton', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    playerMock.playing = false
    playerMock.toggle.mockReset()
  })

  it('carries the French tooltip/aria-label « Extrait Beatport »', () => {
    const wrapper = mount(BeatportPlayButton, { props: { track: TRACK } })
    const btn = wrapper.find('button')
    expect(btn.attributes('aria-label')).toBe('Extrait Beatport')
    expect(btn.attributes('title')).toBe('Extrait Beatport')
  })

  it('click opens the overlay store with the track', async () => {
    const wrapper = mount(BeatportPlayButton, { props: { track: TRACK } })
    await wrapper.find('button').trigger('click')
    const store = useBeatportOverlay()
    expect(store.visible).toBe(true)
    expect(store.track).toEqual({
      id: 42,
      title: 'Higher State',
      artist: 'Josh Wink',
      beatport_id: 987,
    })
  })

  it('click does not bubble to the parent (stretched NavCover guard)', async () => {
    const outer = vi.fn()
    const wrapper = mount({
      components: { BeatportPlayButton },
      template: '<div @click="outer"><BeatportPlayButton :track="track" /></div>',
      setup() {
        return { outer, track: TRACK }
      },
    })
    await wrapper.find('button').trigger('click')
    expect(outer).not.toHaveBeenCalled()
    expect(useBeatportOverlay().visible).toBe(true)
  })
})
