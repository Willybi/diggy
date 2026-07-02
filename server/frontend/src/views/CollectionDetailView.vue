<template>
  <div class="collection-detail">
    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!collection" class="state">Collection introuvable.</div>
    <template v-else>
      <div class="page-head">
        <div class="titles">
          <h1>{{ collection.name }}</h1>
          <div class="sub">
            {{ collection.item_count }} track{{ collection.item_count !== 1 ? 's' : '' }}
          </div>
        </div>
        <div class="head-tools">
          <button class="btn-del" @click="confirmDeleteCollection">Supprimer</button>
        </div>
      </div>

      <div v-if="!collection.items.length" class="state">
        Aucun track — ajoute des tracks depuis le catalog.
      </div>

      <div v-else class="table-wrap">
        <table class="tt">
          <colgroup>
            <col class="w-play" />
            <col class="w-track" />
            <col class="w-bpm col-bpm" />
            <col class="w-key" />
            <col class="w-dur col-dur" />
            <col class="w-rm" />
          </colgroup>
          <thead>
            <tr>
              <th class="tl-play"></th>
              <th>Track</th>
              <th class="num col-bpm">BPM</th>
              <th class="num">Key</th>
              <th class="num col-dur">Durée</th>
              <th class="end"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="t in collection.items"
              :key="t.catalog_id"
              :class="{ playing: player.isCurrent(t.catalog_id) }"
              @click="$router.push(`/catalog/${t.catalog_id}`)"
            >
              <td class="tl-play" @click.stop>
                <button
                  v-if="t.has_preview"
                  class="play-btn"
                  :class="{ playing: player.isCurrent(t.catalog_id) && player.playing }"
                  @click="playTrack(t)"
                >
                  <svg
                    v-if="player.isCurrent(t.catalog_id) && player.playing"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                  >
                    <rect x="6" y="5" width="4" height="14" rx="1" />
                    <rect x="14" y="5" width="4" height="14" rx="1" />
                  </svg>
                  <svg v-else viewBox="0 0 24 24" fill="currentColor">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </button>
              </td>
              <td>
                <div class="td-track">
                  <div class="aw">
                    <img
                      v-if="t.has_artwork"
                      :src="`/storage/catalog-artworks/${t.catalog_id}.jpg`"
                      :alt="t.title"
                    />
                    <span v-else class="fallback-letter">{{ (t.title || '?')[0] }}</span>
                  </div>
                  <div class="tx">
                    <div class="tt-title">{{ t.title }}</div>
                    <div v-if="t.artist" class="tt-art">{{ t.artist }}</div>
                  </div>
                </div>
              </td>
              <td class="num col-bpm">
                <span class="td-mono">{{ t.bpm ? fmtBpm(t.bpm) : '' }}</span>
              </td>
              <td class="num">
                <span class="td-key">{{ t.key || '' }}</span>
              </td>
              <td class="num col-dur">
                <span class="td-mono">{{ fmtMs(t.duration_ms) }}</span>
              </td>
              <td class="end" @click.stop>
                <button class="rm-btn" title="Retirer" @click="removeTrack(t.catalog_id)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api.js'
import { useAudioPlayer } from '../stores/audioPlayer'
import { fmtMs, fmtBpm } from '../utils/format'

const route = useRoute()
const router = useRouter()
const player = useAudioPlayer()

const collection = ref(null)
const loading = ref(true)

async function fetchCollection() {
  try {
    const { data } = await api.get(`/api/collections/${route.params.id}`)
    collection.value = data
  } catch {
    collection.value = null
  } finally {
    loading.value = false
  }
}

function playTrack(t) {
  player.play({
    id: t.catalog_id,
    catalog_id: t.catalog_id,
    title: t.title,
    artist: t.artist,
    bpm: t.bpm,
    key: t.key,
  })
}

async function removeTrack(catalogId) {
  try {
    await api.delete(`/api/collections/${route.params.id}/items/${catalogId}`)
    collection.value.items = collection.value.items.filter((i) => i.catalog_id !== catalogId)
    collection.value.item_count = collection.value.items.length
  } catch {
    // silent
  }
}

async function confirmDeleteCollection() {
  if (!confirm(`Supprimer « ${collection.value.name} » ?`)) return
  try {
    await api.delete(`/api/collections/${route.params.id}`)
    router.push('/collections')
  } catch {
    // silent
  }
}

onMounted(fetchCollection)
</script>

<style scoped>
.collection-detail {
  container-type: inline-size;
  min-height: 100%;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* ============ PAGE HEAD ============ */
.page-head {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 26px 30px 18px;
  flex-wrap: wrap;
}
.titles h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.3px;
  color: var(--ink);
}
.sub {
  margin-top: 5px;
  font: 500 13px/1 var(--font-mono);
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 9px;
}

/* ============ BTN DELETE ============ */
.btn-del {
  height: 38px;
  padding: 0 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 13.5px var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.12s, border-color 0.12s;
}
.btn-del:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}

/* ============ TABLE ============ */
.table-wrap {
  padding: 4px 30px 30px;
  overflow-x: auto;
}
table.tt {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 440px;
}
table.tt col.w-play {
  width: 48px;
}
table.tt col.w-track {
  width: auto;
}
table.tt col.w-bpm {
  width: 80px;
}
table.tt col.w-key {
  width: 70px;
}
table.tt col.w-dur {
  width: 90px;
}
table.tt col.w-rm {
  width: 48px;
}
table.tt thead th {
  font: 600 10.5px/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: 0 14px 11px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  user-select: none;
}
table.tt th.num,
table.tt td.num {
  text-align: center;
}
table.tt th.end,
table.tt td.end {
  text-align: right;
}
table.tt tbody tr {
  border-bottom: 1px solid var(--line);
  height: var(--row-h);
  cursor: pointer;
}
table.tt tbody tr:hover {
  background: var(--surface-2);
}
table.tt td {
  padding: 0 14px;
  vertical-align: middle;
}

/* ============ PLAY BUTTON ============ */
.tl-play {
  width: 48px;
  text-align: center;
}
.play-btn {
  width: 30px;
  height: 30px;
  border: none;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  display: grid;
  place-items: center;
  border-radius: 50%;
  padding: 0;
  transition: color 0.12s, background 0.12s;
}
.play-btn svg {
  width: 16px;
  height: 16px;
}
.play-btn:hover {
  color: var(--accent-ink);
  background: var(--accent-soft);
}
.play-btn.playing {
  color: var(--accent-ink);
}

/* ============ TRACK CELL ============ */
.td-track {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.td-track .aw {
  width: 38px;
  height: 38px;
  border-radius: var(--r-xs);
  flex: none;
  background: var(--surface-3);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.td-track .aw img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.fallback-letter {
  font: 600 16px/1 var(--font-ui);
  color: var(--ink-3);
  text-transform: uppercase;
}
.tx {
  min-width: 0;
  flex: 1;
}
.tt-title {
  font-size: 14.5px;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tt-art {
  font-size: 12.5px;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============ MONO CELLS ============ */
.td-mono {
  font: 500 13px var(--font-mono);
  color: var(--ink-2);
}
.td-key {
  font: 500 13px var(--font-mono);
  color: var(--accent-ink);
}

/* ============ REMOVE BUTTON ============ */
.rm-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  display: grid;
  place-items: center;
  border-radius: var(--r-xs);
  padding: 0;
  opacity: 0;
  transition: opacity 0.14s, color 0.14s;
}
table.tt tbody tr:hover .rm-btn {
  opacity: 1;
}
.rm-btn:hover {
  color: var(--neg-ink);
}
.rm-btn svg {
  width: 16px;
  height: 16px;
}

/* ============ PLAYING ROW ============ */
table.tt tbody tr.playing {
  background: var(--accent-soft);
}

/* ============ STATES ============ */
.state {
  padding: 40px 30px;
  color: var(--ink-3);
  font: 400 14px var(--font-ui);
  font-style: italic;
}

/* ============ RESPONSIVE ============ */
@container (max-width: 820px) {
  .col-dur {
    display: none;
  }
}
@container (max-width: 640px) {
  .page-head {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .table-wrap {
    padding: 4px var(--page-px-mobile) 22px;
  }
  .col-bpm {
    display: none;
  }
  .rm-btn {
    opacity: 1;
  }
  table.tt {
    min-width: 0;
  }
  .state {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
}
</style>
