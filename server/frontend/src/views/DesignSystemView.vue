<template>
  <div ref="dsRoot" class="ds">
    <div class="ds-toolbar">
      <button class="btn btn--sm" @click="toggle">
        {{ isDark ? 'Mode clair' : 'Mode sombre' }}
      </button>
      <button class="btn btn--sm btn--accent" :disabled="exporting" @click="exportPng">
        {{ exporting ? 'Export…' : 'Exporter PNG' }}
      </button>
    </div>
    <header class="ds-head">
      <h1 class="ds-title">Design System</h1>
      <p class="ds-note">
        Vitrine de non-régression visuelle · <b>dev only</b> · aucun style en dur, tout via
        <span class="mono">var(--…)</span>.
      </p>
    </header>

    <!-- 1 · COULEURS -->
    <section class="ds-section">
      <h2 class="ds-h2">1 · Couleurs sémantiques <span class="ds-tag">light / dark</span></h2>
      <div class="themes">
        <div v-for="th in ['light', 'dark']" :key="th" class="panel" :data-theme="th">
          <span class="panel-lbl mono">{{ th }}</span>
          <div v-for="grp in colorGroups" :key="grp.title" class="cgroup">
            <h3 class="cgroup-title mono">{{ grp.title }}</h3>
            <div class="swatches">
              <div v-for="c in grp.swatches" :key="c.name" class="swatch">
                <span class="chip" :style="{ background: c.value }"></span>
                <span class="chip-name mono">{{ c.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 2 · SPACING -->
    <section class="ds-section">
      <h2 class="ds-h2">2 · Échelle spacing <span class="mono ds-tag">--space-*</span></h2>
      <div class="scale">
        <div v-for="s in spaceTokens" :key="s" class="scale-row">
          <span class="scale-name mono">{{ s }}</span>
          <span class="scale-bar" :style="{ width: `var(${s})` }"></span>
          <span class="scale-val mono">{{ computed[s] }}</span>
        </div>
      </div>
    </section>

    <!-- 3 · FONT-SIZE -->
    <section class="ds-section">
      <h2 class="ds-h2">3 · Échelle font-size <span class="mono ds-tag">--fs-*</span></h2>
      <div class="fs-list">
        <div v-for="f in fsTokens" :key="f.name" class="fs-row">
          <span class="fs-meta mono">
            {{ f.name }} · {{ computed[f.name] }}
            <em v-if="f.note" class="fs-note">{{ f.note }}</em>
          </span>
          <span
            class="fs-specimen"
            :style="{
              fontSize: `var(${f.name})`,
              fontFamily: f.mono ? 'var(--font-mono)' : 'var(--font-ui)',
            }"
            >Diggy — Aa Gg 0123</span
          >
        </div>
      </div>
      <p class="ds-note">
        Exception hors-échelle : les titres hero utilisent <span class="mono">clamp()</span>
        (responsive display, cf. design-decisions.md §2bis).
      </p>
    </section>

    <!-- 4 · RADII + OMBRES -->
    <section class="ds-section">
      <h2 class="ds-h2">4 · Radii &amp; ombres</h2>
      <div class="tiles">
        <div v-for="r in radiusTokens" :key="r" class="tile" :style="{ borderRadius: `var(${r})` }">
          <span class="mono">{{ r }}</span>
          <span class="mono tile-val">{{ computed[r] }}</span>
        </div>
      </div>
      <div class="tiles tiles--shadow">
        <div v-for="sh in shadowTokens" :key="sh" class="tile" :style="{ boxShadow: `var(${sh})` }">
          <span class="mono">{{ sh }}</span>
        </div>
      </div>
    </section>

    <!-- 5 · DENSITÉ -->
    <section class="ds-section">
      <h2 class="ds-h2">
        5 · Densité <span class="mono ds-tag">[data-density] → var(--pad) / var(--row-h)</span>
      </h2>
      <div class="density">
        <div v-for="d in densities" :key="d.label" class="dcol" :data-density="d.mode">
          <span class="dcol-lbl mono">{{ d.label }}</span>
          <div class="dcard">
            <div class="dcard-art"></div>
            <div class="dcard-body">
              <span class="dcard-title">Titre de carte</span>
              <span class="dcard-sub mono">padding: var(--pad)</span>
            </div>
          </div>
          <div class="dtable">
            <div v-for="n in 3" :key="n" class="dtr">
              <span class="dtd">Track {{ n }}</span>
              <span class="dtd mono">12{{ n }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 6 · COMPOSANTS -->
    <section class="ds-section">
      <h2 class="ds-h2">6 · Composants</h2>

      <h3 class="ds-h3 mono">buttons.css · survol &amp; focus interactifs</h3>
      <div class="comp-row">
        <button class="btn">Ghost</button>
        <button class="btn btn--accent">Accent</button>
        <button class="btn btn--ghost-accent">Ghost accent</button>
        <button class="btn btn--sm">Small</button>
        <button class="btn btn--danger">Danger</button>
        <button class="btn" disabled>Disabled</button>
      </div>

      <h3 class="ds-h3 mono">buttons.css · état hover forcé <span class="ds-tag">.is-hover</span></h3>
      <div class="comp-row">
        <button class="btn is-hover">Ghost</button>
        <button class="btn btn--accent is-hover">Accent</button>
        <button class="btn btn--ghost-accent is-hover">Ghost accent</button>
        <button class="btn btn--sm is-hover">Small</button>
        <button class="btn btn--danger is-hover">Danger</button>
      </div>

      <h3 class="ds-h3 mono">Badges</h3>
      <div class="comp-row">
        <InLibBadge :in-lib="true" />
        <InLibBadge :in-lib="false" />
        <SourceBadge source="deezer" />
        <SourceBadge source="tidal" />
        <SourceBadge source="spotify" />
        <ScorePill :score="7.5" />
      </div>

      <h3 class="ds-h3 mono">StyleTag · piliers de genre (hues)</h3>
      <div class="comp-row">
        <StyleTag name="House" family="house" />
        <StyleTag name="Techno" family="techno" />
        <StyleTag name="Trance" family="trance" />
        <StyleTag name="Drum &amp; Bass" family="dnb" />
        <StyleTag name="Hardcore" family="hardcore" />
        <StyleTag name="Hard Dance" family="harddance" />
        <StyleTag name="Autres" family="autres" />
      </div>

      <h3 class="ds-h3 mono">.page-head (partagé · assets/page.css)</h3>
      <div class="page-head ds-pagehead">
        <div class="titles">
          <h1>Titre de page</h1>
          <div class="sub mono">1 234 éléments</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { domToPng } from 'modern-screenshot'
import { useTheme } from '../composables/useTheme.js'
import InLibBadge from '../components/InLibBadge.vue'
import SourceBadge from '../components/SourceBadge.vue'
import ScorePill from '../components/ScorePill.vue'
import StyleTag from '../components/StyleTag.vue'

const mk = (names) => names.map((n) => ({ name: n, value: `var(${n})` }))

const colorGroups = [
  {
    title: 'Neutres',
    swatches: mk([
      '--bg',
      '--surface',
      '--surface-2',
      '--surface-3',
      '--ink',
      '--ink-2',
      '--ink-3',
      '--line',
      '--line-2',
    ]),
  },
  {
    title: 'Accent',
    swatches: mk([
      '--accent',
      '--accent-hover',
      '--accent-soft',
      '--accent-soft-2',
      '--accent-ink',
      '--on-accent',
      '--accent-wash',
    ]),
  },
  { title: 'Positif · in-lib', swatches: mk(['--pos', '--pos-soft', '--pos-ink', '--pos-wash', '--pos-wash-2']) },
  { title: 'Négatif · dislike', swatches: mk(['--neg', '--neg-soft', '--neg-ink']) },
  { title: 'Warning', swatches: mk(['--warn', '--warn-soft', '--warn-ink']) },
  { title: 'Erreur', swatches: mk(['--error']) },
  {
    title: 'Tuiles genre',
    swatches: mk(['--genre-tile-ink', '--genre-tile-scrim', '--genre-tile-shadow', '--genre-tile-border-dark']),
  },
  {
    title: 'Hero scrim (composé aux alphas d’usage)',
    swatches: [
      { name: '--hero-scrim / 0.7', value: 'oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.7)' },
      { name: '--hero-scrim / 0.6', value: 'oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.6)' },
      { name: '--hero-scrim / 0.3', value: 'oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.3)' },
    ],
  },
  { title: 'Overlays (invariants)', swatches: mk(['--overlay-modal', '--overlay-soft', '--overlay-text']) },
]

const spaceTokens = [
  '--space-05',
  '--space-1',
  '--space-15',
  '--space-2',
  '--space-25',
  '--space-3',
  '--space-4',
  '--space-5',
  '--space-6',
  '--space-8',
  '--space-10',
  '--space-15x',
]

const fsTokens = [
  { name: '--fs-nano', mono: true, note: 'badges / clés nano' },
  { name: '--fs-label', mono: true, note: 'en-têtes de table, micro-labels' },
  { name: '--fs-xs' },
  { name: '--fs-table-sm', mono: true, note: 'réservé tables' },
  { name: '--fs-sm' },
  { name: '--fs-base' },
  { name: '--fs-table', note: 'réservé tables' },
  { name: '--fs-title', note: 'titres section / carte' },
  { name: '--fs-input', note: 'min 16px — zoom iOS au focus' },
  { name: '--fs-md' },
  { name: '--fs-lg', note: 'view titles' },
  { name: '--fs-xl' },
  { name: '--fs-fallback', note: 'initiales avatar / hero' },
  { name: '--fs-display' },
  { name: '--fs-hero', note: 'mot display Hub' },
]

const radiusTokens = ['--r-xs', '--r-sm', '--r-md', '--r-lg', '--r-xl', '--r-pill']
const shadowTokens = ['--shadow-sm', '--shadow-md', '--shadow-lg']

const densities = [
  { mode: 'compact', label: 'Compact' },
  { mode: null, label: 'Normal (défaut)' },
  { mode: 'comfy', label: 'Confort' },
]

const { isDark, toggle } = useTheme()
const dsRoot = ref(null)
const exporting = ref(false)

async function exportPng() {
  exporting.value = true
  try {
    const dataUrl = await domToPng(dsRoot.value, {
      scale: 2,
      filter: (node) => !node.classList?.contains('ds-toolbar'),
    })
    const link = document.createElement('a')
    link.href = dataUrl
    link.download = `design-system-${isDark.value ? 'dark' : 'light'}-${new Date().toISOString().slice(0, 10)}.png`
    link.click()
  } finally {
    exporting.value = false
  }
}

const computed = ref({})
onMounted(() => {
  const cs = window.getComputedStyle(document.documentElement)
  const map = {}
  ;[...spaceTokens, ...fsTokens.map((f) => f.name), ...radiusTokens].forEach((t) => {
    map[t] = cs.getPropertyValue(t).trim()
  })
  computed.value = map
})
</script>

<style scoped>
.ds {
  min-height: 100%;
  background: var(--bg);
  color: var(--ink);
  padding: var(--space-8) var(--page-px);
  max-width: var(--page-max-w);
  margin-inline: auto;
  font-family: var(--font-ui);
}
.mono {
  font-family: var(--font-mono);
}
.ds-toolbar {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
  display: flex;
  gap: var(--space-2);
  z-index: 10;
}
.ds-head {
  margin-bottom: var(--space-10);
}
.ds-title {
  margin: 0;
  font: 600 var(--fs-display)/1.1 var(--font-ui);
  letter-spacing: -0.02em;
}
.ds-note {
  margin: var(--space-2) 0 0;
  font-size: var(--fs-sm);
  color: var(--ink-3);
}
.ds-section {
  margin-bottom: var(--space-15x);
}
.ds-h2 {
  font: 600 var(--fs-lg)/1.2 var(--font-ui);
  margin: 0 0 var(--space-5);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--line);
}
.ds-h3 {
  font-size: var(--fs-label);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-3);
  margin: var(--space-6) 0 var(--space-3);
}
.ds-tag {
  font-size: var(--fs-sm);
  font-weight: 400;
  color: var(--ink-3);
}

/* 1 · colours */
.themes {
  display: flex;
  gap: var(--space-5);
  flex-wrap: wrap;
}
.panel {
  flex: 1 1 0;
  min-width: 0;
  background: var(--bg);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  padding: var(--space-5);
}
.panel-lbl {
  display: inline-block;
  font-size: var(--fs-label);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  margin-bottom: var(--space-4);
}
.cgroup + .cgroup {
  margin-top: var(--space-5);
}
.cgroup-title {
  font-size: var(--fs-xs);
  color: var(--ink-2);
  margin: 0 0 var(--space-2);
}
.swatches {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}
.swatch {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: var(--space-15x);
}
.chip {
  height: var(--space-10);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
}
.chip-name {
  font-size: var(--fs-nano);
  color: var(--ink-3);
  overflow-wrap: anywhere;
}

/* 2 · spacing */
.scale {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.scale-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.scale-name {
  font-size: var(--fs-sm);
  color: var(--ink-2);
  width: var(--space-15x);
  flex: none;
}
.scale-bar {
  height: var(--space-3);
  background: var(--accent);
  border-radius: var(--r-xs);
  flex: none;
}
.scale-val {
  font-size: var(--fs-xs);
  color: var(--ink-3);
}

/* 3 · font-size */
.fs-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.fs-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-5);
  flex-wrap: wrap;
}
.fs-meta {
  font-size: var(--fs-xs);
  color: var(--ink-2);
  width: var(--page-px);
  min-width: var(--space-15x);
  flex: none;
}
.fs-note {
  display: block;
  font-style: normal;
  color: var(--ink-3);
}
.fs-specimen {
  color: var(--ink);
  line-height: 1.1;
}

/* 4 · radii + shadows */
.tiles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
}
.tiles--shadow {
  margin-top: var(--space-6);
}
.tile {
  width: var(--space-15x);
  height: var(--space-15x);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-05);
  background: var(--surface);
  border: 1px solid var(--line);
  font-size: var(--fs-nano);
  color: var(--ink-2);
  text-align: center;
}
.tiles--shadow .tile {
  border: none;
}
.tile-val {
  color: var(--ink-3);
}

/* 5 · density */
.density {
  display: flex;
  gap: var(--space-6);
  flex-wrap: wrap;
}
.dcol {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: var(--sidebar-w);
}
.dcol-lbl {
  font-size: var(--fs-xs);
  color: var(--ink-3);
}
.dcard {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.dcard-art {
  height: var(--space-15x);
  background: var(--surface-3);
}
.dcard-body {
  padding: var(--pad);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.dcard-title {
  font-size: var(--fs-title);
  font-weight: 600;
}
.dcard-sub {
  font-size: var(--fs-xs);
  color: var(--ink-3);
}
.dtable {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.dtr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--row-h);
  padding: 0 var(--pad);
  gap: var(--space-3);
}
.dtr + .dtr {
  border-top: 1px solid var(--line);
}
.dtd {
  font-size: var(--fs-table);
  color: var(--ink);
}

/* 6 · components */
.comp-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}
.ds-pagehead {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.ds-pagehead .titles h1 {
  margin: 0;
  font: 600 var(--fs-xl)/1 var(--font-ui);
  color: var(--ink);
}
.ds-pagehead .sub {
  margin-top: var(--space-1);
  font-size: var(--fs-sm);
  color: var(--ink-2);
}
</style>
