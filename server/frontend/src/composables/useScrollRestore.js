import { nextTick, toValue } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

/**
 * Restore the scroll position of a listing view on a back/forward return.
 *
 * Two facts make a plain pixel offset insufficient here, so this composable
 * does more than re-apply `scrollTop`:
 *   1. The app scrolls inside `.app-main` (overflow-y: auto), NOT the window —
 *      so `window.scrollY` is always 0 and Vue Router's native scrollBehavior
 *      (which targets the window) can't help. We drive the container directly.
 *   2. Every listing GROWS its height as pages load (infinite scroll / virtual
 *      window). On a fresh mount only page 1 exists, so the page is too short
 *      to reach a deep offset — we must first reload the rows that were loaded
 *      before, THEN re-apply the offset.
 *
 * The reload is delegated to `hydrate(count)`, which the view wires to a fast
 * one-shot loader (e.g. useWindowedList.fetchUpTo — a single parallel burst).
 * Walking pages sequentially here was the source of a multi-second stall.
 *
 * Mechanism: on leave we snapshot `{ top, count }` into `history.state`. That
 * state is attached to the specific history ENTRY (Vue Router preserves custom
 * fields across its push/replace — it spreads `history.state`), so the snapshot
 * only exists on a genuine return to that entry, never on a fresh link.
 *
 * @param {object} opts
 * @param {import('vue').MaybeRefOrGetter<HTMLElement|null>} opts.scroller  scroll container
 * @param {() => number} opts.getCount  currently loaded row count (for the snapshot)
 * @returns {{
 *   restore: (o: { initialFetch: () => Promise<any>, hydrate: (count: number) => Promise<any> }) => Promise<boolean>,
 *   snapshot: () => void,
 *   reapply: () => Promise<void>,
 * }}
 */
const STATE_KEY = '__diggyScroll'

export function useScrollRestore({ scroller, getCount }) {
  const el = () => toValue(scroller)

  function snapshot() {
    const node = el()
    if (!node) return
    const snap = { top: node.scrollTop, count: getCount() }
    try {
      window.history.replaceState({ ...window.history.state, [STATE_KEY]: snap }, '')
    } catch {
      // replaceState can throw under strict privacy settings — restoration is
      // best-effort, a failure just means this return won't restore.
    }
  }

  onBeforeRouteLeave(() => {
    snapshot()
  })

  async function restore({ initialFetch, hydrate }) {
    const saved = window.history.state?.[STATE_KEY]
    // Fresh visit (no snapshot) or top of the list → just the normal first load.
    if (!saved || !saved.top || !saved.count || !hydrate) {
      await initialFetch()
      return false
    }
    // Back-return: reload the previously loaded rows in one shot, then jump.
    await hydrate(saved.count)
    // Two ticks: one for the rows to render, one for the virtual list's spacers
    // (padTop/padBottom) to settle to the full height before we scroll.
    await nextTick()
    await nextTick()
    const node = el()
    if (node) node.scrollTop = saved.top
    return true
  }

  // Cached return under <KeepAlive>: the view is REACTIVATED, not re-mounted, so
  // its rows are still in memory — restore() (with its refetch) must NOT run.
  // reapply() only re-applies the saved offset: on a genuine back-return it reads
  // the snapshot from this history entry; on a fresh push to this view (no
  // snapshot) it resets to the top, so the list never inherits the scroll the
  // previous view left on the shared .app-main scroller. Called from onActivated.
  async function reapply() {
    const node = el()
    if (!node) return
    const saved = window.history.state?.[STATE_KEY]
    // Two ticks: let the reactivated DOM (and the virtual list's spacers) settle
    // to their full height before we jump — mirrors restore()'s ordering.
    await nextTick()
    await nextTick()
    node.scrollTop = saved && saved.top ? saved.top : 0
  }

  return { restore, snapshot, reapply }
}
