<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!track" class="state">Track introuvable.</div>
    <template v-else>
      <PageHero
        variant="square"
        :image-src="coverSrc"
        :title="track.title"
        :subtitle="track.artist"
        :fallback-letter="(track.title || '?')[0]"
      >
        <template #badges>
          <InLibBadge :in-lib="track.in_lib" />
          <RouterLink v-if="track.genre" :to="`/style/${encodeURIComponent(track.genre)}`" style="text-decoration:none">
            <StyleTag :name="track.genre" />
          </RouterLink>
          <StyleTag v-else-if="track.style" :name="track.style" />
        </template>
        <template #actions>
          <HeroPlayer v-if="track.has_preview" :catalog-id="track.id" :title="track.title" :artist="track.artist" :bpm="track.bpm" :track-key="track.key" />
        </template>
      </PageHero>

      <StatStrip :stats="stats" />

      <div v-if="track.label || track.beatport_id" class="track-meta">
        <span v-if="track.label" class="meta-label">{{ track.label }}</span>
        <a
          v-if="track.beatport_id"
          :href="`https://www.beatport.com/track/-/${track.beatport_id}`"
          target="_blank"
          rel="noopener"
          class="meta-link beatport-link"
        >Beatport ↗</a>
      </div>

      <!-- Admin: enrichment actions -->
      <div v-if="auth.user?.is_admin" class="admin-card">
        <div class="admin-header">
          <span class="admin-label">Admin</span>
          <span class="mono muted">beatport_id: {{ track.beatport_id || '—' }} · deezer_id: {{ track.deezer_id || '—' }}</span>
        </div>

        <div class="admin-row">
          <button class="btn-sync" :disabled="enriching" @click="enrichBeatport(false)">
            {{ enriching ? 'Recherche…' : track.beatport_id ? 'Re-enrichir Beatport' : 'Enrichir via Beatport' }}
          </button>
          <button class="btn-sync" :disabled="enriching" @click="enrichBeatport(true)">
            {{ enriching ? '…' : 'Forcer genre Beatport' }}
          </button>
          <span v-if="enrichResult" class="enrich-result" :class="enrichResult.cls">{{ enrichResult.text }}</span>
        </div>

        <div class="admin-row" style="margin-top:8px">
          <button class="btn-sync" :disabled="!track.deezer_id || fetchingDzGenre" @click="fetchDeezerGenre(false)">
            {{ fetchingDzGenre ? 'Recherche…' : 'Genre Deezer' }}
          </button>
          <template v-if="dzGenreResult">
            <span class="enrich-result" :class="dzGenreResult.cls">{{ dzGenreResult.text }}</span>
            <button
              v-if="dzGenreResult.genres?.length"
              class="btn-sync"
              :disabled="fetchingDzGenre"
              @click="applyDeezerGenre(dzGenreResult.genres[0])"
            >Appliquer « {{ dzGenreResult.genres[0] }} »</button>
          </template>
        </div>
      </div>

      <RelBlock v-if="track.radar_appearances.length" title="Détecté dans" :count="track.radar_appearances.length">
        <AppearRow
          v-for="r in track.radar_appearances"
          :key="r.playlist_id"
          :title="r.playlist_title || 'Playlist'"
          :subtitle="r.detected_at ? fmtDate(r.detected_at) : null"
        />
      </RelBlock>

      <RelBlock v-if="track.set_appearances.length" title="Apparaît dans" :count="track.set_appearances.length">
        <AppearRow
          v-for="s in track.set_appearances"
          :key="s.set_id"
          :title="s.set_title"
          :subtitle="s.played_date ? fmtDate(s.played_date) : null"
          :to="`/set/${s.set_id}`"
        />
      </RelBlock>

      <RelBlock v-if="track.same_artist_tracks.length" :title="`Du même artiste`" :count="track.same_artist_tracks.length">
        <AppearRow
          v-for="t in track.same_artist_tracks"
          :key="t.id"
          :title="t.title"
          :subtitle="t.in_lib ? '★ In lib' : null"
          :to="`/catalog/${t.id}`"
        />
      </RelBlock>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api.js'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import AppearRow from '../components/AppearRow.vue'
import InLibBadge from '../components/InLibBadge.vue'
import StyleTag from '../components/StyleTag.vue'
import HeroPlayer from '../components/HeroPlayer.vue'
import { useAuthStore } from '../stores/auth.js'
import { fmtMs, fmtBpm, fmtDate } from '../utils/format'

const route = useRoute()
const auth = useAuthStore()
const track = ref(null)
const loading = ref(true)
const enriching = ref(false)
const enrichResult = ref(null)
const fetchingDzGenre = ref(false)
const dzGenreResult = ref(null)

const coverSrc = computed(() => {
  if (!track.value) return null
  const t = track.value
  if (t.lib_track_id && t.has_artwork) return `/storage/artworks/${t.lib_track_id}.jpg`
  if (t.has_artwork) return `/storage/catalog-artworks/${t.id}.jpg`
  return null
})

const stats = computed(() => {
  if (!track.value) return []
  const t = track.value
  return [
    { label: 'BPM', value: fmtBpm(t.bpm) },
    { label: 'Key', value: t.key || '—' },
    { label: 'Durée', value: fmtMs(t.duration_ms) },
    { label: 'Année', value: t.release_date ? new Date(t.release_date).getFullYear() : '—' },
    { label: 'Rating', value: t.rating ? '★'.repeat(t.rating) : '—' },
    { label: 'Radar', value: t.nb_radar_playlists || '—' },
  ]
})

async function enrichBeatport(forceGenre = false) {
  enriching.value = true
  enrichResult.value = null
  try {
    const params = forceGenre ? '?force_genre=true' : ''
    const { data } = await api.post(
      `/api/admin/enrich-beatport/${track.value.id}${params}`,
      {},
    )
    if (data.status === 'enriched') {
      track.value.bpm = data.bpm
      track.value.key = data.key
      track.value.label = data.label
      track.value.genre = data.genre
      track.value.beatport_id = data.beatport_id
      track.value.bpm_source = 'beatport'
      track.value.key_source = 'beatport'
      const parts = [`BPM=${data.bpm}`, `Key=${data.key}`]
      if (data.genre) parts.push(`Genre=${data.genre}`)
      if (data.label) parts.push(`Label=${data.label}`)
      enrichResult.value = { text: parts.join(' '), cls: 'ok' }
    } else if (data.status === 'unchanged') {
      enrichResult.value = { text: 'Déjà à jour', cls: 'muted' }
    } else {
      if (forceGenre) track.value.genre = null
      enrichResult.value = { text: 'Non trouvé sur Beatport' + (forceGenre ? ' — genre effacé' : ''), cls: 'warn' }
    }
  } catch (e) {
    enrichResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    enriching.value = false
  }
}

async function fetchDeezerGenre() {
  fetchingDzGenre.value = true
  dzGenreResult.value = null
  try {
    const { data } = await api.get(`/api/admin/deezer-genre/${track.value.id}`)
    if (data.genres?.length) {
      dzGenreResult.value = { text: data.genres.join(', '), cls: 'ok', genres: data.genres }
    } else {
      dzGenreResult.value = { text: 'Aucun genre Deezer', cls: 'warn' }
    }
  } catch (e) {
    dzGenreResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    fetchingDzGenre.value = false
  }
}

async function applyDeezerGenre(genre) {
  fetchingDzGenre.value = true
  try {
    await api.get(`/api/admin/deezer-genre/${track.value.id}?apply=true`)
    track.value.genre = genre
    dzGenreResult.value = { text: `Appliqué : ${genre}`, cls: 'ok' }
  } catch (e) {
    dzGenreResult.value = { text: e.response?.data?.detail || 'Erreur', cls: 'err' }
  } finally {
    fetchingDzGenre.value = false
  }
}

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/catalog/${route.params.id}`)
    track.value = data
  } catch {
    track.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: var(--detail-max-w);
  margin-inline: auto;
}
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}

/* Track meta (label + external links) */
.track-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0 4px;
  font: 400 13px/1 var(--font-ui);
  color: var(--ink-muted);
}
.meta-label {
  color: var(--ink-2);
}
.meta-link {
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
}
.meta-link:hover {
  text-decoration: underline;
}

/* Admin card */
.admin-card {
  margin: 16px 0;
  padding: 14px 18px;
  background: var(--surface);
  border: 1px solid var(--warn-ink);
  border-radius: var(--r-sm);
}
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.admin-label {
  font: 600 11px/1 var(--font-mono);
  text-transform: uppercase;
  color: var(--warn-ink);
}
.mono { font-family: var(--font-mono); font-size: 12px; }
.muted { color: var(--ink-3); }
.admin-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.btn-sync {
  padding: 7px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn-sync:disabled { opacity: 0.5; cursor: default; }
.enrich-result {
  font: 400 13px/1.4 var(--font-ui);
}
.enrich-result.ok { color: var(--pos-ink); }
.enrich-result.warn { color: var(--warn-ink); }
.enrich-result.err { color: var(--neg-ink); }
.enrich-result.muted { color: var(--ink-3); }
</style>
