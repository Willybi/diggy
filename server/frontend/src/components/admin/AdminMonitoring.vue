<template>
  <div class="monitoring">
    <div v-if="loading" class="state">Chargement du monitoring…</div>
    <div v-else-if="error" class="state">Impossible de charger le monitoring.</div>

    <template v-else>
      <div v-if="snapshotStale" class="mon-alert" role="alert">
        <span class="mon-alert-icon"><AdminIcon name="alert-triangle" :size="15" /></span>
        <span>
          <strong>Échantillonnage du monitoring interrompu.</strong>
          Dernier instantané {{ snapshotAge }}. Au-delà d'une heure, le worker
          <code>diggy_worker</code> (queue <code>celery</code>) ne prélève plus les backlogs : les
          courbes se figent à cette date et l'interpolation masque le trou. Vérifier le conteneur
          worker (<code>docker compose ps</code>).
        </span>
      </div>
      <div class="mon-toolbar">
        <div class="mon-toolbar-left">
          <span class="mon-snapshot" :class="{ 'is-stale': snapshotStale }">
            Dernier instantané · {{ snapshotAge }}
          </span>
          <span v-if="lockActive" class="lock-chip">
            <AdminIcon name="arc" :size="12" /> Enrichissement en cours
          </span>
        </div>
        <div class="mon-toolbar-right">
          <select v-model.number="days" class="mon-select" @change="load">
            <option :value="7">7 jours</option>
            <option :value="14">14 jours</option>
            <option :value="30">30 jours</option>
          </select>
          <button class="btn btn--sm mon-refresh" @click="load">
            <AdminIcon name="refresh" :size="15" /> Rafraîchir
          </button>
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
            :sublabel="
              artists.backlog_artwork != null
                ? `${fmtInt(artists.backlog_artwork)} sans pochette`
                : ''
            "
            tone="neutral"
          />
          <StatTile label="Sets à recrawler" :value="fmtInt(sets.recrawl_backlog)" tone="neutral" />
          <StatTile
            label="Sets non fiables"
            :value="fmtInt(sets.unreliable)"
            sublabel="majoritairement ID"
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
              :height="30"
            />
          </StatTile>
          <StatTile
            label="BPM à analyser"
            :value="fmtInt(catalog.bpm_missing)"
            sublabel="preview sans BPM"
            tone="neutral"
          />
          <StatTile
            label="Embeddings à vectoriser"
            :value="fmtInt(embeddings.missing)"
            :sublabel="
              embCoveragePct != null ? `${embCoveragePct} % couverts` : 'audio « sonne comme »'
            "
            tone="embeddings"
          >
            <SparkLine
              v-if="embCoverageSeries.length > 1"
              class="tile-spark"
              :points="embCoverageSeries"
              color="var(--chart-embeddings)"
              :height="30"
            />
          </StatTile>
          <StatTile
            label="Covers albums manquantes"
            :value="fmtInt(albums.missing_cover)"
            sublabel="à rattraper"
            tone="neutral"
          />
          <StatTile
            label="Métadonnées albums"
            :value="fmtInt(albums.missing_meta)"
            sublabel="record_type manquant"
            tone="neutral"
          />
        </div>
      </section>

      <!-- ── Intégrité artiste (X4) ── -->
      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Intégrité artiste</h2>
        </div>
        <p class="mon-caption">
          Compteurs instantanés de non-régression (chantier X4) : liaisons artiste incohérentes ou
          manquantes dans le catalogue.
        </p>
        <div class="tiles">
          <StatTile
            label="Divergence artiste"
            :value="fmtInt(integrity.artist_divergence)"
            sublabel="artiste plat ≠ 1er lien"
            :tone="integrityTone(integrity.artist_divergence)"
          />
          <StatTile
            label="Sans lien artiste"
            :value="fmtInt(integrity.missing_m2m_link)"
            sublabel="artiste non cliquable"
            :tone="integrityTone(integrity.missing_m2m_link)"
          />
        </div>
      </section>

      <!-- ── Burn-down backlog dans le temps — 3 thèmes, groupés par ordre de
           grandeur pour rester lisibles (échelle Y unique par graphe) ── -->
      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Enrichissement plateforme dans le temps</h2>
        </div>
        <p class="mon-caption">
          Entrées non enrichies restantes, par plateforme. Teinte pleine = à traiter maintenant
          (jamais cherché + à relancer) ; teinte claire = total restant, dont les morceaux en
          attente de re-scan (30/90 j) ou abandonnés.
        </p>
        <TimeSeriesChart
          :series="platformBurn"
          :height="260"
          show-area
          :y-format="fmtInt"
          :x-format="fmtDayShort"
        />
      </section>

      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Backfills de contenu dans le temps</h2>
        </div>
        <p class="mon-caption">
          Données dérivées à rattraper : les embeddings audio (C9) et le BPM partagent la même
          tuyauterie (preview Deezer → analyse). Chaque courbe descend vers 0 à mesure du
          rattrapage.
        </p>
        <TimeSeriesChart
          :series="contentBurn"
          :height="260"
          :y-format="fmtInt"
          :x-format="fmtDayShort"
        />
      </section>

      <section class="admin-section">
        <div class="section-header">
          <h2 class="section-title">Petits soldes & qualité dans le temps</h2>
        </div>
        <p class="mon-caption">
          Résidus de faible volume : pochettes d'albums rattrapées par le cron, et sets TrackID
          flaggés peu fiables (recalculés à chaque ré-import).
        </p>
        <TimeSeriesChart
          :series="residualBurn"
          :height="260"
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
              :height="260"
              :y-format="fmtInt"
              :x-format="fmtDayShort"
            />
          </div>
          <div class="chart-cell">
            <h3 class="chart-h3">Taux de réussite / jour</h3>
            <TimeSeriesChart
              :series="hitRateChart"
              :height="260"
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
              :height="30"
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
        <div class="at-region">
          <div v-if="!lastRuns.length" class="at-empty">Aucun run enregistré.</div>
          <div v-else class="at-scroll">
            <table class="at-table">
              <thead>
                <tr>
                  <th>Tâche</th>
                  <th>Source</th>
                  <th>Statut</th>
                  <th>Âge</th>
                  <th class="at-tech--right">Durée</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in lastRuns" :key="r.task_type + (r.source || '')">
                  <td data-label="Tâche" data-lead>
                    <span class="at-id">{{ taskLabel(r.task_type) }}</span>
                  </td>
                  <td data-label="Source">
                    <span v-if="r.source" class="at-source">{{ r.source }}</span>
                  </td>
                  <td data-label="Statut">
                    <span class="at-pill" :class="pillClass(r.status)">
                      <AdminIcon v-if="r.status === 'running'" name="arc" :size="10" />
                      {{ statusFr(r.status) }}
                    </span>
                  </td>
                  <td data-label="Âge">
                    <span class="at-tech">{{ fmtAge(r.started_at) }}</span>
                  </td>
                  <td data-label="Durée" class="at-tech--right">
                    <span class="at-tech">{{
                      r.duration_ms != null ? fmtDuration(r.duration_ms) : '—'
                    }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
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
import AdminIcon from './AdminIcon.vue'

const SOURCES = [
  {
    key: 'deezer',
    label: 'Deezer',
    color: 'var(--chart-deezer)',
    colorSoft: 'var(--chart-deezer-soft)',
  },
  {
    key: 'beatport',
    label: 'Beatport',
    color: 'var(--chart-beatport)',
    colorSoft: 'var(--chart-beatport-soft)',
  },
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
const albums = computed(() => latest.value.albums || {})
const embeddings = computed(() => latest.value.embeddings || {})

// ── embeddings coverage (C9.a) ── instant % + climbing spark for the tile.
const embCoveragePct = computed(() => {
  const e = embeddings.value
  if (!Number.isFinite(e.covered) || !Number.isFinite(e.eligible) || !e.eligible) return null
  return Math.round((e.covered / e.eligible) * 100)
})
const embCoverageSeries = computed(() =>
  backlogSeries.value
    .map((snap) => {
      const e = snap.payload?.embeddings
      if (!e || !Number.isFinite(e.covered) || !Number.isFinite(e.eligible) || !e.eligible) {
        return null
      }
      return { t: snap.captured_at, v: (e.covered / e.eligible) * 100 }
    })
    .filter(Boolean),
)

// ── artist-integrity instant counters (X4) ──
const integrity = computed(() => data.value?.integrity || {})
function integrityTone(n) {
  return Number(n) > 0 ? 'neg' : 'pos'
}

// ── backlog tiles ──
function enrichBucket(src) {
  return (latest.value.enrich && latest.value.enrich[src]) || {}
}
function enrichTotal(src) {
  const b = enrichBucket(src)
  if (b.total_missing != null) return b.total_missing
  const sum = (b.never_tried || 0) + (b.due_retry || 0) + (b.cooldown || 0) + (b.abandoned || 0)
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

// ── burn-down dans le temps, découpé en 3 thèmes groupés par ordre de grandeur
// (TimeSeriesChart a UNE échelle Y linéaire par graphe : mélanger des séries de
// magnitudes très différentes écraserait les petites). Toutes les séries gardent
// la garde Number.isFinite → une clé démarre au 1er snapshot qui la porte (les
// anciens payloads ne l'ont pas).

// Helper : extrait un scalaire du payload en série {t,v}, invalides retirés.
function backlogPath(pick) {
  return backlogSeries.value
    .map((snap) => ({ t: snap.captured_at, v: pick(snap.payload) }))
    .filter((p) => Number.isFinite(p.v))
}

// A · Enrichissement plateforme (E1). Deux teintes par source : couleur pleine =
// backlog ACTIONNABLE (never_tried + due_retry, ce que la passe traiterait
// maintenant), teinte claire = total restant (inclut cooldown/abandonnés). Le
// total est tracé EN PREMIER (dessous), l'actionnable PAR-DESSUS → bande 2 tons,
// l'écart entre les deux lignes = le stock parqué (non actionnable).
const platformBurn = computed(() => {
  const out = []
  for (const s of SOURCES) {
    const total = []
    const actionable = []
    for (const snap of backlogSeries.value) {
      const b = snap.payload?.enrich?.[s.key]
      if (!b) continue
      if (Number.isFinite(b.total_missing)) {
        total.push({ t: snap.captured_at, v: b.total_missing })
      }
      // Guard pour d'éventuels snapshots antérieurs aux tiers (never/due null).
      if (b.never_tried != null || b.due_retry != null) {
        actionable.push({
          t: snap.captured_at,
          v: (b.never_tried || 0) + (b.due_retry || 0),
        })
      }
    }
    if (total.length) out.push({ label: `${s.label} · total`, color: s.colorSoft, points: total })
    if (actionable.length) {
      out.push({ label: `${s.label} · à traiter`, color: s.color, points: actionable })
    }
  }
  return out
})

// B · Backfills de contenu dérivé (~44k–213k, même ordre). Embeddings (C9) + BPM
// (E2.c) partagent la tuyauterie preview→analyse ; métadonnées albums (C7/L8) au
// même volume.
const contentBurn = computed(() => {
  const out = []
  const emb = backlogPath((p) => p?.embeddings?.missing)
  if (emb.length) {
    out.push({ label: 'Embeddings · à vectoriser', color: 'var(--chart-embeddings)', points: emb })
  }
  const bpm = backlogPath((p) => p?.catalog?.bpm_missing)
  if (bpm.length) out.push({ label: 'BPM · à analyser', color: 'var(--chart-bpm)', points: bpm })
  const meta = backlogPath((p) => p?.albums?.missing_meta)
  if (meta.length) {
    out.push({ label: 'Albums · métadonnées', color: 'var(--chart-albums)', points: meta })
  }
  return out
})

// C · Petits soldes & qualité (~1k, enfin lisibles ensemble). Covers d'albums
// (C7/L8) rattrapées par le cron + sets TrackID flaggés peu fiables (C8).
const residualBurn = computed(() => {
  const out = []
  const covers = backlogPath((p) => p?.albums?.missing_cover)
  if (covers.length) {
    out.push({ label: 'Albums · covers manquantes', color: 'var(--chart-albums)', points: covers })
  }
  const unreliable = backlogPath((p) => p?.sets?.unreliable)
  if (unreliable.length) {
    out.push({ label: 'Sets · non fiables', color: 'var(--chart-sets)', points: unreliable })
  }
  return out
})

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
  return [...m.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([day, v]) => ({ t: day, v }))
})
const totalErrors = computed(() => throughputSeries.value.reduce((s, r) => s + (r.errors || 0), 0))
const totalRuns = computed(() => throughputSeries.value.reduce((s, r) => s + (r.runs || 0), 0))
const maxDuration = computed(() => {
  let m = 0
  for (const r of throughputSeries.value) {
    if (r.duration_ms_max && r.duration_ms_max > m) m = r.duration_ms_max
  }
  return m || null
})
const enrichLastRuns = computed(() =>
  lastRuns.value.filter(
    (r) => r.task_type === 'enrich_catalog' || r.task_type === 'enrich_beatport',
  ),
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
// Backend-computed: latest snapshot missing or older than 2 h ⇒ the hourly
// sampler stopped (silent worker death). Surfaced as a banner above the tools.
const snapshotStale = computed(() => !!data.value?.status?.snapshot_stale)

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
// Map a run status to the shared .at-pill variant (D7).
const STATUS_PILL = { success: 'at-pill--ok', error: 'at-pill--err', running: 'at-pill--run' }
function pillClass(s) {
  return STATUS_PILL[s] || 'at-pill--neutral'
}
</script>

<style scoped>
.monitoring {
  container-type: inline-size;
}

/* ── Toolbar (archétype F) : instantané ⟷ sélecteur de fenêtre + Rafraîchir ── */
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
.mon-snapshot.is-stale {
  color: var(--warn-ink);
  font-weight: 600;
}
.lock-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
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
/* Sélecteur de fenêtre : hauteur desktop 34px portée par la classe (D14). */
.mon-select {
  height: 34px;
  padding: 0 var(--space-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 400 var(--fs-sm)/1 var(--font-mono);
  cursor: pointer;
}

/* ── Alerte « échantillonnage interrompu » (icône, jamais un emoji) ── */
.mon-alert {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
  padding: var(--space-3) var(--space-4);
  background: var(--warn-soft);
  color: var(--warn-ink);
  border: 1px solid var(--warn);
  border-radius: var(--r-sm);
  font: 400 var(--fs-sm)/1.5 var(--font-ui);
}
.mon-alert-icon {
  display: inline-flex;
  flex: none;
  margin-top: 2px;
}
.mon-alert code {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}

/* ── Bloc de section : --surface + 1px --line + --r-md, pile titre/sous-titre/
   contenu espacée de --space-25, blocs espacés de --space-4 ── */
.admin-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-25);
  margin-bottom: var(--space-4);
  padding: var(--space-4);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.flag-count {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.04em;
  background: var(--surface-3);
  color: var(--ink-2);
  padding: 2px var(--space-2);
  border-radius: var(--r-pill);
}
.mon-caption {
  max-width: 96ch;
  margin: 0;
  font: 400 var(--fs-sm)/1.5 var(--font-ui);
  color: var(--ink-2);
  text-wrap: pretty;
}

/* ── Grille de tuiles ── */
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(196px, 1fr));
  gap: var(--space-25);
}
.tile-spark {
  width: 100%;
}

/* ── Duo Débit & taux : deux graphes côte à côte, une colonne sous 859px ── */
.chart-duo {
  display: grid;
  grid-template-columns: 1fr 1fr;
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

/* Loading / error utility (compact admin-panel variant). */
.state {
  font-size: var(--fs-sm);
  padding: var(--space-3) 0;
}

/* ── Palier unique 859px, container queries uniquement ── */
@container (max-width: 859px) {
  .mon-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .mon-toolbar-right {
    width: 100%;
  }
  .mon-select {
    flex: 1;
    min-height: var(--touch-min);
  }
  .mon-refresh {
    width: 100%;
    min-height: var(--touch-min);
  }
  .admin-section {
    padding: var(--space-3);
  }
  .tiles {
    grid-template-columns: 1fr;
  }
  .chart-duo {
    grid-template-columns: 1fr;
  }
}
</style>
