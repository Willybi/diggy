<template>
  <div class="collections-view">
    <div class="page-head">
      <div class="titles">
        <h1>Collections</h1>
        <div class="sub">{{ collections.length }} collection{{ collections.length !== 1 ? 's' : '' }}</div>
      </div>
      <div class="head-tools">
        <button class="btn-add" @click="showCreateModal = true">
          <span class="plus">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M12 5v14M5 12h14" stroke-linecap="round" />
            </svg>
          </span>
          <span class="addlbl">Nouvelle collection</span>
        </button>
      </div>
    </div>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!collections.length" class="state">
      Aucune collection — crée ta première playlist
    </div>

    <div v-else class="coll-grid">
      <div
        v-for="coll in collections"
        :key="coll.id"
        class="coll-card"
        @click="$router.push(`/collections/${coll.id}`)"
      >
        <div class="coll-name">{{ coll.name }}</div>
        <div class="coll-meta">
          <span class="coll-count">{{ coll.item_count }} track{{ coll.item_count !== 1 ? 's' : '' }}</span>
          <span class="coll-date">{{ fmtDate(coll.created_at) }}</span>
        </div>
        <button class="coll-del" title="Supprimer" @click.stop="confirmDelete(coll)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
            <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="closeCreate">
      <div class="modal-box">
        <h2>Nouvelle collection</h2>
        <input
          ref="nameInput"
          v-model="newName"
          type="text"
          placeholder="Nom de la collection"
          @keydown.enter="doCreate"
          autofocus
        />
        <div class="modal-actions">
          <button class="btn-cancel" @click="closeCreate">Annuler</button>
          <button class="btn-confirm" :disabled="!newName.trim() || creating" @click="doCreate">
            {{ creating ? 'Création…' : 'Créer' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import api from '../utils/api.js'
import { fmtDate } from '../utils/format'

const collections = ref([])
const loading = ref(true)
const showCreateModal = ref(false)
const newName = ref('')
const creating = ref(false)
const nameInput = ref(null)

async function fetchCollections() {
  loading.value = true
  try {
    const { data } = await api.get('/api/collections/')
    collections.value = data
  } finally {
    loading.value = false
  }
}

function closeCreate() {
  showCreateModal.value = false
  newName.value = ''
}

async function doCreate() {
  if (!newName.value.trim() || creating.value) return
  creating.value = true
  try {
    await api.post('/api/collections/', { name: newName.value.trim() })
    closeCreate()
    await fetchCollections()
  } finally {
    creating.value = false
  }
}

async function confirmDelete(coll) {
  if (!confirm(`Supprimer « ${coll.name} » ?`)) return
  try {
    await api.delete(`/api/collections/${coll.id}`)
    await fetchCollections()
  } catch {
    // silent
  }
}

onMounted(async () => {
  await fetchCollections()
  if (showCreateModal.value) {
    await nextTick()
    nameInput.value?.focus()
  }
})
</script>

<style scoped>
.collections-view {
  container-type: inline-size;
  min-height: 100%;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* ============ PAGE HEAD ============ */
.titles h1 {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -0.3px;
  color: var(--ink);
}
.sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* ============ BTN ADD ============ */
.btn-add {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-add:hover {
  background: var(--accent-hover);
}
.btn-add svg {
  width: 15px;
  height: 15px;
}

/* ============ GRID ============ */
.coll-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-4);
  padding: var(--space-4) var(--page-px) var(--space-8);
}
.coll-card {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: var(--space-5);
  cursor: pointer;
  transition: background 0.12s;
}
.coll-card:hover {
  background: var(--surface-2);
}
.coll-name {
  font: 600 var(--fs-title)/1.3 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: var(--space-6);
}
.coll-meta {
  margin-top: var(--space-2);
  display: flex;
  align-items: center;
  gap: var(--space-25);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
}
.coll-del {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: var(--ink-3);
  border-radius: var(--r-xs);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.14s, color 0.14s;
}
.coll-card:hover .coll-del {
  opacity: 1;
}
.coll-del:hover {
  color: var(--neg-ink);
}
.coll-del svg {
  width: 16px;
  height: 16px;
}

/* ============ MODAL ============ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-modal);
  display: grid;
  place-items: center;
  z-index: 900;
}
.modal-box {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: var(--space-6);
  width: 380px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow-lg);
}
.modal-box h2 {
  margin: 0 0 var(--space-4);
  font: 600 var(--fs-md)/1 var(--font-ui);
  color: var(--ink);
}
.modal-box input {
  width: 100%;
  height: 42px;
  padding: 0 var(--space-4);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
  outline: none;
  box-sizing: border-box;
}
.modal-box input::placeholder {
  color: var(--ink-3);
}
.modal-box input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-25);
  margin-top: var(--space-5);
}
.btn-cancel {
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
}
.btn-cancel:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}
.btn-confirm {
  height: 38px;
  padding: 0 var(--space-5);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
}
.btn-confirm:hover {
  background: var(--accent-hover);
}
.btn-confirm:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ============ STATES ============ */
.state {
  padding: var(--space-10) var(--page-px);
  color: var(--ink-3);
  font: 400 var(--fs-base) var(--font-ui);
  font-style: italic;
}

/* ============ RESPONSIVE ============ */
@container (max-width: 640px) {
  .page-head {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .coll-grid {
    padding: var(--space-4) var(--page-px-mobile) var(--space-6);
  }
  .state {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
}
@container (max-width: 500px) {
  .coll-grid {
    grid-template-columns: 1fr;
  }
}
</style>
