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
export function useWindowedList({ endpoint, buildParams }) {
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
    fetch(false)
  }

  return { items, total, loading, hasMore, error, fetch, loadMore }
}
