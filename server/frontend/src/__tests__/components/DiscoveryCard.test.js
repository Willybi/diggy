import { describe, it, expect } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import DiscoveryCard from '../../components/DiscoveryCard.vue'

// NavCover renders a <RouterLink> for an internal `to`; register the stub so it
// resolves without a real router (the pitfall: a string/boolean stub is a no-op).
const global = { components: { RouterLink: RouterLinkStub } }

// Minimal internal (trend) card props.
function baseProps(overrides = {}) {
  return {
    title: 'La La Land',
    artists: [{ id: 1, name: 'Green Velvet' }],
    coverId: 42,
    hasArtwork: true,
    hasPreview: true,
    metaParts: ['125', '4A', '6 j'],
    ...overrides,
  }
}

describe('DiscoveryCard', () => {
  it('renders the title and joins artists with ", "', () => {
    const wrapper = mount(DiscoveryCard, {
      props: baseProps({
        artists: [
          { id: 1, name: 'Kaskade' },
          { id: 2, name: 'deadmau5' },
        ],
      }),
    })
    expect(wrapper.find('.dc-title').text()).toBe('La La Land')
    expect(wrapper.find('.dc-artist').text()).toBe('Kaskade, deadmau5')
  })

  it('falls back to the flat `artist` string when no artists array is given', () => {
    const wrapper = mount(DiscoveryCard, {
      props: baseProps({ artists: [], artist: 'Green Velvet' }),
    })
    expect(wrapper.find('.dc-artist').text()).toBe('Green Velvet')
  })

  it('joins metaParts with " · " and omits empty cells (never a dash)', () => {
    const wrapper = mount(DiscoveryCard, {
      props: baseProps({ metaParts: ['125', null, '6 j', ''] }),
    })
    const meta = wrapper.find('.dc-meta')
    expect(meta.text()).toBe('125 · 6 j')
    expect(meta.text()).not.toContain('—')
    expect(meta.text()).not.toContain('· ·')
  })

  it('renders no meta line when metaParts is empty', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps({ metaParts: [] }) })
    expect(wrapper.find('.dc-meta').exists()).toBe(false)
  })

  it('renders a #rank accent badge when rank is given', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps({ rank: 3 }) })
    const badge = wrapper.find('.dc-badge')
    expect(badge.text()).toBe('#3')
    expect(badge.classes()).toContain('dc-badge--accent')
  })

  it('renders a "Nouveauté" accent badge', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps({ badge: 'Nouveauté' }) })
    const badge = wrapper.find('.dc-badge')
    expect(badge.text()).toBe('Nouveauté')
    expect(badge.classes()).toContain('dc-badge--accent')
  })

  it('renders a "Set" neutral badge with its glyph', () => {
    const wrapper = mount(DiscoveryCard, {
      props: baseProps({ badge: 'Set', badgeIcon: 'set', hasPreview: false }),
    })
    const badge = wrapper.find('.dc-badge')
    expect(badge.text()).toBe('Set')
    expect(badge.classes()).toContain('dc-badge--set')
    expect(badge.find('svg.dc-badge-icon').exists()).toBe(true)
  })

  it('renders no badge when neither rank nor badge is given (reco variant)', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps() })
    expect(wrapper.find('.dc-badge').exists()).toBe(false)
  })

  it('shows no play button when hasPreview is false', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps({ hasPreview: false }) })
    expect(wrapper.find('.dc-play').exists()).toBe(false)
  })

  it('emits `play` (and not `open`) when the play button is clicked', async () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps() })
    await wrapper.find('.dc-play').trigger('click')
    expect(wrapper.emitted('play')).toBeTruthy()
    // @click.stop keeps the card-open handler from firing.
    expect(wrapper.emitted('open')).toBeFalsy()
  })

  it('renders an internal RouterLink to `to` (card root stays a div)', () => {
    const wrapper = mount(DiscoveryCard, {
      props: baseProps({ to: '/catalog/42' }),
      global,
    })
    expect(wrapper.element.tagName).toBe('DIV')
    const link = wrapper.findComponent(RouterLinkStub)
    expect(link.exists()).toBe(true)
    expect(link.props('to')).toBe('/catalog/42')
    // Internal → no external anchor (RouterLinkStub renders an <a>, but never target=_blank).
    expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
  })

  it('renders an external <a target=_blank rel=noopener> when href is given', () => {
    const wrapper = mount(DiscoveryCard, {
      props: baseProps({
        href: 'https://deezer.com/track/1',
        hasPreview: false,
        badge: 'Nouveauté',
        badgeIcon: 'ext',
      }),
      global,
    })
    // The card root is a div; the stretched link is the NavCover anchor.
    expect(wrapper.element.tagName).toBe('DIV')
    const link = wrapper.find('a.nav-cover')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://deezer.com/track/1')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener')
    // href wins over an internal RouterLink.
    expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
  })

  it('renders no link when neither `to` nor `href` is set', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps(), global })
    expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
    expect(wrapper.find('a.nav-cover').exists()).toBe(false)
  })

  it('renders no link on a skeleton card', () => {
    const wrapper = mount(DiscoveryCard, {
      props: { skeleton: true, to: '/catalog/1' },
      global,
    })
    expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
    expect(wrapper.find('a.nav-cover').exists()).toBe(false)
  })

  it('passes no in-lib indicator to Artwork when inLib is undefined', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps() })
    // Artwork renders .aw-lib only for a real boolean.
    expect(wrapper.find('.aw-lib').exists()).toBe(false)
  })

  it('passes the in-lib indicator through to Artwork when inLib is set', () => {
    const wrapper = mount(DiscoveryCard, { props: baseProps({ inLib: true }) })
    expect(wrapper.find('.aw-lib.in').exists()).toBe(true)
  })

  it('renders a skeleton placeholder with no interactive elements', () => {
    const wrapper = mount(DiscoveryCard, { props: { skeleton: true } })
    expect(wrapper.find('.dc-card--skeleton').exists()).toBe(true)
    expect(wrapper.find('.dc-play').exists()).toBe(false)
    expect(wrapper.find('.dc-title').exists()).toBe(false)
  })
})
