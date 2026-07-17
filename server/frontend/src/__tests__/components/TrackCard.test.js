import { describe, it, expect, vi } from 'vitest'
import { mount, config, RouterLinkStub } from '@vue/test-utils'
import TrackCard from '../../components/TrackCard.vue'

// TrackCard now uses <RouterLink> for clickable artists. vue-router isn't installed
// here, so the component would warn on every render (Vue hoists the resolveComponent
// call, even for the string-fallback branch). Register the stub file-wide — VTU
// `stubs` would be a no-op for an unresolved component (see CLAUDE.md pitfall).
config.global.components = { ...config.global.components, RouterLink: RouterLinkStub }

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

  // --- Extension: optional duration column (showDuration) ---

  it('renders no duration column by default even when duration_ms is present', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack({ duration_ms: 200000 }) } })
    expect(wrapper.find('.tk-dur').exists()).toBe(false)
    expect(wrapper.find('.track-card').classes()).not.toContain('has-duration')
  })

  it('renders the duration as m:ss when showDuration is true', () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack({ duration_ms: 200000 }), showDuration: true },
    })
    const dur = wrapper.find('.tk-dur')
    expect(dur.text()).toBe('3:20')
    expect(dur.classes()).not.toContain('tk-dur--empty')
    expect(wrapper.find('.track-card').classes()).toContain('has-duration')
  })

  it('renders a dimmed em dash when duration_ms is null', () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack({ duration_ms: null }), showDuration: true },
    })
    const dur = wrapper.find('.tk-dur')
    expect(dur.text()).toBe('—')
    expect(dur.classes()).toContain('tk-dur--empty')
  })

  it('formats durations of one hour or more as h:mm:ss', () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack({ duration_ms: 3_725_000 }), showDuration: true },
    })
    expect(wrapper.find('.tk-dur').text()).toBe('1:02:05')
  })

  // --- Extension: clickable artists (track.artists[]) ---

  it('renders one link per artist with the right target and a comma separator', () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: makeTrack({
          artists: [
            { id: 1, name: 'deadmau5' },
            { id: 2, name: 'Kaskade' },
          ],
        }),
        showArtist: true,
      },
    })
    const links = wrapper.findAllComponents(RouterLinkStub)
    expect(links).toHaveLength(2)
    expect(links.map((l) => l.props('to'))).toEqual(['/artist/1', '/artist/2'])
    expect(wrapper.find('.tk-artist').text()).toBe('deadmau5, Kaskade')
  })

  it('falls back to the flat artist string when artists is empty', () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack({ artists: [] }), showArtist: true },
    })
    expect(wrapper.findAllComponents(RouterLinkStub)).toHaveLength(0)
    expect(wrapper.find('.tk-artist').text()).toBe('deadmau5')
  })

  it('does not emit play nor propagate to the row when an artist link is clicked', async () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: makeTrack({ artists: [{ id: 1, name: 'deadmau5' }] }),
        showArtist: true,
      },
    })
    // A real listener on the row: VTU's click bubbles, so @click.stop on the link
    // is what must keep the click from reaching the row (and it never emits play).
    const rowSpy = vi.fn()
    wrapper.find('.track-card').element.addEventListener('click', rowSpy)
    await wrapper.find('.tk-artist-link').trigger('click')
    expect(rowSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('play')).toBeFalsy()
  })
})
