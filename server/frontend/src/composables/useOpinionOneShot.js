import { ref } from 'vue'
import api from '../utils/api.js'
import { useOpinionsStore } from '../stores/opinions.js'

/**
 * Drive the « filtre par avis » one-shot shared by the listing views that own a
 * paginated trunk (ArtistsView / SetsView / WatchlistView).
 *
 * Those views browse through usePaginatedList (infinite scroll) in their normal
 * mode, but the opinion facets (liked / disliked / « à explorer ») are NOT
 * paginated: they resolve the matching id set from the opinions store and fire a
 * single non-paginated request, writing the trunk's own refs directly (the mode
 * the usePaginatedList docblock calls a "side mode"). That block was copy-pasted
 * verbatim across the three views; this composable is the one copy.
 *
 * It stays agnostic of the row rendering (ArtistsView is a card grid, the other
 * two are tables): the host supplies the endpoint, the opinions `kind`, and a
 * `buildParams()` that returns the base request params (sort / limit / offset /
 * query / extra) WITHOUT the id clause — this composable appends `ids=` (liked /
 * disliked) or `exclude_ids=` (the optional « unrated » value). It writes the
 * refs the host passes in (`items` / `total` / `hasMore`, plus `loading` when
 * given) and exposes `capped` for the silent-truncation fix (see below).
 *
 * Silent cap: the one-shot sends a fixed `limit` (100 / 200) with `hasMore=false`,
 * so past that ceiling the list was truncated with NO indicator. The backend
 * still returns the true match count in `data.total`, so after the fetch
 * `capped = data.total > data.items.length`; the host surfaces « N premiers
 * affichés » from it. (Pagination was rejected: the three views deliberately keep
 * the sentinel OFF in opinion mode — an indicator honours that contract.)
 *
 * Error / empty handling mirrors the twins: a thrown request empties the refs
 * (`items=[]`, `total=0`, `hasMore=false`); a liked/disliked facet with no
 * matching id short-circuits to the same empty state WITHOUT a request; the
 * « unrated » facet with nothing rated sends no `exclude_ids` and returns the
 * whole corpus.
 *
 * @param {object} opts
 * @param {string} opts.endpoint      list URL (exact slash matters)
 * @param {string} opts.kind          opinions store key: 'artist' | 'set' | 'playlist'
 * @param {object} opts.refs          trunk refs written in place
 * @param {import('vue').Ref<any[]>}   opts.refs.items
 * @param {import('vue').Ref<number>}  opts.refs.total
 * @param {import('vue').Ref<boolean>} opts.refs.hasMore
 * @param {import('vue').Ref<boolean>} [opts.refs.loading]  toggled true/false around the fetch
 * @param {() => Record<string, any>} opts.buildParams  base params (sort / limit /
 *        offset / q / extra), read fresh at call time. The id clause is added here.
 * @param {string} [opts.unratedValue]  opinion value meaning « exclude every rated
 *        row » (e.g. 'none' / 'unrated'). Omit on a view without that facet (Artists).
 * @param {(data: any) => void} [opts.onData]  optional hook for a view-specific
 *        field written from the response (e.g. ArtistsView's familyCounts).
 * @returns {{ run: (opinion: string) => Promise<void>, capped: import('vue').Ref<boolean> }}
 */
export function useOpinionOneShot({
  endpoint,
  kind,
  refs,
  buildParams,
  unratedValue = null,
  onData = null,
}) {
  const opinions = useOpinionsStore()
  const capped = ref(false)

  async function run(opinion) {
    const { items, total, hasMore, loading } = refs
    items.value = []
    capped.value = false
    if (loading) loading.value = true
    try {
      await opinions.load()
      const map = opinions.data[kind] || {}
      const params = buildParams()

      if (unratedValue != null && opinion === unratedValue) {
        // « À explorer » : exclude every rated (liked ∪ disliked) id. Nothing
        // rated → no exclude param, so the endpoint returns the full corpus.
        const ratedIds = Object.keys(map).filter((k) => map[k] === 'liked' || map[k] === 'disliked')
        if (ratedIds.length) params.exclude_ids = ratedIds.join(',')
      } else {
        // liked / disliked : pass the matching ids. No match → empty, no request.
        const matchingIds = Object.entries(map)
          .filter(([, v]) => v === opinion)
          .map(([k]) => k)
        if (!matchingIds.length) {
          total.value = 0
          hasMore.value = false
          return
        }
        params.ids = matchingIds.join(',')
      }

      const { data } = await api.get(endpoint, { params })
      items.value = data.items
      total.value = data.total
      hasMore.value = false
      // True match count exceeds the single page → the list is truncated.
      capped.value = data.total > data.items.length
      if (onData) onData(data)
    } catch {
      items.value = []
      total.value = 0
      hasMore.value = false
    } finally {
      if (loading) loading.value = false
    }
  }

  return { run, capped }
}
