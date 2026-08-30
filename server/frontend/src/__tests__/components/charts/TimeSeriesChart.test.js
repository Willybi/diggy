import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TimeSeriesChart from '../../../components/charts/TimeSeriesChart.vue'

const twoSeries = [
  {
    label: 'Deezer',
    color: 'var(--chart-deezer)',
    points: [
      { t: '2026-07-20', v: 50 },
      { t: '2026-07-21', v: 40 },
      { t: '2026-07-22', v: 30 },
    ],
  },
  {
    label: 'Beatport',
    color: 'var(--chart-beatport)',
    points: [
      { t: '2026-07-20', v: 200 },
      { t: '2026-07-21', v: 180 },
      { t: '2026-07-22', v: 150 },
    ],
  },
]

describe('TimeSeriesChart', () => {
  it('draws one line per series and a legend for ≥ 2 series', () => {
    const wrapper = mount(TimeSeriesChart, { props: { series: twoSeries } })
    expect(wrapper.findAll('.tsc-line')).toHaveLength(2)
    expect(wrapper.findAll('.tsc-leg')).toHaveLength(2)
    expect(wrapper.find('.state').exists()).toBe(false)
  })

  it('omits the legend for a single series', () => {
    const wrapper = mount(TimeSeriesChart, { props: { series: [twoSeries[0]] } })
    expect(wrapper.findAll('.tsc-line')).toHaveLength(1)
    expect(wrapper.find('.tsc-legend').exists()).toBe(false)
  })

  // D21/D22 re-style: no decorative gradient; the area fill is a flat 0.14 shape
  // drawn ONLY under the « total » curve, identified by its `-soft` colour token.
  it('renders an area fill only under the soft/total series when show-area is set', () => {
    const softBand = [
      {
        label: 'Deezer · total',
        color: 'var(--chart-deezer-soft)',
        points: [
          { t: '2026-07-20', v: 50 },
          { t: '2026-07-21', v: 40 },
        ],
      },
      {
        label: 'Deezer · à traiter',
        color: 'var(--chart-deezer)',
        points: [
          { t: '2026-07-20', v: 30 },
          { t: '2026-07-21', v: 20 },
        ],
      },
    ]
    const withArea = mount(TimeSeriesChart, {
      props: { series: softBand, showArea: true },
    })
    // Only the soft (total) series gets an area, not the full-colour "à traiter".
    expect(withArea.findAll('.tsc-area')).toHaveLength(1)
    const without = mount(TimeSeriesChart, { props: { series: softBand } })
    expect(without.findAll('.tsc-area')).toHaveLength(0)
  })

  it('shows an empty state and no lines when there is no data', () => {
    const wrapper = mount(TimeSeriesChart, { props: { series: [] } })
    expect(wrapper.find('.state').text()).toContain('Aucune donnée')
    expect(wrapper.findAll('.tsc-line')).toHaveLength(0)
  })

  it('handles a single sparse point without crashing', () => {
    const wrapper = mount(TimeSeriesChart, {
      props: {
        series: [
          { label: 'X', color: 'var(--chart-neutral)', points: [{ t: '2026-07-22', v: 5 }] },
        ],
      },
    })
    // One line path element exists (a lone "M" moveto); not the empty state.
    // Data-point dots were removed in the D21 re-style (archétype F: no markers).
    expect(wrapper.findAll('.tsc-line')).toHaveLength(1)
    expect(wrapper.find('.state').exists()).toBe(false)
  })

  it('applies yFormat to the axis labels', () => {
    const wrapper = mount(TimeSeriesChart, {
      props: { series: twoSeries, yFormat: (v) => `${Math.round(v)} u` },
    })
    expect(wrapper.find('.tsc-ylabel').text()).toContain('u')
  })
})
