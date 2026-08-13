<template>
  <div v-if="activityItems.length" class="discover discover--activity">
    <div class="discover-head">
      <h2 class="discover-title">
        Nouveautés de tes artistes
        <span v-if="activityNewCount > 0" class="ac-new-badge">
          {{ activityNewCount }} nouvelle{{ activityNewCount > 1 ? 's' : '' }}
        </span>
      </h2>
      <!-- /new-releases doesn't exist yet → inert « Bientôt » (no dead link) -->
      <span class="discover-more is-disabled" aria-disabled="true">Bientôt</span>
    </div>
    <div class="hb-shelfgrid">
      <template v-for="entry in activityShelf" :key="activityKey(entry)">
        <!-- grouped release (2+ tracks share an album) → one expandable card -->
        <ActivityAlbumCard
          v-if="entry.kind === 'album'"
          :album="entry"
          @play="playActivityTrack"
          @open="openActivityTrack"
        />
        <!-- crawled release → full track card (cover, preview, release age) -->
        <DiscoveryCard
          v-else-if="entry.item.type === 'release' && entry.item.catalog_id"
          :title="entry.item.title"
          :artist="entry.item.artist || entry.item.artist_name || ''"
          :cover-id="entry.item.catalog_id"
          :has-artwork="entry.item.has_artwork"
          :has-preview="entry.item.has_preview"
          badge="Nouveauté"
          :meta-parts="trackMeta(entry.item)"
          :playing="catalogPlaying(entry.item.catalog_id)"
          @open="openActivityTrack(entry.item)"
          @play="playActivityTrack(entry.item)"
        />
        <!-- release we could not crawl → external Deezer link fallback -->
        <DiscoveryCard
          v-else-if="entry.item.type === 'release'"
          :title="entry.item.title"
          :artist="entry.item.artist_name || ''"
          badge="Nouveauté"
          badge-icon="ext"
          :href="entry.item.external_url"
          :meta-parts="externalReleaseMeta(entry.item)"
        />
        <!-- followed-artist set -->
        <DiscoveryCard
          v-else
          :title="entry.item.title"
          :artist="entry.item.artist_name || ''"
          badge="Set"
          badge-icon="set"
          :meta-parts="setMeta(entry.item)"
          @open="openSet(entry.item)"
        />
      </template>
    </div>
  </div>
</template>

<script setup>
// « Nouveautés de tes artistes » — the followed-artists activity shelf. Only
// mounted for authenticated users (the Hub gates it). Self-contained (owns its
// fetch + seen-marking + queue source) to stay lazy-loadable out of the Hub's
// main chunk. Renders nothing when the feed is empty.
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../utils/api.js'
import { useAudioPlayer } from '../../stores/audioPlayer'
import { fmtBpm, relativeAge, relativeAgeShort } from '../../utils/format.js'
import ActivityAlbumCard from '../ActivityAlbumCard.vue'
import DiscoveryCard from '../DiscoveryCard.vue'

const router = useRouter()
const player = useAudioPlayer()

const activityItems = ref([])
const activityNewCount = ref(0)

async function loadActivity() {
  // New-count first, so the badge reflects the state before items get marked seen.
  try {
    const { data } = await api.get('/api/following/activity/new-count')
    activityNewCount.value = data.count ?? 0
  } catch {
    /* silent — the Hub must never break on this */
  }
  try {
    const { data } = await api.get('/api/following/activity', { params: { limit: 12 } })
    activityItems.value = data.items || []
  } catch {
    return /* silent */
  }
  if (!activityItems.value.length) return
  try {
    await api.post('/api/following/activity/seen')
    activityNewCount.value = 0
  } catch {
    /* silent — badge stays, items remain unseen server-side */
  }
}

onMounted(loadActivity)

function activityKey(entry) {
  if (entry.kind === 'album') return `album-${entry.album_id}`
  const item = entry.item
  return item.id ?? `${item.type}-${item.set_id || item.external_url || item.title}`
}

// Build the shelf entries:
//  - Releases sharing `payload.album_id` collapse into ONE expandable album card
//    (a followed release is fanned out into N per-track activities upstream).
//  - Everything else (set, external-link fallback, releases with no album_id) and
//    single-track "albums" stay unit cards, keeping their cover/preview/age.
//  - Collab dedup preserved: the same crawled track surfaced via two followed
//    artists (same catalog_id) is shown once.
const activityShelf = computed(() => {
  const groups = new Map()
  const order = []
  const seenCatalog = new Set()

  for (const item of activityItems.value) {
    if (item.catalog_id != null) {
      if (seenCatalog.has(item.catalog_id)) continue
      seenCatalog.add(item.catalog_id)
    }
    const albumId = item.payload?.album_id
    if (albumId) {
      let group = groups.get(albumId)
      if (!group) {
        group = {
          kind: 'album',
          album_id: albumId,
          album_title: item.payload?.album_title || '',
          artist_name: item.artist || item.artist_name || '',
          release_date: item.release_date || '',
          cover_id: null,
          tracks: [],
        }
        groups.set(albumId, group)
        order.push(group)
      }
      group.tracks.push(item)
      if (!group.cover_id && item.catalog_id && item.has_artwork) group.cover_id = item.catalog_id
      if (!group.release_date && item.release_date) group.release_date = item.release_date
      if (!group.artist_name) group.artist_name = item.artist || item.artist_name || ''
      if (!group.album_title && item.payload?.album_title) {
        group.album_title = item.payload.album_title
      }
    } else {
      order.push({ kind: 'unit', item })
    }
  }

  // A single-track album is just a track: render it as a unit card so it keeps
  // its cover/preview/age instead of an expandable list of one.
  return order.map((entry) =>
    entry.kind === 'album' && entry.tracks.length === 1
      ? { kind: 'unit', item: entry.tracks[0] }
      : entry,
  )
})

function openActivityTrack(item) {
  router.push(`/catalog/${item.catalog_id}`)
}

function activityToPlayerTrack(item) {
  return {
    id: item.catalog_id,
    catalog_id: item.catalog_id,
    title: item.title,
    artist: item.artist || item.artist_name,
    artist_id: item.artist_id,
    bpm: item.bpm,
    key: item.key,
    has_preview: item.has_preview,
  }
}

// Queue source: "next" follows the shelf as displayed — units and album
// tracklists flattened in order; link-only activities (no catalog_id) skipped.
const activitySource = {
  type: 'list',
  getItems: () =>
    activityShelf.value
      .flatMap((entry) => (entry.kind === 'album' ? entry.tracks : [entry.item]))
      .filter((item) => item.catalog_id)
      .map(activityToPlayerTrack),
}

function playActivityTrack(item) {
  player.play(activityToPlayerTrack(item), activitySource)
}

function openSet(item) {
  router.push(`/set/${item.set_id}`)
}

// ── DiscoveryCard meta builders (component drops empty cells, never a dash) ──
// BPM · KEY · brut age — the dense card meta line.
function trackMeta(t) {
  return [t.bpm ? fmtBpm(t.bpm) : '', t.key || '', relativeAgeShort(t.release_date)]
}
// External Deezer link: no BPM/KEY available → "Sur Deezer" + verbose age.
function externalReleaseMeta(item) {
  return ['Sur Deezer', relativeAge(item.release_date)]
}
// Set: no BPM/KEY → verbose age alone (omitted when unknown).
function setMeta(item) {
  const age = relativeAge(item.release_date)
  return age ? [age] : []
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
/* Inert « Bientôt » state — no destination yet, not a dead link. */
.discover-more.is-disabled {
  color: var(--ink-3);
  opacity: 0.55;
  cursor: not-allowed;
}
.hb-shelfgrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3);
  padding: 0 0 var(--space-4);
}

/* ── followed artists activity ── */
.ac-new-badge {
  display: inline-flex;
  align-items: center;
  margin-left: var(--space-2);
  padding: var(--space-05) var(--space-15);
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-xs)/1 var(--font-mono);
  vertical-align: middle;
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
