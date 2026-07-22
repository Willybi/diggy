import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Mock the API client so onMounted's fetch resolves to a fixture.
const { apiMock } = vi.hoisted(() => ({ apiMock: { get: vi.fn() } }))
vi.mock('../../utils/api.js', () => ({ default: apiMock }))

import AdminMonitoring from '../../components/admin/AdminMonitoring.vue'
import TimeSeriesChart from '../../components/charts/TimeSeriesChart.vue'
import StatTile from '../../components/charts/StatTile.vue'

// A representative MonitoringResponse: 3 hourly snapshots (full enrich buckets),
// throughput across 2 days × 2 sources, and a couple of last-run rows.
function sampleResponse() {
  const snap = (iso, dz, bp, cat) => ({
    captured_at: iso,
    payload: {
      enrich: {
        deezer: {
          never_tried: dz,
          due_retry: 2,
          cooldown: 1,
          abandoned: 0,
          total_missing: dz + 3,
          total_linked: 100,
        },
        beatport: {
          never_tried: bp,
          due_retry: 5,
          cooldown: 3,
          abandoned: 1,
          total_missing: bp + 9,
          total_linked: 60,
        },
      },
      artists: { backlog_link: 4, backlog_artwork: 7 },
      sets: { recrawl_backlog: 2 },
      catalog: { total: cat },
    },
  })
  return {
    backlog_series: [
      snap('2026-07-20T05:00:00Z', 50, 200, 6000),
      snap('2026-07-21T05:00:00Z', 40, 180, 6050),
      snap('2026-07-22T05:00:00Z', 30, 150, 6120),
    ],
    throughput_series: [
      {
        day: '2026-07-21',
        task_type: 'enrich_catalog',
        source: 'deezer',
        runs: 2,
        errors: 0,
        enriched: 8,
        not_found: 2,
        merged: 1,
        hit_rate: 0.8,
        duration_ms_avg: 4000,
        duration_ms_max: 5000,
      },
      {
        day: '2026-07-21',
        task_type: 'enrich_beatport',
        source: 'beatport',
        runs: 1,
        errors: 1,
        enriched: 3,
        not_found: 7,
        merged: 0,
        hit_rate: 0.3,
        duration_ms_avg: 9000,
        duration_ms_max: 12000,
      },
      {
        day: '2026-07-22',
        task_type: 'enrich_catalog',
        source: 'deezer',
        runs: 1,
        errors: 0,
        enriched: 6,
        not_found: 4,
        merged: 0,
        hit_rate: 0.6,
        duration_ms_avg: 3500,
        duration_ms_max: 4200,
      },
    ],
    status: {
      last_runs: [
        {
          task_type: 'enrich_catalog',
          source: 'deezer',
          status: 'success',
          started_at: '2026-07-22T05:00:00Z',
          finished_at: '2026-07-22T05:00:05Z',
          duration_ms: 4200,
        },
        {
          task_type: 'enrich_beatport',
          source: 'beatport',
          status: 'running',
          started_at: '2026-07-22T06:00:00Z',
          finished_at: null,
          duration_ms: null,
        },
      ],
      latest_snapshot: {
        captured_at: '2026-07-22T05:00:00Z',
        payload: {
          enrich: {
            deezer: {
              never_tried: 30,
              due_retry: 2,
              cooldown: 1,
              abandoned: 0,
              total_missing: 33,
              total_linked: 100,
            },
            beatport: {
              never_tried: 150,
              due_retry: 5,
              cooldown: 3,
              abandoned: 1,
              total_missing: 159,
              total_linked: 60,
            },
          },
          artists: { backlog_link: 4, backlog_artwork: 7 },
          sets: { recrawl_backlog: 2 },
          catalog: { total: 6120 },
        },
      },
    },
  }
}

const emptyResponse = () => ({
  backlog_series: [],
  throughput_series: [],
  status: { last_runs: [], latest_snapshot: null },
})

describe('AdminMonitoring', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
  })

  it('renders KPI tiles and the three time-series charts from the payload', async () => {
    apiMock.get.mockResolvedValue({ data: sampleResponse() })
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    // Fetched once on mount.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/monitoring', {
      params: { days: 30 },
    })

    // Stat tiles present (2 sources + artists + sets + catalog + errors/durations…).
    const tiles = wrapper.findAllComponents(StatTile)
    expect(tiles.length).toBeGreaterThanOrEqual(6)

    // Three charts: burn-down + débit + hit-rate.
    expect(wrapper.findAllComponents(TimeSeriesChart)).toHaveLength(3)

    // Deezer backlog total_missing (33) surfaced in a tile.
    expect(wrapper.text()).toContain('33')
    // Beatport source label present.
    expect(wrapper.text()).toContain('Beatport')
    // A running enrich → lock indicator.
    expect(wrapper.find('.lock-chip').exists()).toBe(true)

    // Charts actually drew lines (not the empty state).
    expect(wrapper.findAll('.tsc-line').length).toBeGreaterThan(0)
    expect(wrapper.find('.run-list').exists()).toBe(true)
  })

  it('renders without error and shows empty states when every series is empty', async () => {
    apiMock.get.mockResolvedValue({ data: emptyResponse() })
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    // No crash; still shows the three charts, each in their empty state.
    expect(wrapper.findAllComponents(TimeSeriesChart)).toHaveLength(3)
    expect(wrapper.text()).toContain('Aucune donnée sur la période.')
    // No lock chip, no run rows.
    expect(wrapper.find('.lock-chip').exists()).toBe(false)
    expect(wrapper.find('.run-list').exists()).toBe(false)
    // Tiles still render with an em-dash placeholder for missing values.
    expect(wrapper.findAllComponents(StatTile).length).toBeGreaterThan(0)
  })

  it('shows an error state when the fetch fails', async () => {
    apiMock.get.mockRejectedValue(new Error('boom'))
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    expect(wrapper.text()).toContain('Impossible de charger le monitoring.')
    expect(wrapper.findComponent(TimeSeriesChart).exists()).toBe(false)
  })
})
