import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Artwork from '../../components/Artwork.vue'

describe('Artwork', () => {
  it('renders the striped placeholder (no image) when src is absent', () => {
    const wrapper = mount(Artwork)
    expect(wrapper.find('.aw-ph').exists()).toBe(true)
    expect(wrapper.find('.aw-img').exists()).toBe(false)
  })

  it('renders the image when src is provided', () => {
    const wrapper = mount(Artwork, {
      props: { src: '/storage/catalog-artworks/1.jpg', alt: 'Cover' },
    })
    const img = wrapper.find('.aw-img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('/storage/catalog-artworks/1.jpg')
    expect(img.attributes('alt')).toBe('Cover')
    expect(wrapper.find('.aw-ph').exists()).toBe(false)
  })

  it('falls back to the placeholder when the image fails to load', async () => {
    const wrapper = mount(Artwork, { props: { src: '/broken.jpg' } })
    expect(wrapper.find('.aw-img').exists()).toBe(true)
    await wrapper.find('.aw-img').trigger('error')
    expect(wrapper.find('.aw-img').exists()).toBe(false)
    expect(wrapper.find('.aw-ph').exists()).toBe(true)
  })

  it('shows no in-lib indicator when inLib is omitted (undefined)', () => {
    const wrapper = mount(Artwork)
    expect(wrapper.find('.aw-lib').exists()).toBe(false)
  })

  it('shows the filled in-lib dot when inLib is true', () => {
    const wrapper = mount(Artwork, { props: { inLib: true } })
    const lib = wrapper.find('.aw-lib')
    expect(lib.exists()).toBe(true)
    expect(lib.classes()).toContain('in')
  })

  it('shows the dashed in-lib dot when inLib is false', () => {
    const wrapper = mount(Artwork, { props: { inLib: false } })
    const lib = wrapper.find('.aw-lib')
    expect(lib.exists()).toBe(true)
    expect(lib.classes()).toContain('out')
  })

  it('applies the size modifier class', () => {
    expect(
      mount(Artwork, { props: { size: 'hero' } })
        .find('.artwork')
        .classes(),
    ).toContain('artwork--hero')
    expect(
      mount(Artwork, { props: { size: 'row' } })
        .find('.artwork')
        .classes(),
    ).toContain('artwork--row')
  })
})
