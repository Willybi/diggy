import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Mock the API client so the split onMounted fetches resolve to fixtures.
const { apiMock } = vi.hoisted(() => ({ apiMock: { get: vi.fn() } }))
vi.mock('../../utils/api.js', () => ({ default: apiMock }))

import AdminMonitoring from '../../components/admin/AdminMonitoring.vue'
import CoverageBars from '../../components/charts/CoverageBars.vue'
import TimeSeriesChart from '../../components/charts/TimeSeriesChart.vue'
import StatTile from '../../components/charts/StatTile.vue'

// L4 split: GET /admin/monitoring returns the instant status (+integrity at
// the root), GET /admin/monitoring/series returns the two time-series.

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

function sampleStatusResponse() {
  return {
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
          sets: { recrawl_backlog: 2, unreliable: 42 },
          catalog: { total: 6120, bpm_missing: 800 },
          albums: { missing_cover: 120, missing_meta: 80, total: 500 },
          embeddings: { covered: 600, eligible: 1000, missing: 400 },
          coverage: sampleCoverage(),
        },
      },
    },
    integrity: {
      artist_divergence: 2,
      missing_m2m_link: 29101,
    },
  }
}

// 3 hourly snapshots (full enrich buckets) + throughput across 2 days × 2 sources.
function sampleSeriesResponse() {
  const snap = (iso, dz, bp, cat, bpm, embCovered) => ({
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
      sets: { recrawl_backlog: 2, unreliable: 42 },
      catalog: { total: cat, bpm_missing: bpm },
      albums: { missing_cover: 120, missing_meta: 80, total: 500 },
      embeddings: { covered: embCovered, eligible: 1000, missing: 1000 - embCovered },
    },
  })
  return {
    backlog_series: [
      snap('2026-07-20T05:00:00Z', 50, 200, 6000, 900, 200),
      snap('2026-07-21T05:00:00Z', 40, 180, 6050, 850, 400),
      snap('2026-07-22T05:00:00Z', 30, 150, 6120, 800, 600),
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
  }
}

const emptyStatusResponse = () => ({
  status: { last_runs: [], latest_snapshot: null },
  integrity: null,
})
const emptySeriesResponse = () => ({ backlog_series: [], throughput_series: [] })

// Route the mocked GET by URL (split endpoints).
function mockBoth(statusResp, seriesResp) {
  apiMock.get.mockImplementation((url) => {
    if (url === '/api/admin/monitoring') return Promise.resolve({ data: statusResp })
    if (url === '/api/admin/monitoring/series') return Promise.resolve({ data: seriesResp })
    return Promise.reject(new Error(`unexpected url ${url}`))
  })
}
const callsTo = (url) => apiMock.get.mock.calls.filter(([u]) => u === url)

describe('AdminMonitoring', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
  })

  it('renders KPI tiles and the five time-series charts from the two split payloads', async () => {
    mockBoth(sampleStatusResponse(), sampleSeriesResponse())
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    // One fetch per endpoint on mount: status without params, series with days.
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/monitoring')
    expect(apiMock.get).toHaveBeenCalledWith('/api/admin/monitoring/series', {
      params: { days: 30 },
    })

    // Stat tiles present (2 sources + artists + sets + catalog + errors/durations…).
    const tiles = wrapper.findAllComponents(StatTile)
    expect(tiles.length).toBeGreaterThanOrEqual(6)

    // Five charts: 3 themed burn-downs (platform / content / residual) + débit
    // + hit-rate.
    const charts = wrapper.findAllComponents(TimeSeriesChart)
    expect(charts).toHaveLength(5)
    const labelsOf = (i) => charts[i].props('series').map((s) => s.label)
    const platformLabels = labelsOf(0)
    const contentLabels = labelsOf(1)
    const residualLabels = labelsOf(2)

    // Deezer backlog total_missing (33) surfaced in a tile.
    expect(wrapper.text()).toContain('33')
    // Beatport source label present.
    expect(wrapper.text()).toContain('Beatport')
    // A running enrich → lock indicator.
    expect(wrapper.find('.lock-chip').exists()).toBe(true)

    // Charts actually drew lines (not the empty state).
    expect(wrapper.findAll('.tsc-line').length).toBeGreaterThan(0)
    // D21: the "Dernier passage par tâche" list is now the shared .at-* table.
    expect(wrapper.find('.at-table').exists()).toBe(true)
    expect(wrapper.findAll('.at-table tbody tr').length).toBe(2)

    // A · Platform chart carries the 2-tone Deezer/Beatport band, NOT the
    // content/residual series.
    expect(platformLabels).toContain('Deezer · total')
    expect(platformLabels).toContain('Beatport · à traiter')
    expect(platformLabels).not.toContain('BPM · à analyser')

    // B · Content chart: C9 embeddings + E2.c BPM + C7 album metadata.
    expect(contentLabels).toContain('Embeddings · à vectoriser')
    expect(contentLabels).toContain('BPM · à analyser')
    expect(contentLabels).toContain('Albums · métadonnées')

    // C · Residual chart: album covers (C7/L8) + unreliable sets (C8).
    expect(residualLabels).toContain('Albums · covers manquantes')
    expect(residualLabels).toContain('Sets · non fiables')

    // C9.a: embeddings backlog surfaced as a tile (missing 400 + coverage %).
    expect(wrapper.text()).toContain('Embeddings à vectoriser')
    expect(wrapper.text()).toContain('60 % couverts')

    // C8: unreliable-sets count surfaced as a tile (42).
    expect(wrapper.text()).toContain('Sets non fiables')
    expect(wrapper.text()).toContain('42')

    // C7/L8: album backlog surfaced as tiles (missing_cover 120).
    expect(wrapper.text()).toContain('Covers albums manquantes')
    expect(wrapper.text()).toContain('Métadonnées albums')
    expect(wrapper.text()).toContain('120')

    // X4.d: artist-integrity counters surfaced as tiles (integrity now at the
    // root of the status response).
    expect(wrapper.text()).toContain('Intégrité artiste')
    expect(wrapper.text()).toContain('Divergence artiste')
    expect(wrapper.text()).toContain('Sans lien artiste')
    // artist_divergence value (2) rendered.
    expect(wrapper.text()).toContain('2')

    // L4: the data-coverage section renders CoverageBars from the snapshot.
    expect(wrapper.text()).toContain('Couverture des données')
    const cov = wrapper.findComponent(CoverageBars)
    expect(cov.exists()).toBe(true)
    expect(cov.props('coverage').total).toBe(200)
  })

  it('renders the status zone while the series are still loading (chart skeletons, no crash)', async () => {
    // Status resolves immediately; the series promise stays pending.
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/admin/monitoring') {
        return Promise.resolve({ data: sampleStatusResponse() })
      }
      return new Promise(() => {})
    })
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    // The status-driven zone is already rendered (tiles, coverage, runs table).
    expect(wrapper.findAllComponents(StatTile).length).toBeGreaterThan(0)
    expect(wrapper.find('.at-table').exists()).toBe(true)
    expect(wrapper.findComponent(CoverageBars).exists()).toBe(true)

    // The chart sections show their own loading state — no chart mounted yet.
    expect(wrapper.findAllComponents(TimeSeriesChart)).toHaveLength(0)
    expect(wrapper.findAll('.state--chart').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('Chargement des courbes…')

    // Series-derived tiles degrade to a placeholder instead of a bogus 0.
    expect(wrapper.text()).toContain('Erreurs (période)')
    expect(wrapper.text()).not.toContain('sur 0 runs')
  })

  it('changing the window refetches only the series; Rafraîchir refetches both', async () => {
    mockBoth(sampleStatusResponse(), sampleSeriesResponse())
    const wrapper = mount(AdminMonitoring)
    await flushPromises()
    expect(callsTo('/api/admin/monitoring')).toHaveLength(1)
    expect(callsTo('/api/admin/monitoring/series')).toHaveLength(1)

    await wrapper.find('select.mon-select').setValue(7)
    await flushPromises()
    expect(callsTo('/api/admin/monitoring')).toHaveLength(1)
    expect(callsTo('/api/admin/monitoring/series')).toHaveLength(2)
    expect(callsTo('/api/admin/monitoring/series')[1][1]).toEqual({ params: { days: 7 } })

    await wrapper.find('.mon-refresh').trigger('click')
    await flushPromises()
    expect(callsTo('/api/admin/monitoring')).toHaveLength(2)
    expect(callsTo('/api/admin/monitoring/series')).toHaveLength(3)
  })

  it('hides the integrity and coverage sections when the snapshot does not carry them', async () => {
    // Pre-deploy snapshot: no coverage key in the payload, integrity null.
    const status = sampleStatusResponse()
    delete status.status.latest_snapshot.payload.coverage
    status.integrity = null
    mockBoth(status, sampleSeriesResponse())
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    expect(wrapper.text()).not.toContain('Intégrité artiste')
    expect(wrapper.text()).not.toContain('Couverture des données')
    expect(wrapper.findComponent(CoverageBars).exists()).toBe(false)
    // The rest of the page still renders.
    expect(wrapper.findAllComponents(TimeSeriesChart)).toHaveLength(5)
  })

  it('renders without error and shows empty states when every series is empty', async () => {
    mockBoth(emptyStatusResponse(), emptySeriesResponse())
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    // No crash; still shows the five charts, each in their empty state.
    expect(wrapper.findAllComponents(TimeSeriesChart)).toHaveLength(5)
    expect(wrapper.text()).toContain('Aucune donnée sur la période.')
    // No lock chip, no run rows (empty state instead of the .at-* table body).
    expect(wrapper.find('.lock-chip').exists()).toBe(false)
    expect(wrapper.find('.at-table').exists()).toBe(false)
    expect(wrapper.find('.at-empty').exists()).toBe(true)
    // Tiles still render with an em-dash placeholder for missing values.
    expect(wrapper.findAllComponents(StatTile).length).toBeGreaterThan(0)
  })

  it('shows an error state when the status fetch fails', async () => {
    apiMock.get.mockRejectedValue(new Error('boom'))
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    expect(wrapper.text()).toContain('Impossible de charger le monitoring.')
    expect(wrapper.findComponent(TimeSeriesChart).exists()).toBe(false)
  })

  it('keeps the status zone and shows a per-section error when only the series fetch fails', async () => {
    apiMock.get.mockImplementation((url) => {
      if (url === '/api/admin/monitoring') {
        return Promise.resolve({ data: sampleStatusResponse() })
      }
      return Promise.reject(new Error('series boom'))
    })
    const wrapper = mount(AdminMonitoring)
    await flushPromises()

    // The zone renders from the status; the chart sections carry the error.
    expect(wrapper.findAllComponents(StatTile).length).toBeGreaterThan(0)
    expect(wrapper.findAllComponents(TimeSeriesChart)).toHaveLength(0)
    expect(wrapper.text()).toContain('Impossible de charger les courbes.')
    expect(wrapper.text()).not.toContain('Impossible de charger le monitoring.')
  })
})
