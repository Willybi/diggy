import { ref, watch, onMounted, onUnmounted, toValue } from 'vue'

/**
 * Pure windowing math for a constant-row-height list scrolled by the PAGE
 * (no nested scroll container). Exported separately so it is testable
 * without any DOM.
 *
 * @param {object} p
 * @param {number} p.scrollTop        page scroll position (px)
 * @param {number} p.viewportHeight   visible viewport height (px)
 * @param {number} p.rowHeight        constant row height (px, > 0)
 * @param {number} p.count            total number of rows
 * @param {number} [p.overscan=6]     extra rows rendered above/below
 * @param {number} [p.offsetTop=0]    distance from document top to the list top
 * @returns {{ startIndex: number, endIndex: number, padTop: number, padBottom: number }}
 *   startIndex/endIndex inclusive; empty list → { 0, -1, 0, 0 }.
 *   padTop/padBottom are the spacer heights replacing the unrendered rows.
 */
export function computeWindow({
  scrollTop,
  viewportHeight,
  rowHeight,
  count,
  overscan = 6,
  offsetTop = 0,
}) {
  if (!count || count <= 0 || !rowHeight || rowHeight <= 0) {
    return { startIndex: 0, endIndex: -1, padTop: 0, padBottom: 0 }
  }
  const rel = scrollTop - offsetTop
  const clampIndex = (i) => Math.max(0, Math.min(count - 1, i))
  const firstVisible = clampIndex(Math.floor(rel / rowHeight))
  const lastVisible = clampIndex(Math.ceil((rel + viewportHeight) / rowHeight) - 1)
  const startIndex = clampIndex(firstVisible - overscan)
  const endIndex = clampIndex(Math.max(startIndex, lastVisible + overscan))
  return {
    startIndex,
    endIndex,
    padTop: startIndex * rowHeight,
    padBottom: (count - 1 - endIndex) * rowHeight,
  }
}

/**
 * Reactive window over a constant-row-height list, driven by a scroll source.
 *
 * The consumer renders only items[startIndex..endIndex] between two spacers of
 * padTop/padBottom pixels. `onNearEnd` fires when the window approaches the end
 * of the loaded rows — wire it to the next-page fetch (e.g. useWindowedList's
 * loadMore, which already guards loading/hasMore).
 *
 * Scroll source: `window` by default (page scroll). When the list lives inside
 * a scrollable ancestor (e.g. an app shell whose main panel is
 * `overflow-y: auto`, not the page), pass `container` — that element becomes
 * the scroll/resize source and its scrollTop/clientHeight drive the math. The
 * composable OWNS the listeners either way (the consumer never wires its own).
 *
 * @param {object} opts
 * @param {import('vue').MaybeRefOrGetter<number>} opts.count      total loaded rows
 * @param {import('vue').MaybeRefOrGetter<number>} opts.rowHeight  constant row height (px)
 * @param {import('vue').Ref<HTMLElement|null>} opts.listRef       the list container element
 * @param {import('vue').MaybeRefOrGetter<HTMLElement|null>} [opts.container]
 *   scroll source; omitted/null → the window (page scroll)
 * @param {number} [opts.overscan=6]
 * @param {number} [opts.nearEndCount=20]  fire onNearEnd when fewer rows remain below the window
 * @param {() => void} [opts.onNearEnd]
 */
export function useVirtualWindow({
  count,
  rowHeight,
  listRef,
  container,
  overscan = 6,
  nearEndCount = 20,
  onNearEnd,
}) {
  const startIndex = ref(0)
  const endIndex = ref(-1)
  const padTop = ref(0)
  const padBottom = ref(0)

  function update() {
    const total = toValue(count)
    const rowH = toValue(rowHeight)
    const el = listRef?.value
    const scroller = toValue(container)
    // offsetTop = the list's distance from the top of the scrolled coordinate
    // space. Against the window that is documentTop; against a container it is
    // the list's offset from the container's own top (both viewport-relative
    // rects cancel the shared page offset, then we add the container scrollTop).
    let scrollTop
    let viewportHeight
    let offsetTop
    if (scroller) {
      scrollTop = scroller.scrollTop
      viewportHeight = scroller.clientHeight
      offsetTop = el ? el.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop : 0
    } else {
      scrollTop = window.scrollY
      viewportHeight = window.innerHeight
      offsetTop = el ? el.getBoundingClientRect().top + window.scrollY : 0
    }
    const win = computeWindow({
      scrollTop,
      viewportHeight,
      rowHeight: rowH,
      count: total,
      overscan,
      offsetTop,
    })
    startIndex.value = win.startIndex
    endIndex.value = win.endIndex
    padTop.value = win.padTop
    padBottom.value = win.padBottom
    if (onNearEnd && total > 0 && win.endIndex >= total - nearEndCount) onNearEnd()
  }

  // The scroll target is rebindable: a container ref may only resolve after
  // mount (the consumer finds its scroll ancestor in its own onMounted, which
  // runs AFTER this composable's). bindScroll re-attaches whenever it changes.
  let scrollTarget = null
  function bindScroll() {
    const next = toValue(container) || window
    if (next === scrollTarget) return
    if (scrollTarget) scrollTarget.removeEventListener('scroll', update)
    scrollTarget = next
    scrollTarget.addEventListener('scroll', update, { passive: true })
    update()
  }

  onMounted(() => {
    bindScroll()
    window.addEventListener('resize', update, { passive: true })
    update()
  })
  onUnmounted(() => {
    if (scrollTarget) scrollTarget.removeEventListener('scroll', update)
    window.removeEventListener('resize', update)
  })

  // Container resolved/changed → rebind the scroll listener onto it.
  watch(
    () => toValue(container),
    () => bindScroll(),
  )

  // New rows appended (or the list replaced) → recompute without waiting for a scroll.
  watch(
    () => toValue(count),
    () => update(),
  )

  return { startIndex, endIndex, padTop, padBottom, update }
}
