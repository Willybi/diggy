<template>
  <!-- Stays mounted (chips included) whenever there are trends OR a family is
       selected, so a family with 0 visible tracks never traps the user — they
       can always switch back via the chips. Renders nothing otherwise. -->
  <div v-if="trendTracks.length || trendFamily !== 'all'" class="discover">
    <div class="discover-head">
      <h2 class="discover-title">Ça sort en ce moment</h2>
      <RouterLink :to="auth.isAuthenticated ? '/radar' : '/login'" class="discover-more">
        Voir plus
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </RouterLink>
    </div>
    <FamilyChips v-model="trendFamily" :counts="trendFamilyCounts" />
    <div v-if="trendTracks.length" class="hb-shelfgrid">
      <DiscoveryCard
        v-for="track in trendTracks"
        :key="track.catalog_id"
        :title="track.title"
        :artist="track.artist || ''"
        :cover-id="track.catalog_id"
        :has-artwork="track.has_artwork"
        :has-preview="track.has_preview"
        :rank="track.rank"
        :meta-parts="trackMeta(track)"
        :playing="catalogPlaying(track.catalog_id)"
        @open="openTrend(track)"
        @play="playTrend(track)"
      />
    </div>
    <div v-else class="discover-empty">Aucune sortie dans ce style pour l'instant.</div>
  </div>
</template>

<script setup>
// « Ça sort en ce moment » discovery shelf — trend tracks by family. Self-contained
// (owns its fetch + queue source) so it can be lazy-loaded out of the Hub's main
// chunk. Shown to guests and members alike; the « Voir plus » destination and the
// open-track guard adapt to the auth state.
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../utils/api.js'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../stores/toast.js'
import { useAudioPlayer } from '../../stores/audioPlayer'
import { fmtBpm, relativeAgeShort } from '../../utils/format.js'
import FamilyChips from '../FamilyChips.vue'
import DiscoveryCard from '../DiscoveryCard.vue'

const router = useRouter()
const auth = useAuthStore()
const player = useAudioPlayer()
const toast = useToast()

const trendFamily = ref('all')
const trendTracks = ref([])
const trendFamilyCounts = ref({})

async function loadTrends() {
  try {
    const params = { limit: 9 }
    if (trendFamily.value !== 'all') params.family = trendFamily.value
    const { data } = await api.get('/api/radar/trends', { params })
    trendTracks.value = data.items || []
    trendFamilyCounts.value = data.family_counts || {}
  } catch {
    /* silent */
  }
}

watch(trendFamily, loadTrends)
onMounted(loadTrends)

function openTrend(track) {
  if (!auth.isAuthenticated) {
    toast.show('Connecte-toi pour ouvrir cette fiche.', 'info', 3000, {
      label: 'Se connecter',
      route: '/login',
    })
    return
  }
  router.push(`/catalog/${track.catalog_id}`)
}

function trendToPlayerTrack(track) {
  return {
    id: track.catalog_id,
    catalog_id: track.catalog_id,
    title: track.title,
    artist: track.artist,
    artist_id: track.artist_id,
    bpm: track.bpm,
    key: track.key,
    has_preview: track.has_preview,
  }
}

// Queue source: "next" follows the « Ça sort » shelf as displayed.
const trendSource = {
  type: 'list',
  getItems: () => trendTracks.value.map(trendToPlayerTrack),
}

function playTrend(track) {
  player.play(trendToPlayerTrack(track), trendSource)
}

// BPM · KEY · brut age — the dense card meta line (component drops empty cells).
function trackMeta(t) {
  return [t.bpm ? fmtBpm(t.bpm) : '', t.key || '', relativeAgeShort(t.release_date)]
}
// A card is "playing" when the global player holds that catalog id.
function catalogPlaying(catalogId) {
  return catalogId != null && player.track?.catalog_id === catalogId && player.playing
}
</script>

<style scoped>
.discover {
  width: 100%;
  max-width: 960px;
  margin: var(--space-2) auto 0;
}
.discover-title {
  font: 600 var(--fs-md)/1 var(--font-ui);
  color: var(--ink);
  margin: 0 0 var(--space-4);
}
/* header row: title + « voir plus » link */
.discover-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
}
.discover-head .discover-title {
  margin: 0;
}
.discover-more {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  flex: none;
  font: 500 var(--fs-sm) var(--font-ui);
  color: var(--accent-ink);
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.12s;
}
.discover-more:hover {
  color: var(--accent);
}
.discover-more svg {
  width: 14px;
  height: 14px;
}
.discover-empty {
  padding: var(--space-6) 0;
  text-align: center;
  color: var(--ink-3);
  font: 500 var(--fs-sm) var(--font-mono);
}
.discover :deep(.fam-chips) {
  padding: 0 0 var(--space-4);
}
/* Shelf grid: 3 → 2 → 1 col. minmax(0,1fr) so a 64px cover never blows a column
   past its share (grid 1fr = minmax(auto,1fr) otherwise). */
.hb-shelfgrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3);
  padding: 0 0 var(--space-4);
}

@container app (max-width: 720px) {
  .hb-shelfgrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container app (max-width: 640px) {
  .discover {
    max-width: 100%;
  }
  .hb-shelfgrid {
    grid-template-columns: 1fr;
  }
}
</style>
