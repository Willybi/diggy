import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'
import { computeWindow, useVirtualWindow } from '../../composables/useVirtualWindow.js'

describe('computeWindow (pure)', () => {
  const base = { scrollTop: 0, viewportHeight: 600, rowHeight: 50, count: 1000, overscan: 5 }

  it('windows the top of the list at scroll 0', () => {
    const win = computeWindow(base)
    // Visible rows 0..11 (600/50), plus 5 overscan below.
    expect(win.startIndex).toBe(0)
    expect(win.endIndex).toBe(16)
    expect(win.padTop).toBe(0)
    expect(win.padBottom).toBe((1000 - 1 - 16) * 50)
  })

  it('windows a middle scroll position with overscan on both sides', () => {
    const win = computeWindow({ ...base, scrollTop: 5000 })
    // First visible = 100, last visible = ceil(5600/50)-1 = 111.
    expect(win.startIndex).toBe(95)
    expect(win.endIndex).toBe(116)
    expect(win.padTop).toBe(95 * 50)
    expect(win.padBottom).toBe((999 - 116) * 50)
  })

  it('accounts for the list offset from the document top', () => {
    const noOffset = computeWindow({ ...base, scrollTop: 5000 })
    const offset = computeWindow({ ...base, scrollTop: 5000, offsetTop: 500 })
    expect(offset.startIndex).toBe(noOffset.startIndex - 10)
  })

  it('clamps the end of the list (padBottom 0, endIndex = count-1)', () => {
    const win = computeWindow({ ...base, scrollTop: 49_600 })
    expect(win.endIndex).toBe(999)
    expect(win.padBottom).toBe(0)
  })

  it('never goes below zero when the viewport is above the list', () => {
    const win = computeWindow({ ...base, scrollTop: 0, offsetTop: 10_000 })
    expect(win.startIndex).toBe(0)
    expect(win.padTop).toBe(0)
    expect(win.endIndex).toBeGreaterThanOrEqual(win.startIndex)
  })

  it('renders a short list entirely', () => {
    const win = computeWindow({ ...base, count: 8 })
    expect(win.startIndex).toBe(0)
    expect(win.endIndex).toBe(7)
    expect(win.padTop).toBe(0)
    expect(win.padBottom).toBe(0)
  })

  it('empty list → empty window with zero spacers', () => {
    expect(computeWindow({ ...base, count: 0 })).toEqual({
      startIndex: 0,
      endIndex: -1,
      padTop: 0,
      padBottom: 0,
    })
  })

  it('guards against a non-positive row height', () => {
    expect(computeWindow({ ...base, rowHeight: 0 })).toEqual({
      startIndex: 0,
      endIndex: -1,
      padTop: 0,
      padBottom: 0,
    })
  })

  it('overscan 0 windows exactly the visible rows', () => {
    const win = computeWindow({ ...base, scrollTop: 5000, overscan: 0 })
    expect(win.startIndex).toBe(100)
    expect(win.endIndex).toBe(111)
  })
})

describe('useVirtualWindow (composable)', () => {
  function setViewport({ scrollY = 0, innerHeight = 600 } = {}) {
    Object.defineProperty(window, 'scrollY', { value: scrollY, configurable: true })
    Object.defineProperty(window, 'innerHeight', { value: innerHeight, configurable: true })
  }

  function mountWindowed(opts) {
    let vw
    const wrapper = mount({
      setup() {
        vw = useVirtualWindow(opts)
        return () => null
      },
    })
    return { wrapper, vw }
  }

  beforeEach(() => {
    setViewport()
  })

  afterEach(() => {
    setViewport()
  })

  it('computes the initial window on mount and reacts to scroll', () => {
    const count = ref(1000)
    const { vw } = mountWindowed({ count, rowHeight: 50, overscan: 5 })
    expect(vw.startIndex.value).toBe(0)
    expect(vw.endIndex.value).toBe(16)

    setViewport({ scrollY: 5000 })
    window.dispatchEvent(new window.Event('scroll'))
    expect(vw.startIndex.value).toBe(95)
    expect(vw.padTop.value).toBe(95 * 50)
  })

  it('recomputes when the row count grows (page appended)', async () => {
    const count = ref(10)
    const { vw } = mountWindowed({ count, rowHeight: 50, overscan: 5 })
    expect(vw.endIndex.value).toBe(9)

    count.value = 100
    await nextTick()
    expect(vw.endIndex.value).toBe(16)
    expect(vw.padBottom.value).toBe((99 - 16) * 50)
  })

  it('fires onNearEnd when the window approaches the loaded end', () => {
    const onNearEnd = vi.fn()
    const count = ref(100)
    const { vw } = mountWindowed({ count, rowHeight: 50, overscan: 5, nearEndCount: 20, onNearEnd })
    expect(onNearEnd).not.toHaveBeenCalled()

    setViewport({ scrollY: 3800 }) // last visible ≈ 87 ≥ 100-20
    window.dispatchEvent(new window.Event('scroll'))
    expect(onNearEnd).toHaveBeenCalled()
    expect(vw.endIndex.value).toBeGreaterThanOrEqual(80)
  })

  it('never fires onNearEnd for an empty list', () => {
    const onNearEnd = vi.fn()
    mountWindowed({ count: ref(0), rowHeight: 50, onNearEnd })
    window.dispatchEvent(new window.Event('scroll'))
    expect(onNearEnd).not.toHaveBeenCalled()
  })

  it('detaches its scroll/resize listeners on unmount', () => {
    const count = ref(1000)
    const { wrapper, vw } = mountWindowed({ count, rowHeight: 50 })
    wrapper.unmount()

    setViewport({ scrollY: 5000 })
    window.dispatchEvent(new window.Event('scroll'))
    expect(vw.startIndex.value).toBe(0) // untouched after unmount
  })
})

describe('useVirtualWindow (container scroll source)', () => {
  // A fake scrollable element: captures its scroll handler so a test can drive
  // scrollTop and re-fire it, and reports its own viewport via clientHeight.
  function makeContainer({ clientHeight = 600 } = {}) {
    let handler = null
    return {
      scrollTop: 0,
      clientHeight,
      getBoundingClientRect: () => ({ top: 0 }),
      addEventListener: (evt, fn) => {
        if (evt === 'scroll') handler = fn
      },
      removeEventListener: (evt) => {
        if (evt === 'scroll') handler = null
      },
      fireScroll(scrollTop) {
        this.scrollTop = scrollTop
        handler?.()
      },
      get bound() {
        return handler != null
      },
    }
  }

  function mountWindowed(opts) {
    let vw
    const wrapper = mount({
      setup() {
        vw = useVirtualWindow(opts)
        return () => null
      },
    })
    return { wrapper, vw }
  }

  it('reads scrollTop/clientHeight from the container, not the window', () => {
    const container = ref(makeContainer({ clientHeight: 600 }))
    const { vw } = mountWindowed({ count: ref(1000), rowHeight: 50, overscan: 5, container })
    expect(vw.startIndex.value).toBe(0)
    expect(vw.endIndex.value).toBe(16)

    container.value.fireScroll(5000)
    expect(vw.startIndex.value).toBe(95)
    expect(vw.padTop.value).toBe(95 * 50)
  })

  it('ignores window scroll when a container is the source', () => {
    const container = ref(makeContainer())
    const { vw } = mountWindowed({ count: ref(1000), rowHeight: 50, overscan: 5, container })

    Object.defineProperty(window, 'scrollY', { value: 5000, configurable: true })
    window.dispatchEvent(new window.Event('scroll'))
    expect(vw.startIndex.value).toBe(0) // container never scrolled
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
  })

  it('binds onto the container once it resolves after mount', async () => {
    const container = ref(null)
    const { vw } = mountWindowed({ count: ref(1000), rowHeight: 50, overscan: 5, container })

    const el = makeContainer()
    container.value = el
    await nextTick()
    expect(el.bound).toBe(true)

    el.fireScroll(5000)
    expect(vw.startIndex.value).toBe(95)
  })

  it('detaches the container scroll listener on unmount', () => {
    const el = makeContainer()
    const { wrapper } = mountWindowed({ count: ref(1000), rowHeight: 50, container: ref(el) })
    expect(el.bound).toBe(true)
    wrapper.unmount()
    expect(el.bound).toBe(false)
  })
})
