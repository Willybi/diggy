<template>
  <div class="overview">
    <!-- ── Erreur de chargement du backlog : bandeau, grille NON rendue ── -->
    <div v-if="error" class="oc-error" role="alert">
      <span class="oc-error-badge">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
          />
          <path d="M12 9v4" />
          <path d="M12 17h.01" />
        </svg>
      </span>
      <div class="oc-error-body">
        <p class="oc-error-title">Backlog indisponible</p>
        <p class="oc-error-text">
          L'appel à <span class="mono">/api/admin/backlog</span> a échoué. Les onglets et leurs
          actions restent utilisables ; les badges de compte sont masqués tant que le backlog n'est
          pas chargé.
        </p>
        <button class="btn btn--sm" @click="emit('refresh')">Réessayer</button>
      </div>
    </div>

    <template v-else>
      <!-- ── Ligne de synthèse ── -->
      <div class="oc-summary">
        <div class="oc-summary-text">
          <p v-if="backlog" class="oc-summary-line">{{ summaryLine }}</p>
          <span v-else class="sk sk-summary"></span>
          <span class="oc-snapshot">Snapshot {{ backlog ? snapshotLabel : '—' }}</span>
        </div>
        <button class="btn btn--sm oc-refresh" :disabled="loading" @click="emit('refresh')">
          <svg
            class="oc-refresh-icon"
            :class="{ spinning: loading }"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="M21 12a9 9 0 1 1-2.64-6.36" />
            <path d="M21 3v6h-6" />
          </svg>
          Actualiser
        </button>
      </div>

      <!-- ── Grille des 12 cartes ── -->
      <div class="oc-grid">
        <!-- Squelette 1er affichage : forme de grille connue, aucun saut de layout -->
        <template v-if="!backlog">
          <div v-for="n in CARDS.length" :key="`sk-${n}`" class="oc-card oc-card--skel">
            <span class="sk sk-eyebrow"></span>
            <span class="sk sk-title"></span>
            <span class="sk sk-counter"></span>
            <span class="sk sk-action"></span>
          </div>
        </template>

        <template v-else>
          <article
            v-for="card in resolvedCards"
            :key="card.id"
            class="oc-card"
            :class="`oc-card--${card.regime}`"
          >
            <span class="oc-eyebrow">{{ card.eyebrow }}</span>
            <h3 class="oc-title">{{ card.title }}</h3>

            <div class="oc-counter">
              <template v-if="card.regime === 'backlog'">
                <span class="oc-value">{{ fmtInt(card.counter) }}</span>
                <span class="oc-unit">{{ card.unit }}</span>
              </template>
              <template v-else-if="card.regime === 'ok'">
                <span class="oc-check">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                </span>
                <span class="oc-uptodate">À jour</span>
              </template>
              <template v-else>
                <span class="oc-unknown">—</span>
              </template>
            </div>

            <p v-if="card.contextSegments" class="oc-context">
              <span v-for="(seg, i) in card.contextSegments" :key="i" :class="{ mono: seg.mono }">{{
                seg.text
              }}</span>
            </p>

            <p v-if="isRunning(card.id)" class="oc-job">
              <svg class="oc-arc" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
              </svg>
              Job en cours…
            </p>

            <div class="oc-actions">
              <template v-if="card.action.kind === 'job'">
                <button
                  class="btn btn--sm"
                  :class="{ 'btn--accent': card.regime === 'backlog' }"
                  :disabled="isRunning(card.id)"
                  @click="runJob(card)"
                >
                  {{ isRunning(card.id) ? 'En cours…' : card.action.label }}
                </button>
                <button class="oc-link" @click="emit('navigate', card.action.navTab)">
                  {{ card.action.navLabel }}
                </button>
              </template>
              <button v-else class="btn btn--sm" @click="emit('navigate', card.action.navTab)">
                {{ card.action.label }}
              </button>
            </div>
          </article>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '../../utils/api.js'

const props = defineProps({
  backlog: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: Boolean, default: false },
})
const emit = defineEmits(['refresh', 'navigate'])

// ── Les 12 cartes de chantier (A1 : une carte = un compteur actionnable). ──
// `group`/`field` pointent dans la réponse de /api/admin/backlog.
// `action.kind` : 'job' → POST + lien secondaire de renvoi (A6) ; 'nav' → renvoi neutre.
const CARDS = [
  {
    id: 'beatport-enrich',
    eyebrow: 'Beatport',
    title: 'Tracks à enrichir',
    group: 'beatport',
    field: 'pending',
    unit: 'tracks',
    context: (b) => [
      { text: 'sur ' },
      { text: fmtInt(b.beatport.total_missing), mono: true },
      { text: ' manquantes · ' },
      { text: fmtInt(b.beatport.abandoned), mono: true },
      { text: ' abandonnées' },
    ],
    action: {
      kind: 'job',
      label: "Lancer l'enrichissement",
      endpoint: '/api/admin/enrich-beatport',
      navTab: 'beatport',
      navLabel: 'Onglet Beatport',
    },
  },
  {
    id: 'deezer-enrich',
    eyebrow: 'Deezer',
    title: 'Tracks à enrichir',
    group: 'deezer',
    field: 'pending',
    unit: 'tracks',
    context: (b) => [
      { text: fmtInt(b.deezer.total_missing), mono: true },
      { text: ' manquantes, en cooldown · ' },
      { text: fmtInt(b.deezer.abandoned), mono: true },
      { text: ' abandonnées' },
    ],
    action: { kind: 'nav', label: 'Voir le monitoring', navTab: 'monitoring' },
  },
  {
    id: 'catalog-bpm',
    eyebrow: 'Beatport',
    title: 'À analyser (BPM)',
    group: 'catalog',
    field: 'bpm_missing',
    unit: 'tracks',
    context: () => [{ text: 'analyse audio nocturne automatique' }],
    action: { kind: 'nav', label: 'Voir le monitoring', navTab: 'monitoring' },
  },
  {
    id: 'artists-link',
    eyebrow: 'Artistes',
    title: 'À lier sur Deezer',
    group: 'artists',
    field: 'to_link',
    unit: 'artistes',
    context: null,
    action: {
      kind: 'job',
      label: 'Lier les artistes',
      endpoint: '/api/admin/artists/link-deezer',
      navTab: 'artists',
      navLabel: 'Onglet Artistes',
    },
  },
  {
    id: 'artists-artwork',
    eyebrow: 'Artistes',
    title: 'Sans pochette',
    group: 'artists',
    field: 'no_artwork',
    unit: 'artistes',
    context: null,
    action: {
      kind: 'job',
      label: 'Fetch artworks',
      endpoint: '/api/admin/artists/fetch-artworks',
      navTab: 'artists',
      navLabel: 'Onglet Artistes',
    },
  },
  {
    id: 'sets-recrawl',
    eyebrow: 'Sets',
    title: 'À recrawler',
    group: 'sets',
    field: 'recrawl',
    unit: 'sets',
    context: () => [{ text: 'recrawl_status ≠ final' }],
    action: { kind: 'nav', label: "Ouvrir l'onglet Sets", navTab: 'sets' },
  },
  {
    id: 'sets-flags',
    eyebrow: 'Sets',
    title: 'Set-flags en attente',
    group: 'sets',
    field: 'flags_pending',
    unit: 'paires',
    context: () => [{ text: 'revue manuelle' }],
    action: { kind: 'nav', label: 'Ouvrir la revue', navTab: 'sets' },
  },
  {
    id: 'artist-flags',
    eyebrow: 'Flags artistes',
    title: 'Flags en attente',
    group: 'artist_flags',
    field: 'pending',
    unit: 'paires',
    context: () => [{ text: 'fusions à valider' }],
    action: { kind: 'nav', label: 'Ouvrir la revue', navTab: 'flags' },
  },
  {
    id: 'genres-unclassified',
    eyebrow: 'Genres',
    title: 'Tracks non classées',
    group: 'genres',
    field: 'unclassified',
    unit: 'tracks',
    context: null,
    action: { kind: 'nav', label: 'Voir les genres', navTab: 'genres' },
  },
  {
    id: 'genres-mappings',
    eyebrow: 'Genres',
    title: 'Mappings non mappés',
    group: 'genres',
    field: 'mappings_unmapped',
    unit: 'mappings',
    context: () => [{ text: 'nom brut sans node' }],
    action: { kind: 'nav', label: 'Voir les mappings', navTab: 'genres' },
  },
  {
    id: 'crawl-due',
    eyebrow: 'Crawl',
    title: 'Playlists dues',
    group: 'crawl',
    field: 'playlists_due',
    unit: 'playlists',
    context: () => [{ text: 'cadence crawl_radar' }],
    action: { kind: 'nav', label: 'Voir la file', navTab: 'crawl' },
  },
  {
    id: 'crawl-dlq',
    eyebrow: 'Crawl',
    title: "File d'échec (DLQ)",
    group: 'crawl',
    field: 'dlq',
    unit: 'entrées',
    context: (b) => [{ text: b.crawl.dlq == null ? 'Redis injoignable' : 'clé Redis dead_letter' }],
    action: { kind: 'nav', label: 'Voir la DLQ', navTab: 'crawl' },
  },
]

// Chaque carte a 3 régimes selon SON compteur actionnable :
//   'backlog' → compteur > 0 (chantier en attente)
//   'ok'      → compteur === 0 (« À jour ✓ », le zéro n'est jamais écrit)
//   'unknown' → compteur == null (seul cas : DLQ quand Redis est injoignable —
//               un faux « à jour » serait trompeur ; ce n'est PAS « en attente »)
function counterOf(card) {
  const g = props.backlog?.[card.group]
  return g ? g[card.field] : null
}
function regimeOf(card) {
  const c = counterOf(card)
  if (c == null) return 'unknown'
  return c > 0 ? 'backlog' : 'ok'
}

const resolvedCards = computed(() =>
  CARDS.map((card) => {
    return {
      ...card,
      counter: counterOf(card),
      regime: regimeOf(card),
      contextSegments: card.context && props.backlog ? card.context(props.backlog) : null,
    }
  }),
)

// Seul le régime « backlog » compte comme travail en attente (unknown exclu).
const backlogCount = computed(
  () => resolvedCards.value.filter((c) => c.regime === 'backlog').length,
)

const summaryLine = computed(() => {
  const n = backlogCount.value
  if (n === 0) return 'Les 12 chantiers sont à jour.'
  if (n === 1) return '1 chantier sur 12 a du travail en attente.'
  return `${n} chantiers sur 12 ont du travail en attente.`
})

const snapshotLabel = computed(() => {
  const iso = props.backlog?.captured_at
  if (!iso) return '—'
  const d = new Date(iso)
  const p = (v) => String(v).padStart(2, '0')
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} · ${p(d.getHours())}:${p(d.getMinutes())}`
})

// ── Jobs (A7) : le bouton passe « En cours… », le compteur ne bouge pas — il ne
// se rafraîchira qu'au prochain backlog frais (parent). On efface l'état des
// jobs dès qu'un nouveau backlog arrive. ──
const runningJobs = ref({})
function isRunning(id) {
  return !!runningJobs.value[id]
}
async function runJob(card) {
  runningJobs.value = { ...runningJobs.value, [card.id]: true }
  try {
    await api.post(card.action.endpoint)
  } catch {
    // Les erreurs (429 / 5xx / réseau) sont remontées en toast par l'intercepteur
    // api ; on rouvre le bouton pour permettre une nouvelle tentative.
    runningJobs.value = { ...runningJobs.value, [card.id]: false }
  }
}
watch(
  () => props.backlog,
  () => {
    runningJobs.value = {}
  },
)

function fmtInt(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString('fr-FR')
}
</script>

<style scoped>
.overview {
  container-type: inline-size;
}

/* ── Ligne de synthèse ── */
.oc-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-5);
}
.oc-summary-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}
.oc-summary-line {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.oc-snapshot {
  font: 400 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
}
.oc-refresh {
  flex: none;
}
.oc-refresh-icon {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.oc-refresh-icon.spinning {
  animation: spin 0.9s linear infinite;
}

/* ── Grille (A12 : 252 ≥860 · 220 [640-859] · 1 col <640) ── */
.oc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(252px, 1fr));
  gap: var(--space-3);
}
@container (max-width: 859px) {
  .oc-grid {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  }
}
@container (max-width: 639px) {
  .oc-grid {
    grid-template-columns: 1fr;
  }
}

/* ── Carte de chantier ── */
.oc-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-25);
  padding: var(--space-4);
  border-radius: var(--r-md);
  border: 1px solid var(--line);
}
/* Backlog : posée (surface + ombre). À jour : enfoncée (bg, sans ombre).
   Inconnu (compteur null, ex. DLQ Redis down) : neutre, bordure un cran plus nette. */
.oc-card--backlog {
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.oc-card--ok {
  background: var(--bg);
}
.oc-card--unknown {
  background: var(--bg);
  border-color: var(--line-2);
}
/* À jour : eyebrow + titre reculent (--ink-3) pour laisser dominer les cartes en
   retard (titre --ink + gros chiffre mono). La pastille verte garde son intensité. */
.oc-card--ok .oc-eyebrow,
.oc-card--ok .oc-title {
  color: var(--ink-3);
}

.oc-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.oc-title {
  font: 600 var(--fs-title)/1.25 var(--font-ui);
  color: var(--ink);
  text-wrap: pretty;
}

.oc-counter {
  display: flex;
  align-items: baseline;
  gap: var(--space-15);
  min-height: 42px;
}
.oc-value {
  font: 600 var(--fs-display)/1 var(--font-mono);
  letter-spacing: -0.02em;
  color: var(--ink);
}
.oc-unit {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.oc-unknown {
  font: 600 var(--fs-display)/1 var(--font-mono);
  color: var(--ink-3);
}
/* Régime à jour : pastille + check, pas de chiffre. Le slot ne réserve plus la
   hauteur d'un gros chiffre (min-height:0) — sinon la pastille ~24px top-alignée
   creuse un écart avant le contexte plus grand que sur une carte à chiffre. Le
   contexte reste ainsi à distance constante (le gap flex) du bloc compteur. */
.oc-counter:has(.oc-check) {
  align-items: center;
  min-height: 0;
}
.oc-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--pos-soft);
  flex: none;
}
.oc-check svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: var(--pos-ink);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.oc-uptodate {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--pos-ink);
}

.oc-context {
  font: 400 var(--fs-xs)/1.4 var(--font-ui);
  color: var(--ink-3);
  text-wrap: pretty;
}

/* ── Job en cours (A7) : seul mouvement de la page ── */
.oc-job {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--accent-ink);
}
.oc-arc {
  width: 13px;
  height: 13px;
  fill: none;
  stroke: var(--accent-ink);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-dasharray: 40 60;
  animation: spin 0.9s linear infinite;
}

/* ── Actions : alignées en pied de carte entre voisines ── */
.oc-actions {
  margin-top: auto;
  padding-top: var(--space-2);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.oc-link {
  border: none;
  background: none;
  padding: 0;
  font: 500 var(--fs-sm)/1 var(--font-ui);
  color: var(--ink-3);
  cursor: pointer;
}
.oc-link:hover {
  color: var(--ink);
}

/* ── Squelette (A : 1er affichage) ── */
.oc-card--skel {
  background: var(--surface);
  gap: var(--space-3);
}
.sk {
  display: block;
  border-radius: var(--r-xs);
  background: var(--surface-3);
  animation: oc-pulse 1.4s ease-in-out infinite;
}
.sk-eyebrow {
  width: 64px;
  height: 9px;
}
.sk-title {
  width: 70%;
  height: 13px;
}
.sk-counter {
  width: 96px;
  height: 32px;
}
.sk-action {
  width: 100%;
  height: 34px;
  margin-top: auto;
}
.sk-summary {
  width: 240px;
  height: 15px;
  border-radius: var(--r-xs);
}
@keyframes oc-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* ── Erreur de chargement ── */
.oc-error {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--surface);
  border: 1px solid var(--neg);
  border-radius: var(--r-md);
}
.oc-error-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--neg-soft);
  flex: none;
}
.oc-error-badge svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: var(--neg-ink);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.oc-error-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}
.oc-error-title {
  font: 600 var(--fs-md)/1.2 var(--font-ui);
  color: var(--ink);
}
.oc-error-text {
  font: 400 var(--fs-sm)/1.5 var(--font-ui);
  color: var(--ink-2);
}
.oc-error .btn--sm {
  align-self: flex-start;
}
.mono {
  font-family: var(--font-mono);
}
</style>
