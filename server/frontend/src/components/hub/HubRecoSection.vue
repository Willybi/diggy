<template>
  <!-- Skeleton while the reco feed loads (never before any item). -->
  <div v-if="recoLoading && !recoItems.length" class="discover discover--foryou" aria-busy="true">
    <h2 class="discover-title">Pour toi</h2>
    <div class="hb-shelfgrid">
      <DiscoveryCard v-for="n in 9" :key="n" skeleton />
    </div>
  </div>

  <!-- Personalized recommendations. Renders nothing once loaded with no items. -->
  <div v-else-if="recoItems.length" class="discover discover--foryou">
    <div class="discover-head">
      <h2 class="discover-title">Pour toi</h2>
      <RouterLink to="/radar" class="discover-more">
        Voir plus
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </RouterLink>
    </div>
    <div class="hb-shelfgrid">
      <DiscoveryCard
        v-for="track in recoItems"
        :key="track.id"
        :title="track.title"
        :artist="track.artist || ''"
        :cover-id="track.id"
        :has-artwork="track.has_artwork"
        :has-preview="track.has_preview"
        :in-lib="track.in_lib"
        :meta-parts="trackMeta(track)"
        :playing="catalogPlaying(track.id)"
        @open="openReco(track)"
        @play="playReco(track)"
      />
    </div>
  </div>
</template>

<script setup>
// « Pour toi » personalized recommendations shelf. Only mounted for authenticated
// users (the Hub gates it), so it carries no guest branches. Self-contained (owns
// its fetch + queue source) to stay lazy-loadable out of the Hub's main chunk.
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../utils/api.js'
import { useAudioPlayer } from '../../stores/audioPlayer'
import { fmtBpm, relativeAgeShort } from '../../utils/format.js'
import DiscoveryCard from '../DiscoveryCard.vue'

const router = useRouter()
const player = useAudioPlayer()

const recoItems = ref([])
const recoLoading = ref(false)

async function loadReco() {
  recoLoading.value = true
  try {
    // Trailing slash is REQUIRED: the route is defined at `/api/recommendations/`.
    // Hitting it slashless returns a 307 to the canonical path, and Safari/iOS
    // drops the Authorization header across that redirect → 401 → the response
    // interceptor auto-logs-out, kicking the user back to /login right after a
    // successful sign-in (desktop Chrome preserves the header, hence "works on PC").
    const { data } = await api.get('/api/recommendations/', { params: { limit: 9 } })
    recoItems.value = data.items || []
  } catch {
    /* silent — the Hub must never break on this */
  } finally {
    recoLoading.value = false
  }
}

onMounted(loadReco)

function openReco(track) {
  router.push(`/catalog/${track.id}`)
}

function recoToPlayerTrack(track) {
  return {
    id: track.id,
    catalog_id: track.id,
    title: track.title,
    artist: track.artist,
    artist_id: track.artist_id,
    bpm: track.bpm,
    key: track.key,
    has_preview: track.has_preview,
  }
}

// Queue source: "next" follows the « Pour toi » shelf as displayed.
const recoSource = {
  type: 'list',
  getItems: () => recoItems.value.map(recoToPlayerTrack),
}

function playReco(track) {
  player.play(recoToPlayerTrack(track), recoSource)
}

// BPM · KEY · brut age — the dense card meta line (component drops empty cells).
function trackMeta(t) {
  return [t.bpm ? fmtBpm(t.bpm) : '', t.key || '', relativeAgeShort(t.release_date)]
}
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
