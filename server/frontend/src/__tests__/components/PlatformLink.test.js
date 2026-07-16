import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PlatformLink from '../../components/PlatformLink.vue'

describe('PlatformLink', () => {
  it('renders a button variant as an external anchor with the right a11y', () => {
    const wrapper = mount(PlatformLink, {
      props: { platform: 'beatport', href: 'https://beatport.com/track/1' },
    })
    const a = wrapper.find('a.plink')
    expect(a.exists()).toBe(true)
    expect(a.attributes('href')).toBe('https://beatport.com/track/1')
    expect(a.attributes('target')).toBe('_blank')
    expect(a.attributes('rel')).toBe('noopener')
    expect(a.attributes('aria-label')).toBe('Voir sur Beatport')
    expect(wrapper.find('path').attributes('d')).toBeTruthy()
  })

  it('maps platform keys to display names (TIDAL, 1001Tracklists)', () => {
    const tidal = mount(PlatformLink, { props: { platform: 'tidal', href: '#' } })
    expect(tidal.find('a').attributes('aria-label')).toBe('Voir sur TIDAL')
    const tl = mount(PlatformLink, { props: { platform: '1001tl', href: '#' } })
    expect(tl.find('a').attributes('aria-label')).toBe('Voir sur 1001Tracklists')
  })

  it('renders a glyph variant as a non-clickable span with source labelling', () => {
    const wrapper = mount(PlatformLink, { props: { platform: 'deezer', variant: 'glyph' } })
    expect(wrapper.find('a').exists()).toBe(false)
    const span = wrapper.find('span.plink')
    expect(span.exists()).toBe(true)
    expect(span.attributes('role')).toBe('img')
    expect(span.attributes('aria-label')).toBe('Détecté sur Deezer')
    expect(span.attributes('title')).toBe('Détecté sur Deezer')
  })

  it('applies the size modifier on the button variant', () => {
    expect(
      mount(PlatformLink, { props: { platform: 'deezer', href: '#', size: 'sm' } })
        .find('a')
        .classes(),
    ).toContain('plink--sm')
  })
})
