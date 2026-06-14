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
          <StyleTag v-if="track.style" :name="track.style" />
          <Rating v-if="track.in_lib && track.rating" :value="track.rating" />
        </template>
        <template #actions>
          <HeroPlayer v-if="track.has_preview" :catalog-id="track.id" />
        </template>
      </PageHero>

      <StatStrip :stats="stats" />

      <RelBlock v-if="track.genres.length" title="Genres">
        <div class="genre-list">
          <StyleTag v-for="g in track.genres" :key="g.id" :name="g.name" />
        </div>
      </RelBlock>

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
import axios from 'axios'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RelBlock from '../components/RelBlock.vue'
import AppearRow from '../components/AppearRow.vue'
import InLibBadge from '../components/InLibBadge.vue'
import StyleTag from '../components/StyleTag.vue'
import Rating from '../components/Rating.vue'
import HeroPlayer from '../components/HeroPlayer.vue'
import { fmtMs, fmtBpm, fmtDate } from '../utils/format'

const route = useRoute()
const track = ref(null)
const loading = ref(true)

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
    { label: 'Key', value: t.key || '--' },
    { label: 'Durée', value: fmtMs(t.duration_ms) },
    { label: 'Année', value: t.release_date ? new Date(t.release_date).getFullYear() : '--' },
    { label: 'ISRC', value: t.isrc || '--' },
  ]
})

onMounted(async () => {
  try {
    const { data } = await axios.get(`/api/catalog/${route.params.id}`)
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
  max-width: 900px;
  margin: 0 auto;
}
.genre-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 14px;
}
.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}
</style>
