<template>
  <section class="admin-section">
    <div class="section-header">
      <h2 class="section-title">
        Flags artistes
        <span v-if="flags.length" class="flag-count">{{ flags.length }}</span>
      </h2>
      <div class="filter-group">
        <button
          v-for="s in ['pending', 'validated', 'skipped']"
          :key="s"
          class="filter-btn"
          :class="{ active: filterStatus === s }"
          @click="setFilter(s)"
        >
          {{ s }}
        </button>
      </div>
    </div>

    <div v-if="loadingFlags" class="state">Chargement…</div>
    <div v-else-if="flags.length === 0" class="state">Aucun flag {{ filterStatus }}.</div>

    <div v-else class="table-wrap">
      <table class="flag-table">
        <thead>
          <tr>
            <th class="col-raw">String brute</th>
            <th class="col-reason">Raison</th>
            <th class="col-tokens">Tokens détectés</th>
            <th class="col-deezer">Deezer</th>
            <th class="col-action" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="flag in flags"
            :key="flag.id"
            :class="{ resolved: flag.status !== 'pending' }"
          >
            <td class="col-raw">
              <span class="raw-string">{{ flag.raw_artist_string }}</span>
            </td>
            <td class="col-reason">
              <span class="reason-badge" :class="flag.reason">{{ flag.reason }}</span>
            </td>
            <td class="col-tokens">
              <div class="token-list">
                <span v-for="t in flag.tokens" :key="t" class="token-pill">{{ t }}</span>
              </div>
            </td>
            <td class="col-deezer">
              <div class="deezer-list">
                <span
                  v-for="(did, name) in flag.deezer_ids"
                  :key="name"
                  class="deezer-entry"
                  :class="{ found: !!did, missing: !did }"
                >
                  <span class="deezer-name">{{ name }}</span>
                  <a
                    v-if="did"
                    :href="`https://www.deezer.com/artist/${did}`"
                    target="_blank"
                    class="deezer-id mono dz-link"
                    >{{ did }}</a
                  >
                  <span v-else class="deezer-id mono">✗</span>
                </span>
              </div>
            </td>
            <td class="col-action">
              <template v-if="flag.status === 'pending'">
                <div class="action-btns">
                  <button
                    class="btn-split"
                    :disabled="resolving[flag.id]"
                    :title="`Créer: ${flag.tokens.join(', ')}`"
                    @click="resolve(flag.id, 'split')"
                  >
                    Splitter
                  </button>
                  <button
                    class="btn-keep"
                    :disabled="resolving[flag.id]"
                    :title="`Créer: ${flag.raw_artist_string}`"
                    @click="resolve(flag.id, 'keep')"
                  >
                    Garder
                  </button>
                  <button
                    class="btn-skip"
                    :disabled="resolving[flag.id]"
                    @click="resolve(flag.id, 'skip')"
                  >
                    Ignorer
                  </button>
                </div>
              </template>
              <template v-else>
                <span class="status-badge" :class="flag.status">{{ flag.status }}</span>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../../utils/api.js'

const flags = ref([])
const loadingFlags = ref(false)
const filterStatus = ref('pending')
const resolving = reactive({})

async function fetchFlags() {
  loadingFlags.value = true
  try {
    const { data } = await api.get('/api/admin/artists/flags', {
      params: { status: filterStatus.value },
    })
    flags.value = data
  } finally {
    loadingFlags.value = false
  }
}

async function setFilter(s) {
  filterStatus.value = s
  await fetchFlags()
}

async function resolve(flagId, action) {
  resolving[flagId] = true
  try {
    const { data } = await api.post(`/api/admin/artists/flags/${flagId}/resolve`, { action })
    const idx = flags.value.findIndex((f) => f.id === flagId)
    if (idx !== -1) flags.value[idx] = data
    if (filterStatus.value === 'pending') {
      flags.value = flags.value.filter((f) => f.status === 'pending')
    }
  } finally {
    resolving[flagId] = false
  }
}

onMounted(() => {
  fetchFlags()
})
</script>

<style scoped>
.admin-section {
  margin-bottom: var(--space-8);
  padding: var(--space-5) var(--space-6);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.section-title {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  margin-bottom: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.flag-count {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--accent-soft);
  color: var(--accent-ink);
  padding: var(--space-05) var(--space-15);
  border-radius: 10px;
}
.filter-group {
  display: flex;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.filter-btn {
  padding: var(--space-15) var(--space-3);
  border: none;
  background: var(--surface);
  color: var(--ink-3);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}
.filter-btn:not(:last-child) {
  border-right: 1px solid var(--line-2);
}
.filter-btn.active {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.table-wrap {
  overflow-x: auto;
}
.flag-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}
.flag-table thead th {
  text-align: left;
  padding: 0 var(--space-3) var(--space-25);
  font: 500 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.flag-table tbody td {
  padding: var(--space-25) var(--space-3);
  vertical-align: top;
  border-bottom: 1px solid var(--line);
}
.flag-table tbody tr:last-child td {
  border-bottom: none;
}
.flag-table tbody tr.resolved td {
  opacity: 0.5;
}
.col-raw {
  min-width: 180px;
}
.col-reason {
  width: 160px;
}
.col-tokens {
  width: 200px;
}
.col-deezer {
  width: 220px;
}
.col-action {
  width: 200px;
  text-align: right;
}
.raw-string {
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
}
.reason-badge {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  white-space: nowrap;
}
.reason-badge.comma_unresolved {
  background: var(--warn-soft);
  color: var(--warn-ink);
}
.reason-badge.ampersand_ambiguous {
  background: var(--neg-soft);
  color: var(--neg-ink);
}
.reason-badge.ampersand_unknown {
  background: var(--surface-2);
  color: var(--ink-3);
}
.token-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.token-pill {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: var(--space-05) var(--space-15);
  border-radius: 4px;
  white-space: nowrap;
}
.deezer-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
}
.deezer-entry {
  display: flex;
  gap: var(--space-15);
  align-items: baseline;
}
.deezer-name {
  font-size: var(--fs-xs);
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100px;
}
.deezer-id {
  font-size: var(--fs-xs);
}
.deezer-entry.found .deezer-id {
  color: var(--pos-ink);
}
.deezer-entry.missing .deezer-id {
  color: var(--neg-ink);
}
.action-btns {
  display: flex;
  gap: var(--space-1);
  justify-content: flex-end;
  flex-wrap: wrap;
}
.btn-split,
.btn-keep,
.btn-skip {
  padding: var(--space-1) var(--space-25);
  border-radius: var(--r-sm);
  font: 500 var(--fs-xs)/1 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.12s;
}
.btn-split:disabled,
.btn-keep:disabled,
.btn-skip:disabled {
  opacity: 0.4;
  cursor: default;
}
.btn-split {
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.btn-split:hover:not(:disabled) {
  background: var(--accent);
  color: var(--on-accent);
}
.btn-keep {
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
}
.btn-keep:hover:not(:disabled) {
  background: var(--surface-2);
}
.btn-skip {
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
}
.btn-skip:hover:not(:disabled) {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}
.status-badge {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  padding: var(--space-05) var(--space-2);
  border-radius: 4px;
}
.status-badge.validated {
  background: var(--pos-soft);
  color: var(--pos-ink);
}
.status-badge.skipped {
  background: var(--surface-2);
  color: var(--ink-3);
}
.state {
  /* diverges from canonical .state: smaller font + compact padding (admin panel) */
  font-size: var(--fs-sm);
  padding: var(--space-3) 0;
}
.mono {
  font-family: var(--font-mono);
}
.dz-link {
  color: var(--accent-ink);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}
.dz-link:hover {
  text-decoration: underline;
}
</style>
