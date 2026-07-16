import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TrackCard from '../../components/TrackCard.vue'

const baseTrack = {
  id: 42,
  title: 'Strobe',
  artist: 'deadmau5',
  bpm: 128,
  key: '9A',
  has_artwork: true,
  has_preview: true,
  in_lib: true,
}

function makeTrack(overrides = {}) {
  return { ...baseTrack, ...overrides }
}

describe('TrackCard', () => {
  it('renders title, rounded bpm and key', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack({ bpm: 127.6 }) } })
    expect(wrapper.find('.tk-title').text()).toBe('Strobe')
    expect(wrapper.find('.tk-bpm').text()).toBe('128') // fmtBpm rounds
    expect(wrapper.find('.tk-key').text()).toBe('9A')
  })

  it('hides the artist by default and shows it when showArtist is true', () => {
    const hidden = mount(TrackCard, { props: { track: makeTrack() } })
    expect(hidden.find('.tk-artist').exists()).toBe(false)

    const shown = mount(TrackCard, { props: { track: makeTrack(), showArtist: true } })
    expect(shown.find('.tk-artist').text()).toBe('deadmau5')
  })

  it('emits play when the play button is clicked (has_preview)', async () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack() } })
    const play = wrapper.find('.tk-play')
    expect(play.exists()).toBe(true)
    await play.trigger('click')
    expect(wrapper.emitted('play')).toHaveLength(1)
  })

  it('renders no play button and never emits play when has_preview is false', async () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack({ has_preview: false }) } })
    expect(wrapper.find('.tk-play').exists()).toBe(false)
    expect(wrapper.emitted('play')).toBeFalsy()
  })

  it('applies the playing state class', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack(), playing: true } })
    expect(wrapper.find('.track-card').classes()).toContain('playing')
  })

  it('renders the end slot and flags the grid with has-end', () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack() },
      slots: { end: '<div class="probe">END</div>' },
    })
    expect(wrapper.find('.tk-end .probe').exists()).toBe(true)
    expect(wrapper.find('.track-card').classes()).toContain('has-end')
  })

  it('has no end column when the slot is unused', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack() } })
    expect(wrapper.find('.tk-end').exists()).toBe(false)
    expect(wrapper.find('.track-card').classes()).not.toContain('has-end')
  })
})
