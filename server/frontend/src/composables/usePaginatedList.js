import { ref, toValue } from 'vue'
import api from '../utils/api.js'
import { useInfiniteScroll } from './useInfiniteScroll.js'

/**
 * Drive a paginated card grid backed by infinite scroll.
 *
 * Absorbs the trunk shared by every listing view — the offset/hasMore
 * bookkeeping, the `{ sort, limit, offset }` params with optional `family`/`q`,
 * the append-vs-replace on reset, the reset-only error reset, the anti
 * double-fetch guard, and the sentinel wiring. The sort/family/query dimensions
 * are read reactively at fetch time, so the host view can map or derive them
 * (e.g. liked/disliked → tracks) without the composable knowing about it.
 *
 * The host keeps ownership of *when* to reset: it wires its own filter watchers
 * to `fetch(true)` and its SearchBox to `fetch(true)`. Non-paginated side modes
 * (opinion filters) live in the view and may write the returned refs directly.
 *
 * @param {object} opts
 * @param {string} opts.endpoint                 list URL (exact slash matters)
 * @param {number} [opts.pageSize=24]            rows per page
 * @param {import('vue').MaybeRefOrGetter<string>} opts.sort    sort value to send
 * @param {import('vue').MaybeRefOrGetter<string>} [opts.family]  'all' → omitted
 * @param {import('vue').MaybeRefOrGetter<string>} [opts.query]   trimmed, empty → omitted
 * @returns {{
 *   items: import('vue').Ref<any[]>,
 *   total: import('vue').Ref<number>,
 *   familyCounts: import('vue').Ref<Record<string, number>>,
 *   loading: import('vue').Ref<boolean>,
 *   offset: import('vue').Ref<number>,
 *   hasMore: import('vue').Ref<boolean>,
 *   sentinel: import('vue').Ref<HTMLElement | null>,
 *   fetch: (reset?: boolean) => Promise<void>,
 *   loadMore: () => void,
 * }}
 */
export function usePaginatedList({ endpoint, pageSize = 24, sort, family, query }) {
  const items = ref([])
  const total = ref(0)
  const familyCounts = ref({})
  const loading = ref(false)
  const offset = ref(0)
  const hasMore = ref(false)

  async function fetch(reset = true) {
    if (reset) {
      offset.value = 0
      items.value = []
    }
    loading.value = true
    try {
      const params = {
        sort: toValue(sort),
        limit: pageSize,
        offset: offset.value,
      }
      const fam = toValue(family)
      if (fam && fam !== 'all') params.family = fam
      const q = (toValue(query) || '').trim()
      if (q) params.q = q

      const { data } = await api.get(endpoint, { params })
      items.value = reset ? data.items : [...items.value, ...data.items]
      total.value = data.total
      familyCounts.value = data.pillarCounts || {}
      hasMore.value = items.value.length < data.total
    } catch {
      if (reset) items.value = []
    } finally {
      loading.value = false
    }
  }

  function loadMore() {
    if (loading.value || !hasMore.value) return
    offset.value = items.value.length
    fetch(false)
  }

  const { sentinel } = useInfiniteScroll(loadMore)

  return { items, total, familyCounts, loading, offset, hasMore, sentinel, fetch, loadMore }
}
