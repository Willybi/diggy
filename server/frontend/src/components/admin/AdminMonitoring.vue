<template>
  <div class="monitoring">
    <div v-if="loading" class="state">Chargement du monitoring…</div>
    <div v-else-if="error" class="state">Impossible de charger le monitoring.</div>

    <template v-else>
      <div class="mon-toolbar">
        <div class="mon-toolbar-left">
          <span class="mon-snapshot">
            Dernier instantané : {{ snapshotAge }}
          </span>
          <span v-if="lockActive" class="lock-chip">🔒 Enrichissement en cours</span>
        </div>
        <div class="mon-toolbar-right">
          <select v-model.number="days" class="mon-select" @change="load">
            <option :value="7">7 jours</option>
            <option :value="14">14 jours</option>
            <option :value="30">30 jours</option>
          </select>
          <button class="mon-refresh" @click="load">Rafraîchir</button>
        </div>
      </div>

      <!-- ── Backlogs ── -->
      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Backlogs d'enrichissement</h2>
        </div>
        <div class="tiles">
          <StatTile
            v-for="s in SOURCES"
            :key="s.key"
            :label="s.label"
            :value="fmtInt(enrichTotal(s.key))"
            :sublabel="enrichSub(s.key)"
            :tone="s.key"
          />
          <StatTile
            label="Artistes à lier"
            :value="fmtInt(artists.backlog_link)"
            :sublabel="artists.backlog_artwork != null ? `${fmtInt(artists.backlog_artwork)} sans pochette` : ''"
            tone="neutral"
          />
          <StatTile
            label="Sets à recrawler"
            :value="fmtInt(sets.recrawl_backlog)"
            tone="neutral"
          />
          <StatTile
            label="Catalogue"
            :value="fmtInt(catalog.total)"
            :delta="catalogDelta"
            :sublabel="catalogDelta != null ? `sur ${days} j` : ''"
            tone="accent"
          >
            <SparkLine
              v-if="catalogSeries.length > 1"
              class="tile-spark"
              :points="catalogSeries"
              color="var(--accent)"
              :height="24"
            />
          </StatTile>
        </div>
      </section>

      <!-- ── Burn-down backlog dans le temps ── -->
      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Backlog à traiter dans le temps</h2>
        </div>
        <p class="mon-caption">Entrées non enrichies restantes, par source.</p>
        <TimeSeriesChart
          :series="burnSeries"
          :height="220"
          show-area
          :y-format="fmtInt"
          :x-format="fmtDayShort"
        />
      </section>

      <!-- ── Débit & taux de réussite ── -->
      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Débit & taux de réussite</h2>
        </div>
        <div class="chart-duo">
          <div class="chart-cell">
            <h3 class="chart-h3">Enrichissements / jour</h3>
            <TimeSeriesChart
              :series="throughputChart"
              :height="200"
              :y-format="fmtInt"
              :x-format="fmtDayShort"
            />
          </div>
          <div class="chart-cell">
            <h3 class="chart-h3">Taux de réussite / jour</h3>
            <TimeSeriesChart
              :series="hitRateChart"
              :height="200"
              :y-format="fmtPct"
              :x-format="fmtDayShort"
            />
          </div>
        </div>
      </section>

      <!-- ── Erreurs & durées ── -->
      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Erreurs & durées</h2>
        </div>
        <div class="tiles">
          <StatTile
            label="Erreurs (période)"
            :value="fmtInt(totalErrors)"
            :sublabel="`sur ${fmtInt(totalRuns)} runs`"
            :tone="totalErrors > 0 ? 'neg' : 'neutral'"
          >
            <SparkLine
              v-if="errorsByDay.length > 1"
              class="tile-spark"
              :points="errorsByDay"
              color="var(--neg)"
              :height="24"
            />
          </StatTile>
          <StatTile
            label="Durée max observée"
            :value="maxDuration != null ? fmtDuration(maxDuration) : '—'"
            sublabel="run le plus long"
            tone="warn"
          />
          <StatTile
            v-for="r in enrichLastRuns"
            :key="r.task_type"
            :label="taskLabel(r.task_type)"
            :value="r.duration_ms != null ? fmtDuration(r.duration_ms) : '—'"
            :sublabel="`${statusFr(r.status)} · ${fmtAge(r.started_at)}`"
            :tone="r.status === 'error' ? 'neg' : r.status === 'running' ? 'accent' : 'pos'"
          />
        </div>
      </section>

      <!-- ── État des tâches ── -->
      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">
            Dernier passage par tâche
            <span v-if="lastRuns.length" class="flag-count">{{ lastRuns.length }}</span>
          </h2>
        </div>
        <div v-if="!lastRuns.length" class="state">Aucun run enregistré.</div>
        <ul v-else class="run-list">
          <li v-for="r in lastRuns" :key="r.task_type + (r.source || '')" class="run-row">
            <span class="run-name">{{ taskLabel(r.task_type) }}</span>
            <span v-if="r.source" class="token-pill">{{ r.source }}</span>
            <span class="status-badge" :class="r.status">{{ statusFr(r.status) }}</span>
            <span class="run-meta">{{ fmtAge(r.started_at) }}</span>
            <span class="run-meta mono">{{
              r.duration_ms != null ? fmtDuration(r.duration_ms) : '—'
            }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import TimeSeriesChart from '../charts/TimeSeriesChart.vue'
import SparkLine from '../charts/SparkLine.vue'
import StatTile from '../charts/StatTile.vue'

const SOURCES = [
  { key: 'deezer', label: 'Deezer', color: 'var(--chart-deezer)' },
  { key: 'beatport', label: 'Beatport', color: 'var(--chart-beatport)' },
]

const TASK_LABELS = {
  enrich_catalog: 'Enrich Deezer',
  enrich_beatport: 'Enrich Beatport',
  crawl_radar: 'Crawl playlists',
  crawl_single_playlist: 'Crawl playlist',
  crawl_trackid_latest: 'Crawl TrackID',
  backfill_trackid_sets: 'Backfill sets',
  recrawl_incomplete_sets: 'Recrawl sets',
  compute_trends: 'Tendances',
  check_followed_artists: 'Artistes suivis',
  link_set_artists: 'Artistes sets',
}
const STATUS_FR = { success: 'Succès', error: 'Erreur', running: 'En cours' }

const data = ref(null)
const loading = ref(true)
const error = ref(false)
const days = ref(30)

async function load() {
  loading.value = true
  error.value = false
  try {
    const { data: d } = await api.get('/api/admin/monitoring', { params: { days: days.value } })
    data.value = d
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
onMounted(load)

// ── raw slices ──
const backlogSeries = computed(() => data.value?.backlog_series || [])
const throughputSeries = computed(() => data.value?.throughput_series || [])
const lastRuns = computed(() => data.value?.status?.last_runs || [])
const latest = computed(() => data.value?.status?.latest_snapshot?.payload || {})

const artists = computed(() => latest.value.artists || {})
const sets = computed(() => latest.value.sets || {})
const catalog = computed(() => latest.value.catalog || {})

// ── backlog tiles ──
function enrichBucket(src) {
  return (latest.value.enrich && latest.value.enrich[src]) || {}
}
function enrichTotal(src) {
  const b = enrichBucket(src)
  if (b.total_missing != null) return b.total_missing
  const sum =
    (b.never_tried || 0) + (b.due_retry || 0) + (b.cooldown || 0) + (b.abandoned || 0)
  return sum || (b.total_linked != null ? 0 : null)
}
function enrichSub(src) {
  const b = enrichBucket(src)
  const parts = []
  if (b.never_tried != null) parts.push(`${fmtInt(b.never_tried)} jamais`)
  if (b.due_retry != null) parts.push(`${fmtInt(b.due_retry)} à relancer`)
  if (b.cooldown != null) parts.push(`${fmtInt(b.cooldown)} en attente`)
  if (b.abandoned != null) parts.push(`${fmtInt(b.abandoned)} abandonnés`)
  if (!parts.length && b.total_linked != null) parts.push(`${fmtInt(b.total_linked)} liés`)
  return parts.join(' · ')
}

// ── catalog growth (ingestion) ──
const catalogSeries = computed(() =>
  backlogSeries.value
    .map((snap) => ({ t: snap.captured_at, v: snap.payload?.catalog?.total }))
    .filter((p) => Number.isFinite(p.v)),
)
const catalogDelta = computed(() => {
  const c = catalogSeries.value
  if (c.length < 2) return null
  const d = c[c.length - 1].v - c[0].v
  return (d >= 0 ? '+' : '') + fmtInt(d)
})

// ── burn-down (backlog per source over time) ──
const burnSeries = computed(() =>
  SOURCES.map((s) => ({
    label: s.label,
    color: s.color,
    points: backlogSeries.value
      .map((snap) => ({ t: snap.captured_at, v: snap.payload?.enrich?.[s.key]?.total_missing }))
      .filter((p) => Number.isFinite(p.v)),
  })).filter((s) => s.points.length),
)

// ── throughput aggregated by (day, source) ──
const bySourceDay = computed(() => {
  const m = new Map()
  for (const r of throughputSeries.value) {
    if (!r.source) continue
    const k = `${r.day}|${r.source}`
    let a = m.get(k)
    if (!a) {
      a = { day: r.day, source: r.source, enriched: 0, not_found: 0, errors: 0, runs: 0 }
      m.set(k, a)
    }
    a.enriched += r.enriched || 0
    a.not_found += r.not_found || 0
    a.errors += r.errors || 0
    a.runs += r.runs || 0
  }
  return [...m.values()]
})

const throughputChart = computed(() =>
  SOURCES.map((s) => ({
    label: s.label,
    color: s.color,
    points: bySourceDay.value
      .filter((r) => r.source === s.key)
      .map((r) => ({ t: r.day, v: r.enriched })),
  })).filter((s) => s.points.length),
)

const hitRateChart = computed(() =>
  SOURCES.map((s) => ({
    label: s.label,
    color: s.color,
    points: bySourceDay.value
      .filter((r) => r.source === s.key)
      .map((r) => {
        const denom = r.enriched + r.not_found
        return { t: r.day, v: denom ? (r.enriched / denom) * 100 : null }
      })
      .filter((p) => p.v != null),
  })).filter((s) => s.points.length),
)

// ── errors & durations ──
const errorsByDay = computed(() => {
  const m = new Map()
  for (const r of throughputSeries.value) m.set(r.day, (m.get(r.day) || 0) + (r.errors || 0))
  return [...m.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([day, v]) => ({ t: day, v }))
})
const totalErrors = computed(() =>
  throughputSeries.value.reduce((s, r) => s + (r.errors || 0), 0),
)
const totalRuns = computed(() => throughputSeries.value.reduce((s, r) => s + (r.runs || 0), 0))
const maxDuration = computed(() => {
  let m = 0
  for (const r of throughputSeries.value) {
    if (r.duration_ms_max && r.duration_ms_max > m) m = r.duration_ms_max
  }
  return m || null
})
const enrichLastRuns = computed(() =>
  lastRuns.value.filter((r) => r.task_type === 'enrich_catalog' || r.task_type === 'enrich_beatport'),
)

// ── status ──
const lockActive = computed(() =>
  lastRuns.value.some(
    (r) =>
      r.status === 'running' &&
      (r.task_type === 'enrich_catalog' || r.task_type === 'enrich_beatport'),
  ),
)
const snapshotAge = computed(() => {
  const iso = data.value?.status?.latest_snapshot?.captured_at
  return iso ? fmtAge(iso) : 'aucun'
})

// ── formatters ──
function fmtInt(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString('fr-FR')
}
function fmtPct(v) {
  return `${Math.round(v)} %`
}
function fmtDuration(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s} s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, '0')}`
  const h = Math.floor(m / 60)
  return `${h} h ${String(m % 60).padStart(2, '0')}`
}
function fmtAge(iso) {
  if (!iso) return '—'
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 60) return `il y a ${s} s`
  const m = Math.floor(s / 60)
  if (m < 60) return `il y a ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `il y a ${h} h`
  const d = Math.floor(h / 24)
  return `il y a ${d} j`
}
function fmtDayShort(ts) {
  const d = new Date(ts)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}`
}
function taskLabel(t) {
  return TASK_LABELS[t] || t
}
function statusFr(s) {
  return STATUS_FR[s] || s
}
</script>

<style scoped>
.monitoring {
  container-type: inline-size;
}
.mon-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}
.mon-toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.mon-snapshot {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.lock-chip {
  font: 500 var(--fs-xs)/1 var(--font-ui);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--r-pill);
}
.mon-toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.mon-select {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 400 var(--fs-xs)/1 var(--font-mono);
  cursor: pointer;
}
.mon-refresh {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
}
.mon-refresh:hover {
  color: var(--ink);
  border-color: var(--line);
}

.admin-section {
  margin-bottom: var(--space-6);
  padding: var(--space-5) var(--space-6);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.section-title {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.flag-count {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: var(--space-05) var(--space-15);
  border-radius: 10px;
}
.mon-caption {
  margin: calc(-1 * var(--space-2)) 0 var(--space-4);
  font: 400 var(--fs-xs)/1.4 var(--font-ui);
  color: var(--ink-3);
}

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--space-3);
}
.tile-spark {
  margin-top: var(--space-2);
  width: 100%;
}

.chart-duo {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-6);
}
.chart-cell {
  min-width: 0;
}
.chart-h3 {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-2);
  margin-bottom: var(--space-3);
}

.run-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.run-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--line);
  font-size: var(--fs-sm);
}
.run-row:last-child {
  border-bottom: none;
}
.run-name {
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink);
  min-width: 120px;
}
.run-meta {
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-3);
}
.run-meta.mono {
  font-family: var(--font-mono);
  margin-left: auto;
}
.token-pill {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  white-space: nowrap;
}
.status-badge {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  padding: var(--space-05) var(--space-2);
  border-radius: 4px;
}
.status-badge.running {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.status-badge.success {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.status-badge.error {
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.state {
  /* diverges from canonical .state: compact admin-panel padding + smaller font */
  font-size: var(--fs-sm);
  padding: var(--space-3) 0;
}
</style>
