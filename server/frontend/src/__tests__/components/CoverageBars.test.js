import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import CoverageBars from '../../components/charts/CoverageBars.vue'

// Nominal coverage payload (L1 snapshot shape). Counts kept < 1000 so the
// fr-FR thousands separator never interferes with text assertions.
const sampleCoverage = () => ({
  total: 200,
  deezer: { linked: 120, abandoned: 10 },
  beatport: { linked: 80, abandoned: 5 },
  bpm: { beatport: 60, rekordbox: 30, analysis: 10 },
  key: { beatport: 50, rekordbox: 20 },
  preview: { covered: 150 },
  artwork: { covered: 180 },
  genres: { covered: 170 },
  embedding: { covered: 120 },
  artist_link: { covered: 190 },
  album: { covered: 80 },
  completeness: { 0: 2, 1: 3, 2: 5, 3: 5, 4: 5, 5: 10, 6: 20, 7: 50, 8: 100 },
  top_combos: [
    {
      dims: {
        deezer: true,
        beatport: false,
        bpm: false,
        key: false,
        genres: true,
        artwork: true,
        embedding: false,
        artist_link: true,
      },
      count: 40,
    },
    {
      dims: {
        deezer: true,
        beatport: true,
        bpm: true,
        key: true,
        genres: true,
        artwork: true,
        embedding: false,
        artist_link: true,
      },
      count: 20,
    },
  ],
})

describe('CoverageBars', () => {
  it('renders the completeness buckets, the per-dimension bars and the top combos', () => {
    const wrapper = mount(CoverageBars, { props: { coverage: sampleCoverage() } })

    // ── Complétude globale : 4 buckets with label + % + count in the legend.
    expect(wrapper.text()).toContain('Complétude globale')
    const legend = wrapper.find('.cb-legend').text()
    expect(legend).toContain('8/8 complet')
    expect(legend).toContain('7/8')
    expect(legend).toContain('5-6/8')
    expect(legend).toContain('≤4/8')
    // 100/200 complete → 50 %; ≤4 bucket = 2+3+5+5+5 = 20 → 10 %.
    expect(legend).toContain('50 %')
    expect(legend).toContain('(100)')
    expect(legend).toContain('10 %')
    expect(legend).toContain('(20)')
    // The global bar carries one segment per bucket.
    expect(wrapper.findAll('.cb-global .cb-seg')).toHaveLength(4)

    // ── Per-dimension rows: the 10 French labels, in order.
    const rows = wrapper.findAll('.cb-row')
    expect(rows).toHaveLength(10)
    const labels = rows.map((r) => r.find('.cb-row-label').text())
    expect(labels).toEqual([
      'Deezer',
      'Beatport',
      'BPM',
      'Key',
      'Genres',
      'Pochettes',
      'Embeddings',
      'Artiste lié',
      'Preview',
      'Album',
    ])
    // Deezer: linked + abandoned = 2 segments; % + count text (120/200 = 60 %).
    const deezerRow = rows[0]
    expect(deezerRow.findAll('.cb-seg')).toHaveLength(2)
    expect(deezerRow.find('.cb-row-val').text()).toContain('60 %')
    expect(deezerRow.find('.cb-row-val').text()).toContain('120')
    // The abandoned segment carries a describing title (hover detail).
    const segTitles = deezerRow.findAll('.cb-seg').map((s) => s.attributes('title'))
    expect(segTitles.some((t) => t.includes('abandonnés'))).toBe(true)
    // BPM: one segment per source (3), covered = 100/200 → 50 %.
    const bpmRow = rows[2]
    expect(bpmRow.findAll('.cb-seg')).toHaveLength(3)
    expect(bpmRow.find('.cb-row-val').text()).toContain('50 %')
    // Single-dim row (Embeddings 120/200 → 60 %).
    expect(rows[6].findAll('.cb-seg')).toHaveLength(1)
    expect(rows[6].find('.cb-row-val').text()).toContain('60 %')

    // ── Top combos: 2 entries × 8 ✓/✗ chips + proportional bar + count.
    const combos = wrapper.findAll('.cb-combo')
    expect(combos).toHaveLength(2)
    const first = combos[0]
    expect(first.findAll('.cb-chip')).toHaveLength(8)
    // First combo misses beatport/bpm/key/embedding → 4 miss chips, 4 ok.
    expect(first.findAll('.cb-chip--miss')).toHaveLength(4)
    expect(first.findAll('.cb-chip--ok')).toHaveLength(4)
    expect(first.text()).toContain('✓')
    expect(first.text()).toContain('✗')
    expect(first.text()).toContain('40')
    // Bar proportional to the max count: first = 100 %, second = 50 %.
    expect(first.find('.cb-combo-fill').attributes('style')).toContain('width: 100%')
    expect(combos[1].find('.cb-combo-fill').attributes('style')).toContain('width: 50%')
  })

  it('formats a tiny non-zero share as <1 %', () => {
    const wrapper = mount(CoverageBars, {
      props: {
        coverage: { total: 1000, embedding: { covered: 3 } },
      },
    })
    expect(wrapper.find('.cb-row-val').text()).toContain('<1 %')
  })

  it('renders without crashing when the prop is absent', () => {
    const wrapper = mount(CoverageBars)
    expect(wrapper.text()).toContain('Aucune donnée de couverture.')
    expect(wrapper.findAll('.cb-row')).toHaveLength(0)
  })

  it('renders without crashing on an empty object', () => {
    const wrapper = mount(CoverageBars, { props: { coverage: {} } })
    expect(wrapper.text()).toContain('Aucune donnée de couverture.')
  })

  it('renders without crashing on a partial payload (total only + malformed keys)', () => {
    const wrapper = mount(CoverageBars, {
      props: {
        coverage: {
          total: 100,
          deezer: { linked: 60 }, // no abandoned key
          bpm: {}, // empty by-source dict → all-missing bar, no segment
          completeness: null,
          top_combos: [{ dims: null, count: 5 }, null],
        },
      },
    })
    // Deezer row renders (single linked segment), malformed blocks are skipped.
    const rows = wrapper.findAll('.cb-row')
    expect(rows.length).toBeGreaterThanOrEqual(1)
    expect(rows[0].find('.cb-row-label').text()).toBe('Deezer')
    expect(rows[0].findAll('.cb-seg')).toHaveLength(1)
    expect(wrapper.findAll('.cb-combo')).toHaveLength(0)
    expect(wrapper.find('.cb-legend').exists()).toBe(false)
  })
})
