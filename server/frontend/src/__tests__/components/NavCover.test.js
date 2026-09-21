import { describe, it, expect } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'

import NavCover from '../../components/NavCover.vue'

// vue-router is not installed in the test env, so <router-link> never resolves —
// register RouterLinkStub as a global component (VTU `stubs` are a no-op for an
// unresolved component; see CLAUDE.md pitfall / BottomNav.test.js).
const globalOpts = { global: { components: { RouterLink: RouterLinkStub } } }

describe('NavCover', () => {
  it('renders a RouterLink to the internal target when `to` is set', () => {
    const wrapper = mount(NavCover, {
      props: { to: '/artist/42', label: 'Amelie Lens' },
      ...globalOpts,
    })
    const link = wrapper.findComponent(RouterLinkStub)
    expect(link.exists()).toBe(true)
    expect(link.props('to')).toBe('/artist/42')
    expect(link.attributes('aria-label')).toBe('Amelie Lens')
    // No external anchor is rendered on the internal path.
    expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
  })

  it('renders an external <a> (new tab, noopener) when `href` is set', () => {
    const wrapper = mount(NavCover, {
      props: { href: 'https://example.com', label: 'Open externally' },
      ...globalOpts,
    })
    const a = wrapper.find('a.nav-cover')
    expect(a.exists()).toBe(true)
    expect(a.attributes('href')).toBe('https://example.com')
    expect(a.attributes('target')).toBe('_blank')
    expect(a.attributes('rel')).toBe('noopener')
    expect(a.attributes('aria-label')).toBe('Open externally')
    expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
  })

  it('prefers `href` over `to` when both are set', () => {
    const wrapper = mount(NavCover, {
      props: { href: 'https://example.com', to: '/artist/42' },
      ...globalOpts,
    })
    expect(wrapper.find('a[target="_blank"]').exists()).toBe(true)
    expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
  })

  it('renders nothing when neither `to` nor `href` is provided', () => {
    const wrapper = mount(NavCover, { props: {}, ...globalOpts })
    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
    expect(wrapper.html()).toBe('<!--v-if-->')
  })
})
