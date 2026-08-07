<template>
  <div class="admin-view">
    <header class="view-header">
      <h1 class="view-title">Admin</h1>
      <div ref="tabBar" class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
          <span v-if="badgeFor(tab.id) > 0" class="tab-badge">{{
            fmtBadge(badgeFor(tab.id))
          }}</span>
        </button>
      </div>
    </header>

    <AdminOverview
      v-if="activeTab === 'overview'"
      :backlog="backlog"
      :loading="loadingBacklog"
      :error="errorBacklog && !backlog"
      @refresh="loadBacklog"
      @navigate="navigateTo"
    />
    <AdminArtists v-else-if="activeTab === 'artists'" />
    <AdminFlags v-else-if="activeTab === 'flags'" />
    <AdminSets v-else-if="activeTab === 'sets'" />
    <AdminGenres v-else-if="activeTab === 'genres'" />
    <AdminCrawl v-else-if="activeTab === 'crawl'" />
    <AdminMonitoring v-else-if="activeTab === 'monitoring'" />
    <AdminBeatport v-else-if="activeTab === 'beatport'" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '../utils/api.js'
import AdminOverview from '../components/admin/AdminOverview.vue'
import AdminArtists from '../components/admin/AdminArtists.vue'
import AdminFlags from '../components/admin/AdminFlags.vue'
import AdminSets from '../components/admin/AdminSets.vue'
import AdminGenres from '../components/admin/AdminGenres.vue'
import AdminCrawl from '../components/admin/AdminCrawl.vue'
import AdminMonitoring from '../components/admin/AdminMonitoring.vue'
import AdminBeatport from '../components/admin/AdminBeatport.vue'

const tabs = [
  { id: 'overview', label: 'Aperçu' },
  { id: 'artists', label: 'Artistes' },
  { id: 'flags', label: 'Flags' },
  { id: 'sets', label: 'Sets' },
  { id: 'genres', label: 'Genres' },
  { id: 'crawl', label: 'Crawl' },
  { id: 'monitoring', label: 'Monitoring' },
  { id: 'beatport', label: 'Beatport' },
]

const activeTab = ref('overview')
const tabBar = ref(null)

// Navigation PROGRAMMATIQUE (clic sur une carte de renvoi de l'Aperçu) : l'onglet
// cible peut être hors-écran en mobile → on l'amène dans la vue de la barre. Les
// clics DIRECTS dans la barre gardent `@click="activeTab = tab.id"` et ne scrollent
// pas (l'onglet est déjà sous le doigt).
function navigateTo(id) {
  activeTab.value = id
  nextTick(() => {
    const bar = tabBar.value
    if (!bar || typeof bar.scrollBy !== 'function') return
    const active = bar.querySelector('.tab-btn.active')
    if (!active) return
    const delta = active.getBoundingClientRect().left - bar.getBoundingClientRect().left - 16
    bar.scrollBy({ left: delta, behavior: 'smooth' })
  })
}

// ── Backlog (A8) : un seul fetch alimente ET les badges d'onglets ET l'Aperçu. ──
const backlog = ref(null)
const loadingBacklog = ref(false)
const errorBacklog = ref(false)

async function loadBacklog() {
  loadingBacklog.value = true
  errorBacklog.value = false
  try {
    const { data } = await api.get('/api/admin/backlog')
    backlog.value = data
  } catch {
    errorBacklog.value = true
  } finally {
    loadingBacklog.value = false
  }
}
onMounted(loadBacklog)

// Badge d'onglet = somme des compteurs actionnables des chantiers portés par
// l'onglet. Aperçu et Monitoring n'en portent jamais. Masqué à 0 et tant que le
// backlog n'est pas chargé (backlog null → tout à 0).
const badges = computed(() => {
  const b = backlog.value
  if (!b) return {}
  return {
    artists: (b.artists?.to_link || 0) + (b.artists?.no_artwork || 0),
    flags: b.artist_flags?.pending || 0,
    sets: (b.sets?.recrawl || 0) + (b.sets?.flags_pending || 0),
    genres: (b.genres?.unclassified || 0) + (b.genres?.mappings_unmapped || 0),
    crawl: (b.crawl?.playlists_due || 0) + (b.crawl?.dlq || 0),
    beatport: b.beatport?.pending || 0,
  }
})
function badgeFor(id) {
  return badges.value[id] || 0
}
// Repère, pas donnée : abrégé au-delà de 9 999 (42 031 → « 42,0 k »).
function fmtBadge(n) {
  if (n > 9999) {
    return `${(n / 1000).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} k`
  }
  return n.toLocaleString('fr-FR')
}
</script>

<style scoped>
.admin-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1100px;
  margin: 0 auto;
}
.view-header {
  margin-bottom: var(--space-6);
}
.view-title {
  font: 600 var(--fs-lg)/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
  margin-bottom: var(--space-4);
}
/* Barre scrollable (A10) : jamais de wrap — la ligne de rupture bougerait avec
   la largeur des badges et ferait sauter la page à chaque backlog frais. */
.tab-bar {
  display: flex;
  gap: var(--space-1);
  border-bottom: 1px solid var(--line);
  padding-bottom: 0;
  overflow-x: auto;
  flex-wrap: nowrap;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
}
.tab-bar::-webkit-scrollbar {
  display: none;
}
.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  flex: none;
  white-space: nowrap;
  scroll-snap-align: start;
  min-height: var(--touch-min);
  padding: var(--space-2) var(--space-4);
  border: none;
  background: none;
  color: var(--ink-3);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition:
    color 0.12s,
    border-color 0.12s;
}
.tab-btn:hover {
  color: var(--ink);
}
.tab-btn.active {
  color: var(--accent-ink);
  border-bottom-color: var(--accent);
}
/* Badge (A9) : pastille mono nano, silencieuse au repos, accent sur l'onglet actif. */
.tab-badge {
  min-width: 20px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  color: var(--ink-2);
  font: 500 var(--fs-nano)/1 var(--font-mono);
}
.tab-btn.active .tab-badge {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
</style>
