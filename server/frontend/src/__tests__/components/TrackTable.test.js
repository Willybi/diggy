import { describe, it, expect } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import { h } from 'vue'
import TrackTable from '../../components/TrackTable.vue'

// TrackTable is the shared, presentational virtualised table extracted from
// Explorer & Radar (A4-01). It renders the thead, the visible row slice, the
// skeleton and the empty/error states, and reports intents as events. These
// tests drive it in isolation (no view, no fetch, no composables).

function makeRow(overrides = {}) {
  return {
    id: 1,
    title: 'Alpha',
    artist: 'Kaskade',
    artist_id: 10,
    artists: [{ id: 10, name: 'Kaskade' }],
    genres: [
      { name: 'House', pillar: 'house', depth: 0 },
      { name: 'Tech House', pillar: 'house', depth: 1 },
    ],
    style: null,
    bpm: 128.4,
    key: '5A',
    duration_ms: 245000,
    has_artwork: false,
    has_preview: true,
    in_lib: true,
    avis: null,
    trend_rank: 14,
    ...overrides,
  }
}

function mountTable(props = {}, slots = {}) {
  return mount(TrackTable, {
    props: {
      variant: 'explorer',
      windowItems: [makeRow()],
      items: [makeRow()],
      ...props,
    },
    slots,
    // vue-router isn't mocked here: register the stub so the style-link
    // RouterLink + ArtistLinks resolve (repo pitfall: string stubs are no-ops).
    global: { components: { RouterLink: RouterLinkStub } },
  })
}

describe('TrackTable', () => {
  it('applies the variant layout class', () => {
    expect(mountTable({ variant: 'explorer' }).find('.tt-table--explorer').exists()).toBe(true)
    expect(mountTable({ variant: 'radar' }).find('.tt-table--radar').exists()).toBe(true)
  })

  it('renders the sortable header in its sorted state with the arrow glyph', () => {
    const w = mountTable({
      trackSortable: true,
      keySortable: true,
      showDuration: true,
      sort: 'bpm',
      arrow: '↓',
    })
    const bpm = w.find('.tt-th--btn.col-bpm')
    expect(bpm.classes()).toContain('is-sorted')
    expect(bpm.find('.tt-arr').text()).toBe('↓')
    // The non-active headers carry no arrow and no sorted state.
    expect(w.find('.tt-th--btn.col-key').classes()).not.toContain('is-sorted')
    expect(w.find('.tt-th--btn.col-key .tt-arr').exists()).toBe(false)
  })

  it('renders Track/Key as plain (non-button) headers when not sortable', () => {
    const w = mountTable({ trackSortable: false, keySortable: false })
    // Only BPM stays a sortable button; Track & Key are plain spans.
    expect(w.findAll('.tt-thead .tt-th--btn')).toHaveLength(1)
    expect(w.find('.tt-th--btn.col-bpm').exists()).toBe(true)
  })

  it('emits header-sort with the column field on a header click', async () => {
    const w = mountTable({ trackSortable: true, keySortable: true, showDuration: true })
    await w.find('.tt-th--btn.col-bpm').trigger('click')
    await w.find('.tt-th--btn.col-key').trigger('click')
    await w.find('.tt-th--btn.col-dur').trigger('click')
    expect(w.emitted('header-sort')).toEqual([['bpm'], ['key'], ['duration_ms']])
  })

  it('renders a data row: title, #rank, bpm rounded, key, « +N » styles, play button', () => {
    const w = mountTable({ showDuration: true })
    const row = w.find('.tt-row:not(.tt-row--skel)')
    expect(row.text()).toContain('Alpha')
    expect(row.find('.tt-rank').text()).toBe('#14')
    expect(row.find('.tt-bpm').text()).toBe('128')
    expect(row.find('.tt-key').text()).toBe('5A')
    expect(row.find('.tt-more').text()).toBe('+1')
    expect(row.find('.tt-pbtn').exists()).toBe(true)
  })

  it('shows « — » for null bpm/key and no play button without a preview', () => {
    const w = mountTable({
      windowItems: [makeRow({ bpm: null, key: null, genres: [], has_preview: false })],
    })
    const row = w.find('.tt-row:not(.tt-row--skel)')
    expect(row.findAll('.tt-null').length).toBeGreaterThanOrEqual(3)
    expect(row.find('.tt-pbtn').exists()).toBe(false)
  })

  it('prefixes an estimated bpm (bpm_source=analysis) with a ~', () => {
    const w = mountTable({ windowItems: [makeRow({ bpm: 124, bpm_source: 'analysis' })] })
    const bpm = w.find('.tt-row:not(.tt-row--skel) .tt-bpm')
    expect(bpm.find('.tt-bpm-est').exists()).toBe(true)
    expect(bpm.text()).toBe('~124')
  })

  it('emits row-click on the row and play on the play button (stopped)', async () => {
    const w = mountTable()
    const row = w.find('.tt-row:not(.tt-row--skel)')
    await row.trigger('click')
    expect(w.emitted('row-click')[0][0].id).toBe(1)
    await row.find('.tt-pbtn').trigger('click')
    expect(w.emitted('play')[0][0].id).toBe(1)
    // The play click is stopped: it does not also fire a second row-click.
    expect(w.emitted('row-click')).toHaveLength(1)
  })

  it('emits avis (row, value) from the LikeDislike control', async () => {
    const w = mountTable()
    await w.find('.tt-row:not(.tt-row--skel) .ld-btn.like').trigger('click')
    expect(w.emitted('avis')[0][0].id).toBe(1)
    expect(w.emitted('avis')[0][1]).toBe('liked')
  })

  it('colors liked/disliked rows and flags the current+playing row', () => {
    expect(
      mountTable({ windowItems: [makeRow({ avis: 'liked' })] })
        .find('.tt-row:not(.tt-row--skel)')
        .classes(),
    ).toContain('liked')

    const playing = mountTable({ isCurrent: (id) => id === 1, playing: true })
    const row = playing.find('.tt-row:not(.tt-row--skel)')
    expect(row.classes()).toContain('playing')
    expect(row.find('.tt-pbtn').classes()).toContain('tt-pbtn--playing')
    // Playing → the pause icon (two rects), not the play triangle.
    expect(row.find('.tt-pbtn').findAll('rect')).toHaveLength(2)
  })

  it('renders the injected extra columns through the head-extra / row-extra slots', () => {
    const w = mount(TrackTable, {
      props: {
        variant: 'radar',
        windowItems: [makeRow({ trend_score_10: 9 })],
        items: [makeRow()],
        sort: 'tendance',
      },
      slots: {
        'head-extra': () => h('button', { class: 'rd-th--score col-trend' }, 'Tendance'),
        'row-extra': ({ row }) => h('span', { class: 'col-trend' }, String(row.trend_score_10)),
      },
      global: { components: { RouterLink: RouterLinkStub } },
    })
    // The slotted header sits in the grid before Avis; the slotted cell carries
    // the row-scoped data.
    expect(w.find('.tt-thead .rd-th--score.col-trend').text()).toBe('Tendance')
    expect(w.find('.tt-row:not(.tt-row--skel) .col-trend').text()).toBe('9')
  })

  it('renders 8 skeleton rows including the extra-column ghosts while loading', () => {
    const w = mount(TrackTable, {
      props: { variant: 'radar', initialLoading: true, extraSkeleton: ['disc', 'disc'] },
      global: { components: { RouterLink: RouterLinkStub } },
    })
    const skels = w.findAll('.tt-row--skel')
    expect(skels).toHaveLength(8)
    expect(skels[0].findAll('.sk-disc')).toHaveLength(2)
    // No real rows while loading.
    expect(w.find('.tt-row:not(.tt-row--skel)').exists()).toBe(false)
  })

  it('shows the error state and emits retry', async () => {
    const w = mountTable({ isError: true })
    expect(w.find('.tt-empty').text()).toContain('Erreur de chargement')
    await w.find('.tt-empty .btn').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })

  it('shows the empty state with repair chips and emits remove-chip / reset', async () => {
    const w = mountTable({
      isEmpty: true,
      activeChips: [{ id: 'c1', key: 'genre', label: 'Style', value: 'House', rawValue: 'House' }],
    })
    expect(w.find('.tt-empty').text()).toContain('Aucun résultat')
    await w.find('.fchip--empty').trigger('click')
    expect(w.emitted('remove-chip')[0][0].id).toBe('c1')
    await w.find('.tt-empty .btn').trigger('click')
    expect(w.emitted('reset')).toHaveLength(1)
  })
})
