<template>
  <div class="detail-view">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!artist" class="state">Artiste introuvable.</div>
    <template v-else>
      <PageHero
        variant="round"
        :image-src="artist.has_artwork ? `/storage/artist-artworks/${artist.id}.jpg` : null"
        :title="artist.name"
        :subtitle="heroSub"
        :fallback-letter="artist.name[0]"
      >
        <template #badges>
          <StyleTag v-for="g in artist.genres" :key="g.id" :name="g.name" />
        </template>
        <template #actions>
          <a v-if="artist.deezer_id" class="btn-ghost" :href="`https://deezer.com/artist/${artist.deezer_id}`" target="_blank">Deezer</a>
          <a v-if="artist.soundcloud_id" class="btn-ghost" :href="`https://soundcloud.com/${artist.soundcloud_id}`" target="_blank">SoundCloud</a>
          <a v-if="artist.trackid_id" class="btn-ghost" :href="`https://trackid.net/artist/${artist.trackid_id}`" target="_blank">TrackID</a>
        </template>
      </PageHero>

      <StatStrip :stats="stats" />

      <RelBlock v-if="artist.aliases.length" title="Aliases">
        <div class="aliases-text">
          {{ artist.aliases.map(a => a.alias).join(', ') }}
        </div>
      </RelBlock>

      <RelBlock v-if="artist.bio" title="Biographie">
        <div class="bio-text">{{ artist.bio }}</div>
      </RelBlock>

      <RelBlock v-if="artist.catalog_tracks.length" title="Tracks" :count="artist.stats.nb_catalog">
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead>
              <tr>
                <th class="mt-track">Track</th>
                <th class="mt-style">Style</th>
                <th class="mt-num">BPM</th>
                <th class="mt-num">Key</th>
                <th class="mt-num">Rating</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in artist.catalog_tracks" :key="t.id">
                <td class="mt-track">
                  <RouterLink :to="`/catalog/${t.id}`" class="mt-link">
                    <span class="mt-title">{{ t.title }}</span>
                    <span class="mt-artist">{{ t.artist }}</span>
                  </RouterLink>
                </td>
                <td class="mt-style"><StyleTag v-if="t.style" :name="t.style" /></td>
                <td class="mt-num mono">{{ t.bpm ? fmtBpm(t.bpm) : '—' }}</td>
                <td class="mt-num mono">{{ t.key || '—' }}</td>
                <td class="mt-num">
                  <span v-if="t.rating" class="rating">
                    <span v-for="n in 5" :key="n" class="star" :class="{ 'is-on': n <= t.rating }">★</span>
                  </span>
                  <span v-else class="dash">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </RelBlock>

      <RelBlock v-if="artist.sets.length" title="Sets" :count="artist.stats.nb_sets">
        <AppearRow
          v-for="s in artist.sets"
          :key="s.set_id"
          :title="s.title"
          :subtitle="setSub(s)"
          :to="`/set/${s.set_id}`"
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
import StyleTag from '../components/StyleTag.vue'
import { fmtBpm, fmtDate } from '../utils/format'

const route = useRoute()
const artist = ref(null)
const loading = ref(true)

const heroSub = computed(() => {
  if (!artist.value) return null
  const parts = []
  if (artist.value.real_name) parts.push(artist.value.real_name)
  if (artist.value.country) parts.push(artist.value.country)
  return parts.join(' · ') || null
})

const stats = computed(() => {
  if (!artist.value) return []
  const s = artist.value.stats
  return [
    { label: 'Catalog', value: s.nb_catalog ?? 0 },
    { label: 'In lib', value: s.nb_lib ?? 0 },
    { label: 'Sets', value: s.nb_sets ?? 0 },
    { label: 'Rating moy.', value: s.avg_rating ?? '--' },
  ]
})

function setSub(s) {
  const parts = []
  if (s.played_date) parts.push(fmtDate(s.played_date))
  if (s.role === 'b2b') parts.push('B2B')
  const id = s.identified_tracks === s.total_tracks
    ? `${s.total_tracks} tracks · toutes identifiées`
    : `${s.total_tracks} tracks · ${s.identified_tracks} identifiées`
  parts.push(id)
  return parts.join(' · ')
}

onMounted(async () => {
  try {
    const { data } = await axios.get(`/api/artists/${route.params.id}`)
    artist.value = data
  } catch {
    artist.value = null
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
.aliases-text, .bio-text {
  padding: 12px 14px;
  font: 400 13.5px/1.5 var(--font-ui);
  color: var(--ink-2);
}
.btn-ghost {
  padding: 8px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  text-decoration: none;
  transition: background 0.12s, color 0.12s;
}
.btn-ghost:hover {
  background: var(--surface-2);
  color: var(--ink);
}
/* Mini track table */
.mini-table-wrap { overflow-x: auto; }
.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.mini-table thead th {
  text-align: left;
  padding: 8px 12px;
  font: 500 10.5px/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
}
.mini-table tbody td {
  padding: 8px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--line);
}
.mini-table tbody tr:last-child td { border-bottom: none; }
.mini-table tbody tr:hover td { background: var(--surface-2); }
.mt-track { min-width: 160px; }
.mt-style { width: 90px; }
.mt-num { width: 56px; text-align: center; }
.mono { font-family: var(--font-mono); color: var(--ink-2); }
.mt-link { text-decoration: none; color: inherit; }
.mt-link:hover .mt-title { color: var(--accent-ink); }
.mt-title {
  display: block;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mt-artist {
  display: block;
  font-size: 12px;
  color: var(--ink-2);
}
.rating { white-space: nowrap; }
.star { color: var(--ink-3); font-size: 12px; }
.star.is-on { color: var(--accent-ink); }
.dash { color: var(--ink-3); }

.state {
  color: var(--ink-3);
  font-size: 14px;
  font-style: italic;
  padding-top: 40px;
}
</style>
