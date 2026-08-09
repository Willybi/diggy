import { ref } from 'vue'
import api from '../utils/api.js'

/**
 * Drive a paginated list backed by a VIRTUALISED table (windowing), not a
 * sentinel-observed card grid.
 *
 * Sibling of usePaginatedList — same offset/hasMore/append-vs-replace
 * bookkeeping and the same reset-only error reset — but split off because the
 * two cannot share an implementation:
 *   - usePaginatedList is the canon for card grids with an IntersectionObserver
 *     sentinel and a fixed `{ sort, limit, offset, family?, q? }` param shape
 *     (axios object params, bracket-serialized arrays).
 *   - a virtualised table has NO sentinel (the window math fires loadMore) and
 *     needs an arbitrary, page-specific param set — here a `skip`-paginated
 *     endpoint with repeated list params — that only the page can build.
 * So the param construction is delegated: the page supplies `buildParams(skip)`
 * returning the complete request params (typically a URLSearchParams), and this
 * composable owns the trunk (in-flight token to defeat request races,
 * loading/hasMore, append vs replace, reset).
 *
 * Pair with useVirtualWindow: wire its `onNearEnd` to `loadMore`, and render
 * only items[startIndex..endIndex].
 *
 * @param {object} opts
 * @param {string} opts.endpoint                 list URL (exact slash matters)
 * @param {(skip: number) => any} opts.buildParams  page-built request params for
 *   a given skip offset (the value passed straight to axios `{ params }`;
 *   the page bakes its own page size into it as the request's `limit`)
 * @returns {{
 *   items: import('vue').Ref<any[]>,
 *   total: import('vue').Ref<number | null>,
 *   loading: import('vue').Ref<boolean>,
 *   hasMore: import('vue').Ref<boolean>,
 *   error: import('vue').Ref<boolean>,
 *   fetch: (reset?: boolean) => Promise<void>,
 *   loadMore: () => void,
 * }}
 */
export function useWindowedList({ endpoint, buildParams, pageSize = 100 }) {
  const items = ref([])
  const total = ref(null)
  const loading = ref(false)
  const hasMore = ref(false)
  // A reset fetch that fails flags `error` instead of leaving total at 0 — that
  // would masquerade as "no results" (empty state) on a plain network outage.
  const error = ref(false)

  // Monotonic token: a filter change mid-flight bumps it so a stale response
  // (resolving after a newer request) is dropped instead of clobbering state.
  let token = 0

  async function fetch(reset = true) {
    const mine = ++token
    const skip = reset ? 0 : items.value.length
    loading.value = true
    try {
      const { data } = await api.get(endpoint, { params: buildParams(skip) })
      if (mine !== token) return
      items.value = reset ? data.items : [...items.value, ...data.items]
      total.value = data.total
      hasMore.value = items.value.length < data.total
      error.value = false
    } catch {
      if (mine === token && reset) {
        // Distinguish a failure from an empty result: clear the list, leave
        // total null (NOT 0), and flag error so the page shows a retry, not
        // the "no results" empty state. A loadMore failure keeps prior items.
        items.value = []
        total.value = null
        hasMore.value = false
        error.value = true
      }
    } finally {
      if (mine === token) loading.value = false
    }
  }

  function loadMore() {
    if (loading.value || !hasMore.value) return
    // Return the promise so a caller can await a page.
    return fetch(false)
  }

  // Scroll-restore fast path: reload the first `count` rows quickly instead of
  // walking pages one after another. Fires ceil(count / pageSize) requests (each
  // with the page's own baked limit, so offsets stay contiguous — no gaps) in
  // SEQUENTIAL batches of RESTORE_MAX_CONCURRENCY and stitches them in order.
  // Two caps: RESTORE_MAX_PAGES bounds the total pages (a very deep scroll can't
  // fan out unboundedly), RESTORE_MAX_CONCURRENCY bounds how many fire at once
  // (a heavy endpoint like /radar/feed can't recreate the OOM burst).
  const RESTORE_MAX_PAGES = 12
  const RESTORE_MAX_CONCURRENCY = 3
  async function fetchUpTo(count) {
    const mine = ++token
    loading.value = true
    const nPages = Math.min(RESTORE_MAX_PAGES, Math.max(1, Math.ceil(count / pageSize)))
    try {
      const pages = []
      for (let start = 0; start < nPages; start += RESTORE_MAX_CONCURRENCY) {
        const batch = await Promise.all(
          Array.from({ length: Math.min(RESTORE_MAX_CONCURRENCY, nPages - start) }, (_, j) =>
            api.get(endpoint, { params: buildParams((start + j) * pageSize) }),
          ),
        )
        // Re-check the token per batch: a filter change mid-burst supersedes this
        // restore, so drop the stale work before touching state.
        if (mine !== token) return
        pages.push(...batch)
      }
      const merged = pages.flatMap((p) => p.data.items)
      items.value = merged
      total.value = pages[0].data.total
      hasMore.value = merged.length < pages[0].data.total
      error.value = false
    } catch {
      if (mine === token) {
        items.value = []
        total.value = null
        hasMore.value = false
        error.value = true
      }
    } finally {
      if (mine === token) loading.value = false
    }
  }

  return { items, total, loading, hasMore, error, fetch, loadMore, fetchUpTo }
}
