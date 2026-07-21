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

      <h3 class="ds-h3 mono">
        buttons.css · état hover forcé <span class="ds-tag">.is-hover</span>
      </h3>
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

    <!-- 7 · COMPOSANTS TRANSVERSES (refonte D4) -->
    <section class="ds-section">
      <h2 class="ds-h2">7 · Composants transverses <span class="mono ds-tag">refonte D4</span></h2>

      <h3 class="ds-h3 mono">Artwork · tailles &amp; indicateur in-lib</h3>
      <div class="comp-row comp-row--wide">
        <div class="ds-aw ds-aw--hero"><Artwork size="hero" :in-lib="true" /></div>
        <div class="ds-aw ds-aw--card"><Artwork size="card" :in-lib="false" /></div>
        <Artwork size="row" :in-lib="true" />
        <Artwork size="row" :in-lib="false" />
        <Artwork size="row" />
      </div>

      <h3 class="ds-h3 mono">TrackCard · ligne (repos · artiste · playing · slot end)</h3>
      <div class="ds-stack">
        <TrackCard :track="demoTrack" />
        <TrackCard :track="demoTrack" :show-artist="true" />
        <TrackCard :track="demoTrack" :show-artist="true" :playing="true" />
        <TrackCard :track="{ ...demoTrack, has_preview: false }" :show-artist="true">
          <template #end><ScoreRing :score="0.86" size="sm" /></template>
        </TrackCard>
      </div>

      <h3 class="ds-h3 mono">
        TrackCard étendu · durée + artistes cliquables
        <span class="ds-tag">refonte Playlist Detail</span>
      </h3>
      <div class="ds-stack">
        <!-- défaut inchangé -->
        <TrackCard :track="demoTrackExt" :show-artist="true" />
        <!-- + colonne durée -->
        <TrackCard :track="demoTrackExt" :show-artist="true" :show-duration="true" />
        <!-- artistes cliquables (liens /artist/:id) -->
        <TrackCard :track="demoTrackDuo" :show-artist="true" :show-duration="true" />
        <!-- fallback chaîne plate (pas de artists[]) -->
        <TrackCard :track="demoTrack" :show-artist="true" :show-duration="true" />
        <!-- playing -->
        <TrackCard
          :track="demoTrackDuo"
          :show-artist="true"
          :show-duration="true"
          :playing="true"
        />
      </div>

      <h3 class="ds-h3 mono">
        TrackCard étendu · set (position · timecode · états ID)
        <span class="ds-tag">refonte Set Detail</span>
      </h3>
      <div class="ds-stack">
        <!-- identifiée · position · timecode lien -->
        <TrackCard
          :track="demoSetTrack"
          :show-artist="true"
          :show-duration="true"
          :position="1"
          :timecode="{ ms: 185000, href: '#' }"
        />
        <!-- timecode texte (non cliquable) -->
        <TrackCard
          :track="demoSetTrack"
          :show-artist="true"
          :show-duration="true"
          :position="2"
          :timecode="{ ms: 546000 }"
        />
        <!-- playing -->
        <TrackCard
          :track="demoSetTrack"
          :show-artist="true"
          :show-duration="true"
          :position="3"
          :timecode="{ ms: 1122000, href: '#' }"
          :playing="true"
        />
        <!-- état ID (non identifié) -->
        <TrackCard
          :track="demoSetTrack"
          :show-artist="true"
          :show-duration="true"
          :position="4"
          :timecode="{ ms: 1500000, href: '#' }"
          state="id"
        />
        <!-- état non résolu -->
        <TrackCard
          :track="demoSetUnresolved"
          :show-artist="true"
          :show-duration="true"
          :position="5"
          :timecode="{ ms: null }"
          state="unresolved"
        />
      </div>

      <h3 class="ds-h3 mono">ScoreRing · sm &amp; md</h3>
      <div class="comp-row">
        <ScoreRing :score="0" />
        <ScoreRing :score="0.3" />
        <ScoreRing :score="0.86" />
        <ScoreRing :score="1" />
        <ScoreRing :score="0.86" size="md" label="Similarité 9 /10" />
        <ScoreRing :score="1" size="md" />
      </div>

      <h3 class="ds-h3 mono">
        ScoreRing · mode % <span class="ds-tag">identified/total · Set Detail</span>
      </h3>
      <div class="comp-row">
        <ScoreRing :score="0" mode="pct" />
        <ScoreRing :score="0.69" mode="pct" />
        <ScoreRing :score="1" mode="pct" />
        <ScoreRing :score="0" mode="pct" size="md" />
        <ScoreRing :score="0.69" mode="pct" size="md" label="69 % de tracks identifiées" />
        <ScoreRing :score="1" mode="pct" size="md" />
      </div>

      <h3 class="ds-h3 mono">
        SetCard · carte set réutilisable <span class="ds-tag">refonte Set Detail</span>
      </h3>
      <div class="ds-setgrid">
        <!-- complète -->
        <SetCard :set="demoSet" />
        <!-- sans artwork -->
        <SetCard :set="{ ...demoSet, has_artwork: false }" />
        <!-- méta partielle (date omise) -->
        <SetCard :set="{ ...demoSet, played_date: null, artists: [] }" />
        <!-- slot footer (point d'extension) -->
        <SetCard :set="demoSet">
          <template #footer><ScoreRing :score="0.7" size="sm" /></template>
        </SetCard>
      </div>

      <h3 class="ds-h3 mono">PlatformLink · button (md / sm) &amp; glyph</h3>
      <div class="comp-row">
        <PlatformLink v-for="p in demoPlatforms" :key="p" :platform="p" href="#" />
      </div>
      <div class="comp-row">
        <PlatformLink v-for="p in demoPlatforms" :key="p" :platform="p" href="#" size="sm" />
      </div>
      <div class="comp-row">
        <PlatformLink v-for="p in demoPlatforms" :key="p" :platform="p" variant="glyph" />
      </div>
    </section>

    <!-- 8 · FILTRES (famille partagée Explorer/Radar) -->
    <section class="ds-section">
      <h2 class="ds-h2">8 · Filtres <span class="mono ds-tag">components/filters · D6</span></h2>

      <h3 class="ds-h3 mono">SearchInput · défaut / variante Label sans loupe / désactivé</h3>
      <div class="comp-row comp-row--fields">
        <SearchInput v-model="fltDemo.q" placeholder="Artiste, titre ou label…" />
        <SearchInput v-model="fltDemo.label" :icon="false" placeholder="Defected, Drumcode…" />
        <SearchInput model-value="" placeholder="Désactivé" disabled />
      </div>

      <h3 class="ds-h3 mono">RangeSlider · actif / plage complète (inactif) / désactivé</h3>
      <div class="comp-row comp-row--fields">
        <RangeSlider v-model="fltDemo.bpm" :min="60" :max="200" label="BPM" />
        <RangeSlider v-model="fltDemo.year" :min="1985" :max="2026" label="Année" />
        <RangeSlider :model-value="[100, 140]" :min="60" :max="200" label="BPM" disabled />
      </div>

      <h3 class="ds-h3 mono">CamelotSelect · 12×2 / variante drawer 6×4</h3>
      <div class="flt-vitrine-cam">
        <CamelotSelect v-model="fltDemo.keys" />
        <div class="flt-vitrine-cam-drawer">
          <CamelotSelect v-model="fltDemo.keys" variant="drawer" />
        </div>
      </div>

      <h3 class="ds-h3 mono">StyleMultiSelect · groupé par pilier, ring accent en sélection</h3>
      <StyleMultiSelect v-model="fltDemo.styles" :options="demoGenreOptions" />

      <h3 class="ds-h3 mono">ArtistTypeAhead · chips + recherche serveur (dropdown live)</h3>
      <div class="comp-row comp-row--fields">
        <ArtistTypeAhead v-model="fltDemo.artists" />
      </div>

      <h3 class="ds-h3 mono">
        SegmentedFilter · tri-state « Tous » / presets mono (re-clic = désélection)
      </h3>
      <div class="comp-row">
        <SegmentedFilter v-model="fltDemo.inlib" :options="demoInLibOptions" />
        <SegmentedFilter v-model="fltDemo.duration" :options="demoDurationOptions" mono />
        <SegmentedFilter model-value="a" :options="[{ value: 'a', label: 'Désactivé' }]" disabled />
      </div>

      <h3 class="ds-h3 mono">ToggleChip &amp; SortSelect</h3>
      <div class="comp-row">
        <ToggleChip v-model="fltDemo.preview" label="Écoutable uniquement">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M8 5v14l11-7z" stroke-linejoin="round" />
            </svg>
          </template>
        </ToggleChip>
        <ToggleChip :model-value="false" label="Désactivé" disabled />
        <SortSelect v-model="fltSort" :options="demoSortOptions" />
      </div>

      <h3 class="ds-h3 mono">FilterChip · chip / valeur longue / variante empty-state (hover --neg)</h3>
      <div class="comp-row">
        <FilterChip label="BPM" value="120–133" />
        <FilterChip label="Key" value="5A 6A 7A 6B" />
        <FilterChip label="Style" value="Tech House" empty />
      </div>

      <h3 class="ds-h3 mono">FilterBar · assemblage complet (barre + badge + chips + panneau inline)</h3>
      <FilterBar
        v-model:filters="fltDemo"
        v-model:panelOpen="fltPanelOpen"
        v-model:drawerOpen="fltDrawerOpen"
        :criteria="demoCriteria"
        :result-count="1234"
      >
        <template #search>
          <SearchInput v-model="fltDemo.q" placeholder="Artiste, titre ou label…" />
        </template>
        <template #sort>
          <SortSelect v-model="fltSort" :options="demoSortOptions" />
        </template>
        <template #panel>
          <FilterPanel :result-count="1234" @reset="resetFltDemo" @close="closeFltPanel">
            <div class="flt-field">
              <span class="flt-label">BPM</span>
              <RangeSlider v-model="fltDemo.bpm" :min="60" :max="200" label="BPM" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Année</span>
              <RangeSlider v-model="fltDemo.year" :min="1985" :max="2026" label="Année" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Durée</span>
              <SegmentedFilter v-model="fltDemo.duration" :options="demoDurationOptions" mono />
            </div>
            <div class="flt-field flt-field--4">
              <span class="flt-label">Key</span>
              <CamelotSelect v-model="fltDemo.keys" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Bibliothèque</span>
              <SegmentedFilter v-model="fltDemo.inlib" :options="demoInLibOptions" />
            </div>
            <div class="flt-field flt-field--4">
              <span class="flt-label">Styles</span>
              <StyleMultiSelect v-model="fltDemo.styles" :options="demoGenreOptions" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Artiste</span>
              <ArtistTypeAhead v-model="fltDemo.artists" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Label</span>
              <SearchInput v-model="fltDemo.label" :icon="false" placeholder="Defected, Drumcode…" />
            </div>
            <div class="flt-field">
              <span class="flt-label">Extrait audio</span>
              <ToggleChip v-model="fltDemo.preview" label="Écoutable uniquement" />
            </div>
          </FilterPanel>
        </template>
      </FilterBar>

      <h3 class="ds-h3 mono">FilterDrawer · bottom-sheet mobile</h3>
      <button class="btn" @click="openFltDrawer">Ouvrir le drawer</button>
      <FilterDrawer v-model:open="fltDrawerOpen" :result-count="1234" @reset="resetFltDemo">
        <div class="flt-field">
          <span class="flt-label">BPM</span>
          <RangeSlider v-model="fltDemo.bpm" :min="60" :max="200" label="BPM" />
        </div>
        <div class="flt-field">
          <span class="flt-label">Key</span>
          <CamelotSelect v-model="fltDemo.keys" variant="drawer" />
        </div>
        <div class="flt-field">
          <span class="flt-label">Bibliothèque</span>
          <SegmentedFilter v-model="fltDemo.inlib" :options="demoInLibOptions" variant="drawer" />
        </div>
        <div class="flt-field">
          <span class="flt-label">Styles</span>
          <StyleMultiSelect v-model="fltDemo.styles" :options="demoGenreOptions" variant="drawer" />
        </div>
        <div class="flt-field">
          <span class="flt-label">Extrait audio</span>
          <ToggleChip v-model="fltDemo.preview" label="Écoutable uniquement" variant="drawer" />
        </div>
      </FilterDrawer>
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
import Artwork from '../components/Artwork.vue'
import TrackCard from '../components/TrackCard.vue'
import ScoreRing from '../components/ScoreRing.vue'
import PlatformLink from '../components/PlatformLink.vue'
import SetCard from '../components/SetCard.vue'
import FilterBar from '../components/filters/FilterBar.vue'
import FilterChip from '../components/filters/FilterChip.vue'
import FilterPanel from '../components/filters/FilterPanel.vue'
import FilterDrawer from '../components/filters/FilterDrawer.vue'
import SearchInput from '../components/filters/SearchInput.vue'
import RangeSlider from '../components/filters/RangeSlider.vue'
import CamelotSelect from '../components/filters/CamelotSelect.vue'
import StyleMultiSelect from '../components/filters/StyleMultiSelect.vue'
import ArtistTypeAhead from '../components/filters/ArtistTypeAhead.vue'
import SegmentedFilter from '../components/filters/SegmentedFilter.vue'
import ToggleChip from '../components/filters/ToggleChip.vue'
import SortSelect from '../components/filters/SortSelect.vue'
import { compareCamelot } from '../components/filters/camelot.js'
import { defaultValue } from '../components/filters/criteria.js'

const demoTrack = {
  id: 0,
  title: 'Strobe (Club Mix)',
  artist: 'deadmau5',
  bpm: 128,
  key: '9A',
  has_artwork: false,
  has_preview: true,
  in_lib: true,
}
// Extension demos: with a duration, and with clickable artists[].
const demoTrackExt = { ...demoTrack, duration_ms: 384000 }
const demoTrackDuo = {
  ...demoTrack,
  title: 'Move for Me',
  artist: 'Kaskade, deadmau5',
  duration_ms: 447000,
  artists: [
    { id: 1, name: 'Kaskade' },
    { id: 2, name: 'deadmau5' },
  ],
}
const demoPlatforms = [
  'beatport',
  'deezer',
  'tidal',
  'soundcloud',
  'youtube',
  'spotify',
  'trackid',
  '1001tl',
]
// Set-row extension demos (position · timecode · states).
const demoSetTrack = {
  id: 0,
  title: 'Opus (Four Tet Remix)',
  artist: 'Eric Prydz',
  bpm: 124,
  key: '4A',
  duration_ms: 546000,
  has_artwork: false,
  has_preview: true,
  in_lib: true,
  artists: [{ id: 1, name: 'Eric Prydz' }],
}
const demoSetUnresolved = {
  id: 0,
  title: 'Unknown bootleg — ID',
  artist: 'Unknown Artist',
  has_artwork: false,
  has_preview: false,
  in_lib: false,
}
// SetCard demo (contract GET /api/sets/{id}/similar — artists[] are plain names).
const demoSet = {
  id: 0,
  title: 'Cercle: Sébastien Léger @ Le Panthéon, Paris',
  source: 'youtube',
  played_date: '2023-11-18',
  duration_ms: 5460000,
  has_artwork: false,
  total_tracks: 22,
  identified_tracks: 15,
  artists: ['Sébastien Léger'],
}

// ── Section 8 · Filtres — demo state ──
const demoInLibOptions = [
  { value: null, label: 'Tous' },
  { value: 'in', label: 'Dans ma bib' },
  { value: 'out', label: 'Pas dans RB' },
]
const demoDurationOptions = [
  { value: 'lt3', label: '< 3 min' },
  { value: '3-5', label: '3–5 min' },
  { value: '5-8', label: '5–8 min' },
  { value: 'gt8', label: '> 8 min' },
]
const demoSortOptions = [
  { value: 'recent', label: 'Récemment ajoutés' },
  { value: 'title', label: 'Titre A–Z' },
  { value: 'artist', label: 'Artiste A–Z' },
  { value: 'bpm', label: 'BPM' },
  { value: 'key', label: 'Key (harmonique)' },
  { value: 'duration', label: 'Durée' },
  { value: 'release', label: 'Date de sortie' },
]
const demoGenreOptions = [
  { name: 'House', count: 4120, pillar: 'house', depth: 0 },
  { name: 'Tech House', count: 1284, pillar: 'house', depth: 1 },
  { name: 'Deep House', count: 940, pillar: 'house', depth: 1 },
  { name: 'Techno', count: 3860, pillar: 'techno', depth: 0 },
  { name: 'Hard Techno', count: 720, pillar: 'techno', depth: 1 },
  { name: 'Trance', count: 1520, pillar: 'trance', depth: 0 },
  { name: 'Psytrance', count: 410, pillar: 'trance', depth: 1 },
  { name: 'Drum & Bass', count: 980, pillar: 'dnb', depth: 0 },
  { name: 'Hardcore', count: 310, pillar: 'hardcore', depth: 0 },
  { name: 'Hardstyle', count: 260, pillar: 'harddance', depth: 1 },
  { name: 'Ambient', count: 240, pillar: 'autres', depth: 0 },
]
const demoCriteria = [
  { key: 'q', type: 'text', label: 'Recherche', chip: false },
  { key: 'bpm', type: 'range', label: 'BPM', min: 60, max: 200 },
  { key: 'year', type: 'range', label: 'Année', min: 1985, max: 2026 },
  { key: 'keys', type: 'multi', label: 'Key', sort: compareCamelot },
  { key: 'styles', type: 'multi', label: 'Style', chipPerValue: true },
  {
    key: 'artists',
    type: 'multi',
    label: 'Artiste',
    chipPerValue: true,
    format: (a) => a.name,
  },
  { key: 'inlib', type: 'segment', label: 'Bibliothèque', options: demoInLibOptions },
  { key: 'duration', type: 'segment', label: 'Durée', options: demoDurationOptions },
  { key: 'preview', type: 'toggle', label: 'Extrait', valueLabel: 'Écoutable' },
  { key: 'label', type: 'text', label: 'Label' },
]
const fltDemo = ref({
  q: '',
  bpm: [120, 133],
  year: [1985, 2026],
  keys: ['6B', '7A', '5A', '6A'],
  styles: ['Tech House'],
  artists: [{ id: 1, name: 'Kaskade' }],
  inlib: 'in',
  duration: null,
  preview: true,
  label: '',
})
const fltSort = ref('recent')
const fltPanelOpen = ref(true)
const fltDrawerOpen = ref(false)

function resetFltDemo() {
  const next = {}
  for (const c of demoCriteria) next[c.key] = defaultValue(c)
  fltDemo.value = next
}

function closeFltPanel() {
  fltPanelOpen.value = false
}

function openFltDrawer() {
  fltDrawerOpen.value = true
}

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
  {
    title: 'Positif · in-lib',
    swatches: mk(['--pos', '--pos-soft', '--pos-ink', '--pos-wash', '--pos-wash-2']),
  },
  { title: 'Négatif · dislike', swatches: mk(['--neg', '--neg-soft', '--neg-ink']) },
  { title: 'Warning', swatches: mk(['--warn', '--warn-soft', '--warn-ink']) },
  { title: 'Erreur', swatches: mk(['--error']) },
  {
    title: 'Tuiles genre',
    swatches: mk([
      '--genre-tile-ink',
      '--genre-tile-scrim',
      '--genre-tile-shadow',
      '--genre-tile-border-dark',
    ]),
  },
  {
    title: 'Hero scrim (composé aux alphas d’usage)',
    swatches: [
      {
        name: '--hero-scrim / 0.7',
        value: 'oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.7)',
      },
      {
        name: '--hero-scrim / 0.6',
        value: 'oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.6)',
      },
      {
        name: '--hero-scrim / 0.3',
        value: 'oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.3)',
      },
    ],
  },
  {
    title: 'Overlays (invariants)',
    swatches: mk(['--overlay-modal', '--overlay-soft', '--overlay-text']),
  },
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
.comp-row--wide {
  align-items: flex-end;
  gap: var(--space-5);
}

/* 8 · filters showcase */
.comp-row--fields {
  align-items: flex-start;
}
.comp-row--fields > * {
  flex: 1 1 220px;
  max-width: 400px;
}
.flt-vitrine-cam {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--space-5);
}
.flt-vitrine-cam > :first-child {
  flex: 1 1 420px;
  min-width: 0;
}
.flt-vitrine-cam-drawer {
  width: 260px;
  flex: none;
}

/* 7 · transverse components showcase */
.ds-aw--hero {
  width: 216px;
}
.ds-aw--card {
  width: 120px;
}
.ds-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-width: 420px;
}
.ds-setgrid {
  display: grid;
  grid-template-columns: repeat(4, minmax(150px, 1fr));
  gap: var(--space-4);
  max-width: 720px;
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
