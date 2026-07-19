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

  it('renders a dimmed em dash for a missing key on a normal row', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack({ key: null }) } })
    const key = wrapper.find('.tk-key')
    expect(key.text()).toBe('—')
    expect(key.classes()).toContain('tk-key--empty')
  })

  it('renders a dimmed em dash for a missing bpm on a normal row', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack({ bpm: null }) } })
    const bpm = wrapper.find('.tk-bpm')
    expect(bpm.text()).toBe('—')
    expect(bpm.classes()).toContain('tk-bpm--empty')
  })

  it('does not dim a present key or bpm', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack() } })
    expect(wrapper.find('.tk-key').classes()).not.toContain('tk-key--empty')
    expect(wrapper.find('.tk-bpm').classes()).not.toContain('tk-bpm--empty')
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

  // --- Extension set: position + timecode + states ---

  it('renders no position, timecode or state markers by default', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack() } })
    expect(wrapper.find('.tk-pos').exists()).toBe(false)
    expect(wrapper.find('.tk-tc').exists()).toBe(false)
    const cls = wrapper.find('.track-card').classes()
    expect(cls).not.toContain('has-position')
    expect(cls).not.toContain('has-timecode')
    expect(cls).not.toContain('state-id')
    expect(cls).not.toContain('state-unresolved')
  })

  it('renders the position cell (mono, never a link) when position is provided', () => {
    const wrapper = mount(TrackCard, { props: { track: makeTrack(), position: 7 } })
    const pos = wrapper.find('.tk-pos')
    expect(pos.exists()).toBe(true)
    expect(pos.text()).toBe('7') // no zero-padding
    expect(pos.element.tagName).toBe('SPAN')
    expect(wrapper.find('.track-card').classes()).toContain('has-position')
  })

  it('renders the timecode as a link with target/rel when href is given', () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: makeTrack(),
        timecode: { ms: 3_725_000, href: 'https://youtu.be/x?t=3725' },
      },
    })
    const tc = wrapper.find('.tk-tc')
    expect(tc.exists()).toBe(true)
    expect(tc.element.tagName).toBe('A')
    expect(tc.classes()).toContain('tk-tc--link')
    expect(tc.attributes('href')).toBe('https://youtu.be/x?t=3725')
    expect(tc.attributes('target')).toBe('_blank')
    expect(tc.attributes('rel')).toBe('noopener')
    expect(tc.text()).toBe('1:02:05')
    expect(wrapper.find('.track-card').classes()).toContain('has-timecode')
  })

  it('renders the timecode as plain text (no link) when href is absent', () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack(), timecode: { ms: 200000 } },
    })
    const tc = wrapper.find('.tk-tc')
    expect(tc.element.tagName).toBe('SPAN')
    expect(tc.classes()).not.toContain('tk-tc--link')
    expect(tc.text()).toBe('3:20')
  })

  it('renders an em dash when the timecode ms is null', () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack(), timecode: { ms: null } },
    })
    expect(wrapper.find('.tk-tc').text()).toBe('—')
  })

  it('does not propagate to the row nor emit play when the timecode link is clicked', async () => {
    const wrapper = mount(TrackCard, {
      props: { track: makeTrack(), timecode: { ms: 100000, href: 'https://youtu.be/x?t=100' } },
    })
    const rowSpy = vi.fn()
    wrapper.find('.track-card').element.addEventListener('click', rowSpy)
    await wrapper.find('.tk-tc--link').trigger('click')
    expect(rowSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('play')).toBeFalsy()
  })

  it('renders the "id" state: "ID" title, empty data cells, no play, no in-lib', () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: makeTrack({ has_preview: true }),
        showArtist: true,
        position: 7,
        timecode: { ms: 100000 },
        state: 'id',
      },
    })
    expect(wrapper.find('.track-card').classes()).toContain('state-id')
    expect(wrapper.find('.tk-title').text()).toBe('ID')
    expect(wrapper.find('.tk-title').classes()).toContain('tk-title--id')
    expect(wrapper.find('.tk-artist').text()).toBe('non identifié')
    // Data cells are empty (not dashes) — the track itself is unknown.
    expect(wrapper.find('.tk-bpm').text()).toBe('')
    expect(wrapper.find('.tk-key').text()).toBe('')
    // No play affordance (even with has_preview), no in-lib chip, placeholder cover.
    expect(wrapper.find('.tk-play').exists()).toBe(false)
    expect(wrapper.find('.aw-lib').exists()).toBe(false)
    expect(wrapper.find('.aw-ph').exists()).toBe(true)
    // Position + timecode still render normally.
    expect(wrapper.find('.tk-pos').text()).toBe('7')
    expect(wrapper.find('.tk-tc').text()).toBe('1:40')
  })

  it('renders the "unresolved" state: raw title/artist as plain text, dashes, no play', () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: makeTrack({
          title: 'Unknown ID',
          artist: 'Some DJ',
          artists: [{ id: 1, name: 'Linked' }],
          has_preview: true,
        }),
        showArtist: true,
        showDuration: true,
        state: 'unresolved',
      },
    })
    expect(wrapper.find('.track-card').classes()).toContain('state-unresolved')
    expect(wrapper.find('.tk-title').text()).toBe('Unknown ID')
    expect(wrapper.find('.tk-title').classes()).not.toContain('tk-title--id')
    // Raw artist string, never links — artists[] is ignored in this state.
    expect(wrapper.findAllComponents(RouterLinkStub)).toHaveLength(0)
    expect(wrapper.find('.tk-artist').text()).toBe('Some DJ')
    expect(wrapper.find('.tk-bpm').text()).toBe('—')
    expect(wrapper.find('.tk-key').text()).toBe('—')
    expect(wrapper.find('.tk-dur').text()).toBe('—')
    expect(wrapper.find('.tk-play').exists()).toBe(false)
  })
})
