import { describe, it, expect } from 'vitest'
import { mount, config, RouterLinkStub } from '@vue/test-utils'
import SetCard from '../../components/SetCard.vue'

// SetCard wraps the whole card in a <RouterLink>. vue-router isn't installed here,
// so register the stub file-wide — VTU `stubs` are a no-op for an unresolved
// component (see CLAUDE.md pitfall / BottomNav.test.js).
config.global.components = { ...config.global.components, RouterLink: RouterLinkStub }

const baseSet = {
  id: 12,
  title: 'Boiler Room: Amsterdam',
  source: 'soundcloud',
  played_date: '2024-05-01',
  duration_ms: 7275000, // 2:01:15
  has_artwork: true,
  total_tracks: 30,
  identified_tracks: 18,
  artists: ['DJ One', 'DJ Two'],
}

function makeSet(overrides = {}) {
  return { ...baseSet, ...overrides }
}

describe('SetCard', () => {
  it('links the whole card to /set/:id (a single link)', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet() } })
    const links = wrapper.findAllComponents(RouterLinkStub)
    expect(links).toHaveLength(1)
    expect(links[0].props('to')).toBe('/set/12')
  })

  it('renders the title', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet() } })
    expect(wrapper.find('.sc-title').text()).toBe('Boiler Room: Amsterdam')
  })

  it('joins the artist names with a comma', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet() } })
    expect(wrapper.find('.sc-artists').text()).toBe('DJ One, DJ Two')
  })

  it('omits the artists line when artists is empty', () => {
    const empty = mount(SetCard, { props: { set: makeSet({ artists: [] }) } })
    expect(empty.find('.sc-artists').exists()).toBe(false)
    const undef = mount(SetCard, { props: { set: makeSet({ artists: undefined }) } })
    expect(undef.find('.sc-artists').exists()).toBe(false)
  })

  it('renders the meta line date · durée · N tracks', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet() } })
    // The exact day is timezone-dependent — assert the structure, not the calendar day.
    expect(wrapper.find('.sc-meta').text()).toMatch(/^\d{2}\/\d{2}\/\d{4} · 2:01:15 · 30 tracks$/)
  })

  it('omits null meta fields and adjusts separators (never a dash)', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet({ played_date: null }) } })
    const meta = wrapper.find('.sc-meta').text()
    expect(meta).toBe('2:01:15 · 30 tracks')
    expect(meta).not.toContain('—')
  })

  it('drops both date and duration when null', () => {
    const wrapper = mount(SetCard, {
      props: { set: makeSet({ played_date: null, duration_ms: null }) },
    })
    expect(wrapper.find('.sc-meta').text()).toBe('30 tracks')
  })

  it('uses the singular "track" for a single track', () => {
    const wrapper = mount(SetCard, {
      props: { set: makeSet({ played_date: null, duration_ms: null, total_tracks: 1 }) },
    })
    expect(wrapper.find('.sc-meta').text()).toBe('1 track')
  })

  it('renders the set cover from the set-artworks bucket', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet() } })
    expect(wrapper.find('.aw-img').attributes('src')).toBe('/storage/set-artworks/12.jpg')
  })

  it('falls back to the striped placeholder without artwork', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet({ has_artwork: false }) } })
    expect(wrapper.find('.aw-ph').exists()).toBe(true)
    expect(wrapper.find('.aw-img').exists()).toBe(false)
  })

  it('shows no in-lib indicator on the cover', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet() } })
    expect(wrapper.find('.aw-lib').exists()).toBe(false)
  })

  it('never displays the score or identified count', () => {
    const wrapper = mount(SetCard, { props: { set: makeSet() } })
    // 18 = identified_tracks; it appears nowhere in the base set otherwise.
    expect(wrapper.text()).not.toContain('18')
  })

  it('renders nothing in the footer by default and the slot when provided', () => {
    const empty = mount(SetCard, { props: { set: makeSet() } })
    expect(empty.find('.sc-footer').exists()).toBe(false)
    const withFooter = mount(SetCard, {
      props: { set: makeSet() },
      slots: { footer: '<span class="probe">F</span>' },
    })
    expect(withFooter.find('.sc-footer .probe').exists()).toBe(true)
  })
})
