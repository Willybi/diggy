<template>
  <section class="flags-wrap">
    <div class="at-region">
      <div class="at-head">
        <h2 class="at-title">
          Flags artistes
          <span v-if="total" class="at-count">{{ total }}</span>
        </h2>
        <div class="at-seg">
          <button
            v-for="s in ['pending', 'validated', 'skipped']"
            :key="s"
            class="at-seg-b"
            :class="{ active: filterStatus === s }"
            @click="setFilter(s)"
          >
            {{ s }}
          </button>
        </div>
      </div>

      <div v-if="loadingFlags" class="at-empty">Chargement…</div>
      <div v-else-if="flags.length === 0" class="at-empty">Aucun flag {{ filterStatus }}.</div>

      <div v-else class="at-scroll">
        <table class="at-table">
          <thead>
            <tr>
              <th>Chaîne brute</th>
              <th>Raison</th>
              <th>Segments</th>
              <th>Statut</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="flag in flags" :key="flag.id">
              <tr>
                <td data-label="Chaîne brute" data-lead>
                  <span class="at-id">{{ flag.raw_artist_string }}</span>
                </td>
                <td data-label="Raison">
                  <span class="at-pill at-pill--neutral">{{ flag.reason }}</span>
                </td>
                <td data-label="Segments" data-stack>
                  <div class="at-chips">
                    <span v-for="name in flag.tokens" :key="name" class="at-chip">
                      <span class="at-chip-k">{{ name }}</span>
                      <span class="at-chip-v fl-dz" :class="dzClass(name)">
                        <AdminIcon v-if="dz(name)?.status === 'searching'" name="arc" :size="10" />
                        <template v-else-if="dz(name)?.status === 'found'">
                          <AdminIcon name="check" :size="10" />
                          <a
                            :href="`https://www.deezer.com/artist/${dz(name).hit.deezer_id}`"
                            target="_blank"
                            class="fl-dz-link"
                            :title="`${dz(name).hit.name} · ${dz(name).hit.nb_fan?.toLocaleString('fr-FR')} fans`"
                            @click.stop
                            >{{ dz(name).hit.nb_fan?.toLocaleString('fr-FR') }}</a
                          >
                        </template>
                        <template v-else-if="dz(name)?.status === 'missing'">
                          <AdminIcon name="x" :size="10" />
                          <span>0</span>
                        </template>
                        <span v-else>—</span>
                      </span>
                    </span>
                  </div>
                </td>
                <td data-label="Statut">
                  <span
                    class="at-pill"
                    :class="flag.status === 'validated' ? 'at-pill--ok' : 'at-pill--neutral'"
                    >{{ flag.status }}</span
                  >
                </td>
                <td data-act>
                  <div v-if="flag.status === 'pending'" class="fl-actions">
                    <button
                      class="btn btn--sm fl-btn"
                      :class="{ 'is-open': editingFlagId === flag.id }"
                      :disabled="resolving[flag.id]"
                      title="Éditer les segments puis découper"
                      @click="toggleEditor(flag)"
                    >
                      <AdminIcon name="split" :size="15" />
                      Découper…
                    </button>
                    <button
                      class="btn btn--sm fl-btn"
                      :disabled="resolving[flag.id]"
                      :title="`Créer: ${flag.raw_artist_string}`"
                      @click="resolve(flag.id, 'keep')"
                    >
                      Garder
                    </button>
                    <button
                      class="btn btn--sm fl-btn"
                      :disabled="resolving[flag.id]"
                      @click="resolve(flag.id, 'skip')"
                    >
                      Ignorer
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="editingFlagId === flag.id" class="at-editor">
                <td :colspan="5">
                  <ArtistSegmentSplitter
                    :key="flag.id"
                    :raw="flag.raw_artist_string"
                    :pending="!!resolving[flag.id]"
                    :error="editError"
                    @confirm="onSplitConfirm(flag, $event)"
                    @cancel="closeEditor"
                  />
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="at-pager">
        <button class="btn btn--sm" :disabled="page <= 1" @click="prevPage()">Précédent</button>
        <span class="at-pager-count">{{ page }} / {{ totalPages }}</span>
        <button class="btn btn--sm" :disabled="page >= totalPages" @click="nextPage()">
          Suivant
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import api from '../../utils/api.js'
import { foldArtistName } from '../../utils/artistSplit.js'
import ArtistSegmentSplitter from './ArtistSegmentSplitter.vue'
import AdminIcon from './AdminIcon.vue'

const PER_PAGE = 25

const flags = ref([])
const total = ref(0)
const page = ref(1)
const loadingFlags = ref(false)
const filterStatus = ref('pending')
const resolving = reactive({})
const editingFlagId = ref(null)
const editError = ref('')

const totalPages = computed(() => Math.ceil(total.value / PER_PAGE))

async function fetchFlags() {
  loadingFlags.value = true
  try {
    const { data } = await api.get('/api/admin/artists/flags', {
      params: { status: filterStatus.value, page: page.value, per_page: PER_PAGE },
    })
    flags.value = data.items
    total.value = data.total
    queueDeezer(flags.value.flatMap((f) => f.tokens || []))
  } finally {
    loadingFlags.value = false
  }
}

async function setFilter(s) {
  filterStatus.value = s
  page.value = 1
  await fetchFlags()
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  fetchFlags()
}

function nextPage() {
  if (page.value >= totalPages.value) return
  page.value++
  fetchFlags()
}

// ── Live Deezer signal per token (display only) ───────────────────────────────
// The flag.deezer_ids snapshot is only filled by the sync_artists worker; flags
// created manually or by the auto_split backfill carry an empty map. So we search
// Deezer live for every token on the page (reusing the admin search endpoint the
// splitter uses) and show a per-token signal so the admin decides "split or keep"
// with eyes open. Cached by token text (searched at most once across pages) and
// processed sequentially to stay gentle on the admin Deezer rate bucket.
const DEEZER_DEBOUNCE_MS = 400
const deezerByText = ref({})
const deezerQueue = new Set()
let deezerTimer = null

const dz = (text) => deezerByText.value[text]

// Colour channel of a token's Deezer signal chip: found → --pos, searching →
// accent (arc), missing/error → neutral (a missing match is a normal case).
function dzClass(name) {
  const s = dz(name)?.status
  if (s === 'found') return 'is-found'
  if (s === 'searching') return 'is-searching'
  if (s === 'missing') return 'is-missing'
  return ''
}

function queueDeezer(texts) {
  let queued = false
  for (const raw of texts) {
    const text = (raw || '').trim()
    if (!text || deezerByText.value[text]) continue
    deezerByText.value[text] = { status: 'searching', hit: null }
    deezerQueue.add(text)
    queued = true
  }
  if (!queued) return
  clearTimeout(deezerTimer)
  deezerTimer = setTimeout(flushDeezerQueue, DEEZER_DEBOUNCE_MS)
}

async function flushDeezerQueue() {
  const texts = [...deezerQueue]
  deezerQueue.clear()
  // Sequential: 25 flags × ~2 tokens fired at once would trip the 429 bucket.
  for (const text of texts) {
    await searchDeezer(text)
  }
}

// "Found" = a hit whose name folds equal to the token (Deezer returns fuzzy hits
// for anything, so a non-empty list alone proves nothing — same rule as the splitter).
async function searchDeezer(text) {
  try {
    const { data } = await api.get('/api/admin/artists/search-deezer', { params: { q: text } })
    const hit = (data || []).find((h) => foldArtistName(h.name) === foldArtistName(text)) || null
    deezerByText.value[text] = { status: hit ? 'found' : 'missing', hit }
  } catch {
    // 429 / network errors are toasted by the api interceptor; leave the entry so
    // a false miss never shows — a neutral "—" reads as "not checked".
    deezerByText.value[text] = { status: 'error', hit: null }
  }
}

onUnmounted(() => clearTimeout(deezerTimer))

function applyResolved(flagId, data) {
  const idx = flags.value.findIndex((f) => f.id === flagId)
  if (idx !== -1) flags.value[idx] = data
  if (filterStatus.value === 'pending') {
    flags.value = flags.value.filter((f) => f.status === 'pending')
    total.value = Math.max(0, total.value - 1)
  }
}

async function resolve(flagId, action) {
  resolving[flagId] = true
  try {
    const { data } = await api.post(`/api/admin/artists/flags/${flagId}/resolve`, { action })
    applyResolved(flagId, data)
  } finally {
    resolving[flagId] = false
  }
}

function toggleEditor(flag) {
  editError.value = ''
  editingFlagId.value = editingFlagId.value === flag.id ? null : flag.id
}

function closeEditor() {
  editingFlagId.value = null
}

// Upsert the flag with the EDITED tokens (keeping its original `reason` so its
// category is preserved and any already-found deezer_ids are retained by the
// backend upsert), then resolve it as a split. raw_artist_string stays verbatim.
async function onSplitConfirm(flag, tokens) {
  if (!tokens.length) return
  resolving[flag.id] = true
  editError.value = ''
  try {
    await api.post('/api/admin/artists/flags/manual', {
      raw_artist_string: flag.raw_artist_string,
      tokens,
      reason: flag.reason,
    })
    const { data } = await api.post(`/api/admin/artists/flags/${flag.id}/resolve`, {
      action: 'split',
    })
    editingFlagId.value = null
    applyResolved(flag.id, data)
  } catch (e) {
    editError.value = e.response?.data?.detail || 'Erreur lors du split'
  } finally {
    resolving[flag.id] = false
  }
}

onMounted(() => {
  fetchFlags()
})
</script>

<style scoped>
.flags-wrap {
  margin-bottom: var(--space-8);
}

/* Chaîne brute : sur mobile la ligne de tête a un peu plus de corps. */
.at-id {
  font-size: var(--fs-table-sm);
}

/* Signal Deezer par token, logé dans la valeur d'une chip clé/valeur. */
.fl-dz {
  display: inline-flex;
  align-items: center;
  gap: var(--space-05);
  color: var(--ink-3);
}
.fl-dz.is-found {
  color: var(--pos-ink);
}
.fl-dz.is-searching {
  color: var(--accent-ink);
}
.fl-dz.is-missing {
  color: var(--ink-3);
}
.fl-dz-link {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: inherit;
  text-decoration: none;
}
.fl-dz-link:hover {
  text-decoration: underline;
}

/* Actions de la file : boutons neutres, fer à droite en desktop. */
.fl-actions {
  display: flex;
  gap: var(--space-15);
  justify-content: flex-end;
  flex-wrap: wrap;
}
.fl-btn.is-open {
  background: var(--accent);
  border-color: transparent;
  color: var(--on-accent);
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* Ligne éditeur dépliable (Flags) : traitement --surface-2 + filet haut, embarque
   l'archétype E. Le socle transforme la rangée en carte sous 859 px — on neutralise
   son ::before de label et son flex label·valeur pour laisser respirer le splitter. */
.at-editor td {
  padding: var(--space-3);
  background: var(--surface-2);
  border-top: 1px solid var(--line);
}

@container (max-width: 859px) {
  .at-editor td {
    display: block;
  }
  .at-editor td::before {
    display: none;
  }
  .fl-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .fl-actions .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
}
</style>
