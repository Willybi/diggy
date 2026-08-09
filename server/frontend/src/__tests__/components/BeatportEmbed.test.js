import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import BeatportEmbed from '../../components/BeatportEmbed.vue'

// jsdom has no IntersectionObserver; a recording stub drives visibility by hand.
let observers

class ObserverStub {
  constructor(cb, options) {
    this.cb = cb
    this.options = options
    this.observed = []
    this.disconnected = false
    observers.push(this)
  }
  observe(el) {
    this.observed.push(el)
  }
  disconnect() {
    this.disconnected = true
  }
}

beforeEach(() => {
  observers = []
  vi.stubGlobal('IntersectionObserver', ObserverStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('BeatportEmbed', () => {
  it('renders a same-height placeholder (no iframe) before entering the viewport', () => {
    const wrapper = mount(BeatportEmbed, { props: { beatportId: 12345 } })
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('.bp-frame--placeholder').exists()).toBe(true)
    expect(observers).toHaveLength(1)
    expect(observers[0].observed).toHaveLength(1)
  })

  it('stays a placeholder on a non-intersecting notification', async () => {
    const wrapper = mount(BeatportEmbed, { props: { beatportId: 12345 } })
    observers[0].cb([{ isIntersecting: false }])
    await nextTick()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(observers[0].disconnected).toBe(false)
  })

  it('mounts the lazy iframe on intersection, then disconnects (one-shot)', async () => {
    const wrapper = mount(BeatportEmbed, { props: { beatportId: 12345 } })
    observers[0].cb([{ isIntersecting: true }])
    await nextTick()
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('https://embed.beatport.com/?id=12345&type=track')
    expect(iframe.attributes('loading')).toBe('lazy')
    expect(wrapper.find('.bp-frame--placeholder').exists()).toBe(false)
    expect(observers[0].disconnected).toBe(true)
  })

  it('renders the functional link to the Beatport track page', () => {
    const wrapper = mount(BeatportEmbed, { props: { beatportId: 12345 } })
    const link = wrapper.find('a.bp-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://www.beatport.com/track/-/12345')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener')
  })

  it('falls back to an eager iframe when IntersectionObserver is unavailable', async () => {
    vi.unstubAllGlobals()
    const wrapper = mount(BeatportEmbed, { props: { beatportId: 12345 } })
    await nextTick()
    expect(wrapper.find('iframe').exists()).toBe(true)
    expect(wrapper.find('.bp-frame--placeholder').exists()).toBe(false)
  })

  it('disconnects the observer on unmount', () => {
    const wrapper = mount(BeatportEmbed, { props: { beatportId: 12345 } })
    wrapper.unmount()
    expect(observers[0].disconnected).toBe(true)
  })
})
